"""Read-only Open Food Facts integration; reuse the audited candidate import path."""
import csv
import hashlib
import io
import json
import re
import threading
import time
from collections import deque
from typing import Any

import requests

from repository import BusinessError, Repository
from services.import_service import COLUMNS, preview_import, commit_import
from services.unit_service import normalize_weight

BASE = 'https://world.openfoodfacts.org'
USER_AGENT = 'QianpinZhiying/1.0 (https://github.com/workyy-SVG/OPAshuqian)'
ATTRIBUTION = 'Open Food Facts · ODbL / Database Contents License'
FIELDS = 'code,product_name,product_name_zh,brands,quantity,ingredients_text,ingredients_text_zh,nutriments,last_modified_t'
_lock = threading.Lock()
_calls: dict[str, deque[float]] = {'barcode': deque(), 'name': deque()}


def _reserve(kind: str) -> None:
    with _lock:
        recent = _calls[kind]
        tick = time.monotonic()
        while recent and tick - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= (12 if kind == 'barcode' else 8):
            raise BusinessError('公共查询频率已达上限，请一分钟后再试。', 'food_rate_limit')
        recent.append(tick)


def lookup(query: str, kind: str = 'barcode') -> list[dict[str, Any]]:
    query = query.strip()
    if kind not in ('barcode', 'name'):
        raise BusinessError('请选择条码查询或名称搜索。')
    if kind == 'barcode' and not re.fullmatch(r'[0-9]{8}|[0-9]{12,14}', query):
        raise BusinessError('请输入8、12、13或14位数字条码，保留前导零。')
    if kind == 'name' and not 2 <= len(query) <= 100:
        raise BusinessError('商品名称请输入2至100个字符。')
    _reserve(kind)
    url = f'{BASE}/api/v3/product/{query}' if kind == 'barcode' else f'{BASE}/cgi/search.pl'
    params = {'fields': FIELDS, 'lc': 'zh'}
    if kind == 'name':
        params.update(search_terms=query, search_simple='1', action='process', json='1', page_size='5')
    try:
        with requests.get(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=(5, 15),
                          stream=True, allow_redirects=False) as response:
            if response.status_code == 404:
                return []
            if response.status_code == 429:
                raise BusinessError('数据源查询限流，请稍后再试或使用CSV演示。', 'food_rate_limit')
            if response.status_code != 200:
                raise BusinessError('数据源暂时不可用，请稍后再试或使用CSV演示。', 'food_unavailable')
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise BusinessError('数据源响应过大，已停止读取。', 'food_response')
            data = json.loads(body)
    except BusinessError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise BusinessError('查询失败或超时，请稍后重试；CSV导入仍可使用。', 'food_network') from exc
    if not isinstance(data, dict):
        raise BusinessError('数据源返回格式异常。', 'food_response')
    products = [data.get('product')] if kind == 'barcode' else data.get('products', [])
    if not isinstance(products, list):
        raise BusinessError('数据源返回格式异常。', 'food_response')
    return [p for p in products[:5] if isinstance(p, dict) and re.fullmatch(r'[0-9]{8,14}', str(p.get('code', '')))]


def candidate_preview(product: dict[str, Any], sku: str, version: str) -> dict[str, Any]:
    code = str(product.get('code', ''))
    if not re.fullmatch(r'[0-9]{8,14}', code):
        raise BusinessError('数据源条码无效，请重新查询。')
    values = {'product_name': product.get('product_name_zh') or product.get('product_name'),
              'ingredients_text': product.get('ingredients_text_zh') or product.get('ingredients_text')}
    quantity = product.get('quantity')
    weight = re.fullmatch(r'(\d+(?:\.\d+)?\s*(?:mg|kg|毫克|千克|公斤|g|克|斤|两))\s*[e℮]?', quantity.strip(), re.I) if isinstance(quantity, str) else None
    if weight:
        try:
            normalize_weight(weight[1])
            values['net_weight_g'] = weight[1]
        except ValueError:
            pass
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, COLUMNS)
    writer.writeheader()
    for field, raw in values.items():
        if isinstance(raw, str) and raw.strip():
            writer.writerow(dict(sku=sku, product_version=version, field_key=field, raw_value=raw,
                                 context_key='general', source_label=ATTRIBUTION,
                                 source_locator=f'{BASE}/product/{code}#snapshot={snapshot_id(product)}', effective_from=''))
    preview = preview_import(output.getvalue().encode('utf-8-sig'))
    if preview['errors']:
        raise BusinessError('该商品没有可导入的名称、明确重量或配料资料。')
    return preview


def snapshot_bytes(product: dict[str, Any]) -> bytes:
    return json.dumps({'provider': ATTRIBUTION, 'product': product}, ensure_ascii=False,
                      sort_keys=True, separators=(',', ':')).encode('utf-8')


def snapshot_id(product: dict[str, Any]) -> str:
    return hashlib.sha256(snapshot_bytes(product)).hexdigest()


def import_product(repo: Repository, product: dict[str, Any], sku: str, version: str) -> dict[str, Any]:
    preview = candidate_preview(product, sku, version)
    if any(row['error'] for row in preview['rows']):
        raise BusinessError('候选存在格式问题，请检查SKU、版本或来源字段后再导入。')
    folder = repo.settings.runtime_dir / 'sources'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'off-{snapshot_id(product)}.json'
    try:
        with path.open('xb') as file:
            file.write(snapshot_bytes(product))
    except FileExistsError:
        if path.read_bytes() != snapshot_bytes(product):
            raise BusinessError('来源快照校验失败，已停止导入。')
    return commit_import(repo, preview, f'OpenFoodFacts-{product["code"]}.csv')
