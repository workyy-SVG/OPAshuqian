"""Read-only Open Food Facts integration; reuse the audited candidate import path."""
import csv
import hashlib
import io
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from collections import deque
from typing import Any

import requests

from repository import BusinessError, Repository
from services.import_service import COLUMNS, preview_import, commit_import
from services.unit_service import normalize_weight
from services.food_catalog_cache import read_snapshot, write_snapshot

BASE = 'https://world.openfoodfacts.org'
USER_AGENT = 'QianpinZhiying/1.0 (https://github.com/workyy-SVG/OPAshuqian)'
ATTRIBUTION = 'Open Food Facts · ODbL / Database Contents License'
FIELDS = 'code,product_name,product_name_zh,brands,quantity,ingredients_text,ingredients_text_zh,nutriments,last_modified_t,image_front_url,image_front_small_url,categories_tags'
_lock = threading.Lock()
_calls: dict[str, deque[float]] = {'barcode': deque(), 'name': deque()}


class FoodSourceError(BusinessError):
    def __init__(self, message: str, code: str, status_code: int | None = None):
        super().__init__(message, code)
        self.retryable = status_code in (500, 502, 503, 504) or code == 'food_network'


def product_image_urls(product: dict[str, Any]) -> list[str]:
    """Require the OFF host AND an image directory belonging to this barcode."""
    code = str(product.get('code', ''))
    if not re.fullmatch(r'[0-9]{8,14}', code):
        return []
    urls = []
    for field in ('image_front_url', 'image_front_small_url'):
        value = product.get(field)
        if not isinstance(value, str):
            continue
        try:
            parsed = urlparse(value)
            if (parsed.scheme == 'https' and parsed.hostname == 'images.openfoodfacts.org'
                    and not parsed.username and not parsed.password and parsed.port in (None, 443)
                    and parsed.path.startswith('/images/products/')):
                directories = parsed.path.removeprefix('/images/products/').split('/')[:-1]
                if (directories and all(re.fullmatch(r'[0-9]+', p) for p in directories)
                        and ''.join(directories).lstrip('0') == code.lstrip('0')):
                    if value not in urls:
                        urls.append(value)
        except ValueError:
            continue
    return urls


def product_image_url(product: dict[str, Any]) -> str | None:
    urls = product_image_urls(product)
    return urls[0] if urls else None


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
    data = _request(url, params)
    products = [data.get('product')] if kind == 'barcode' else data.get('products', [])
    return _products(products, 5)


def _request(url: str, params: dict[str, str]) -> dict[str, Any]:
    try:
        with requests.get(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=(5, 15),
                          stream=True, allow_redirects=False) as response:
            if response.status_code == 404:
                return {}
            if response.status_code == 429:
                raise BusinessError('数据源查询限流，请稍后再试或使用CSV演示。', 'food_rate_limit')
            if response.status_code != 200:
                raise FoodSourceError(f'数据源暂时不可用（HTTP {response.status_code}），请稍后再试或使用CSV演示。', 'food_unavailable', response.status_code)
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise BusinessError('数据源响应过大，已停止读取。', 'food_response')
            data = json.loads(body)
    except BusinessError:
        raise
    except requests.exceptions.ProxyError as exc:
        raise BusinessError('部署环境代理无法连接数据源，请检查网络访问配置。', 'food_proxy') from exc
    except (requests.RequestException, ValueError) as exc:
        raise FoodSourceError('查询失败或超时，请稍后重试；CSV导入仍可使用。', 'food_network') from exc
    if not isinstance(data, dict):
        raise BusinessError('数据源返回格式异常。', 'food_response')
    return data


def _products(products: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(products, list):
        raise BusinessError('数据源返回格式异常。', 'food_response')
    return [p for p in products[:limit] if isinstance(p, dict) and re.fullmatch(r'[0-9]{8,14}', str(p.get('code', '')))]


CATEGORIES = {
    '熟食': {'即食餐食':'en:prepared-meals'},
    '水饮': {'饮用水':'en:waters', '果汁':'en:fruit-juices', '茶饮料':'en:iced-teas',
             '碳酸饮料':'en:sodas', '饮料与饮用水':'en:beverages'},
    '生鲜': {'果蔬':'en:fruits-and-vegetables','肉类':'en:meats','蛋类':'en:eggs','水产':'en:seafood'},
    '零食': {'休闲零食':'en:snacks'},
    '乳品': {'乳制品':'en:dairies', '牛奶':'en:milks', '酸奶':'en:yogurts', '奶酪':'en:cheeses'},
    '调味品': {'酱料与调味':'en:condiments'},
}
PAGE_SIZE = 12


def browse(category: str, subcategory: str, page: int = 1, cache_dir: Path | None = None) -> dict[str, Any]:
    if category not in CATEGORIES or subcategory not in CATEGORIES[category]:
        raise BusinessError('请选择目录中的分类。')
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000:
        raise BusinessError('目录页码须在1至1000之间，请缩小分类范围。')
    tag = CATEGORIES[category][subcategory]
    cached = read_snapshot(cache_dir, tag, page)
    if cached and not cached['stale']:
        return cached
    params = {'categories_tags':tag, 'no_count':'1', 'sort_by':'nothing',
              'page_size':str(PAGE_SIZE),'page':str(page),'fields':FIELDS}
    try:
        for attempt in range(2):
            _reserve('name')
            try:
                data = _request(f'{BASE}/api/v2/search', params)
                break
            except FoodSourceError as exc:
                if not exc.retryable or attempt == 1:
                    raise
                time.sleep(0.5)
    except BusinessError as exc:
        transient = (isinstance(exc, FoodSourceError) and exc.retryable) or exc.code == 'food_rate_limit'
        if cached and transient:
            return {**cached, 'source_error': str(exc)}
        raise
    raw = data.get('products', [])
    products = _products(raw, PAGE_SIZE)
    # With no_count, the API may return this page's length as count, not a total.
    result = {'products':products, 'page':page, 'total':None, 'has_next':len(raw)>=PAGE_SIZE,
              'saved_at':time.time(), 'cached':False, 'stale':False}
    write_snapshot(cache_dir, tag, result)
    return result


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
