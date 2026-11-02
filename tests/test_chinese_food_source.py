import json

import pytest
import requests

from repository import BusinessError
from services import chinese_food_source as source


class Response:
    def __init__(self, payload=None, status=200):
        self.status_code = status
        self.body = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.body


def test_search_returns_bounded_chinese_pages(monkeypatch):
    payload = {'query': {'pages': [
        {'title': '酸汤鱼', 'extract': '贵州地方菜。',
         'thumbnail': {'source': 'https://upload.wikimedia.org/example.jpg'}},
        {'title': '其他结果', 'extract': ''},
    ]}}
    calls = []
    monkeypatch.setattr(source.requests, 'get', lambda *a, **kw: calls.append((a, kw)) or Response(payload))
    results = source.search_food('酸汤鱼')
    assert results[0]['title'] == '酸汤鱼'
    assert results[0]['url'].startswith('https://zh.wikipedia.org/wiki/')
    assert results[0]['image'].startswith('https://upload.wikimedia.org/')
    assert calls[0][1]['allow_redirects'] is False
    assert calls[0][1]['params']['gsrsearch'] == '酸汤鱼 食品'


def test_search_rejects_bad_transport_and_untrusted_images(monkeypatch):
    payload = {'query': {'pages': [{'title': '刺梨', 'thumbnail': {'source': 'https://evil.example/a.jpg'}}]}}
    monkeypatch.setattr(source.requests, 'get', lambda *a, **kw: Response(payload))
    assert source.search_food('刺梨')[0]['image'] == ''
    monkeypatch.setattr(source.requests, 'get', lambda *a, **kw: Response(status=503))
    with pytest.raises(BusinessError, match='暂时不可用'):
        source.search_food('刺梨')
    monkeypatch.setattr(source.requests, 'get', lambda *a, **kw: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(BusinessError, match='失败或超时'):
        source.search_food('刺梨')


@pytest.mark.parametrize('name,limit', [('', 3), ('x' * 61, 3), ('刺梨', 0), ('刺梨', 6)])
def test_search_validates_input(name, limit):
    with pytest.raises(BusinessError):
        source.search_food(name, limit)
