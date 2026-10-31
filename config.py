"""All runtime paths are absolute; secrets never live in source control."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRAND_CODE = "DEMO"
BRAND_NAME = "黔味小铺（拟制演示品牌）"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
FIELDS = {
    "product_name": "产品名称", "net_weight_g": "净含量（克）",
    "price_cent": "价格", "ingredients_text": "配料原文",
    "usage_text": "使用方法", "storage_text": "储存说明",
}
CONTENT_TYPES = {"product_intro": "商品介绍", "social_post": "朋友圈文案"}


@dataclass(frozen=True)
class Settings:
    runtime_dir: Path
    db_path: Path

    @classmethod
    def from_env(cls):
        runtime = Path(os.environ.get("QIANPIN_RUNTIME_DIR", ROOT / "runtime")).resolve()
        return cls(runtime, Path(os.environ.get("QIANPIN_DB_PATH", runtime / "qianpin.sqlite3")).resolve())


@dataclass(frozen=True)
class ModelConfig:
    api_key: str = ""
    endpoint: str = "https://api.deepseek.com/chat/completions"
    name: str = "deepseek-flash"


@dataclass(frozen=True)
class QwenConfig:
    api_key: str = ""
    endpoint: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    name: str = "qwen-plus"
