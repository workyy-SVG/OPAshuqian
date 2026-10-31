"""Optional live API smoke check. Not imported or run by pytest."""
import json
import os
import tomllib
from config import ROOT, ModelConfig
from repository import Repository, BusinessError
from services.content_service import generate_content

if __name__ == "__main__":
    import argparse
    import uuid
    from services.llm_client import DeepSeekClient
    parser = argparse.ArgumentParser(description="执行一次真实 DeepSeek 调用，会使用账号 API 额度。")
    parser.add_argument("product_id", type=int)
    parser.add_argument("--channel", default="retail")
    parser.add_argument("--confirm-live", action="store_true", required=True)
    args = parser.parse_args()
    config_path = ROOT / ".streamlit" / "secrets.toml"
    values = tomllib.loads(config_path.read_text(encoding="utf-8")).get("model", {}) if config_path.is_file() else {}
    cfg = ModelConfig(api_key=os.environ.get("DEEPSEEK_API_KEY", values.get("api_key", "")),
                      endpoint=values.get("endpoint", ModelConfig().endpoint), name=values.get("name", ModelConfig().name))
    if not cfg.api_key:
        raise SystemExit("尚未配置密钥。请在本机配置，勿粘贴到仓库或终端命令中。")
    repo = Repository()
    repo.initialize()
    result = generate_content(repo, args.product_id, uuid.uuid4().hex, args.channel, mode="deepseek", client=DeepSeekClient(cfg))
    print(json.dumps(result, ensure_ascii=False))
