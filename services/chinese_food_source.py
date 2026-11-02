"""Bounded, read-only Chinese Wikipedia lookup for local food discovery."""
import json
from typing import Any
from urllib.parse import quote, urlparse

import requests

from repository import BusinessError


API_URL = 'https://zh.wikipedia.org/w/api.php'
USER_AGENT = 'QianpinZhiying/1.0 (https://github.com/workyy-SVG/OPAshuqian)'


def _safe_image(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        if (parsed.scheme == 'https' and parsed.hostname == 'upload.wikimedia.org'
                and not parsed.username and not parsed.password and parsed.port in (None, 443)):
            return value
    except ValueError:
        pass
    return None


def search_food(name: str, limit: int = 3) -> list[dict[str, str]]:
    term = name.strip()
    if not 1 <= len(term) <= 60 or isinstance(limit, bool) or not 1 <= limit <= 5:
        raise BusinessError('中文食品查询内容或数量无效。', 'chinese_food_input')
    params = {
        'action': 'query', 'generator': 'search', 'gsrsearch': term + ' 食品',
        'gsrnamespace': '0', 'gsrlimit': str(limit), 'prop': 'extracts|pageimages',
        'exintro': '1', 'explaintext': '1', 'exsentences': '3',
        'piprop': 'thumbnail', 'pithumbsize': '360', 'redirects': '1',
        'format': 'json', 'formatversion': '2',
    }
    try:
        with requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT},
                          timeout=(4, 10), stream=True, allow_redirects=False) as response:
            if response.status_code == 429:
                raise BusinessError('中文资料查询较频繁，请稍后再试。', 'chinese_food_rate_limit')
            if response.status_code != 200:
                raise BusinessError(f'中文资料接口暂时不可用（HTTP {response.status_code}）。',
                                    'chinese_food_unavailable')
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    raise BusinessError('中文资料接口响应过大，已停止读取。', 'chinese_food_response')
            data = json.loads(body)
    except BusinessError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise BusinessError('中文资料查询失败或超时，请稍后重试。', 'chinese_food_network') from exc
    pages = data.get('query', {}).get('pages', []) if isinstance(data, dict) else []
    if not isinstance(pages, list):
        raise BusinessError('中文资料接口返回格式异常。', 'chinese_food_response')
    results = []
    for page in pages[:limit]:
        if not isinstance(page, dict) or not isinstance(page.get('title'), str):
            continue
        title = page['title'].strip()
        if not title:
            continue
        raw_extract = page.get('extract')
        extract = raw_extract if isinstance(raw_extract, str) else ''
        raw_thumbnail = page.get('thumbnail')
        thumbnail = raw_thumbnail if isinstance(raw_thumbnail, dict) else {}
        results.append({'title': title, 'extract': extract.strip(),
                        'url': 'https://zh.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                        'image': _safe_image(thumbnail.get('source')) or ''})
    return results
