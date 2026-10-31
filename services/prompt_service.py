"""Prompts are immutable, versioned artifacts validated against a manifest."""
import hashlib
import json
from config import ROOT

PROMPT_VERSION = 'qianpin-v2'


def load_prompt(version: str = PROMPT_VERSION) -> str:
    manifest = json.loads((ROOT / 'prompts/manifest.json').read_text(encoding='utf-8'))
    if version not in manifest:
        raise ValueError('未知提示词版本，请检查配置。')
    path = ROOT / 'prompts' / f'{version}.txt'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest[version]:
        raise ValueError('提示词校验失败。请恢复原文件，修改内容时应创建新版本。')
    return data.decode('utf-8')
