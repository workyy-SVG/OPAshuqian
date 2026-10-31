"""DeepSeek adapter. Error records contain codes, never response bodies or keys."""
import json
import re
import time
from decimal import Decimal
import requests
from config import ModelConfig, QwenConfig
from repository import BusinessError
from services.text_check_service import text_issues
from services.prompt_service import PROMPT_VERSION, load_prompt
from services.retry_service import RetryPolicy


class ModelError(BusinessError):
    def __init__(self, message, code, attempts=1):
        super().__init__(message, code)
        self.attempts = attempts


def validate_result(result, snapshot):
    if not isinstance(result, dict):
        raise ModelError("模型结果必须为 JSON 对象。", "invalid_json")
    for key in ("title", "body"):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ModelError("模型返回的标题或正文为空。", "empty_content")
        if len(result[key]) > (200 if key == "title" else 10000):
            raise ModelError("模型返回的内容过长。", "invalid_content")
    ids = result.get("used_fact_ids")
    valid_ids = {f["fact_revision_id"] for f in snapshot["facts"]}
    if not isinstance(ids, list) or any(type(i) is not int or i not in valid_ids for i in ids):
        raise ModelError("模型引用了输入快照以外的依据。", "invalid_fact_ids")
    missing = result.get("missing_fields")
    if not isinstance(missing, list) or any(not isinstance(v, str) for v in missing):
        raise ModelError("模型缺失字段格式错误。", "invalid_missing_fields")
    if missing:
        raise ModelError("模型报告资料不足，请核对资料后重新生成。", "missing_fields")
    issues = text_issues(result['title'], result['body'], snapshot)
    if issues:
        raise ModelError('；'.join(issues), 'fact_mismatch')
    return result


class CompatibleModelClient:
    provider = "模型"
    allowed_endpoint = ""

    def __init__(self, config, post=None, sleep=None, policy=None):
        self.config = config
        self.post = post or requests.post
        self.sleep = sleep or time.sleep
        try:
            self.policy = policy or RetryPolicy.from_env()
        except ValueError as exc:
            raise ModelError('重试配置无效，请检查本机参数。', 'invalid_retry_config', 0) from exc

    def extra_payload(self):
        return {}

    def generate_json(self, snapshot, prompt_version=PROMPT_VERSION):
        if not self.config.api_key:
            raise ModelError(f"尚未配置{self.provider}密钥，请在本机配置后重试。", "missing_api_key", 0)
        if self.config.endpoint != self.allowed_endpoint:
            raise ModelError(f"仅支持{self.provider}官方 HTTPS 接口。", "invalid_endpoint", 0)
        try:
            system = load_prompt(prompt_version)
        except ValueError as exc:
            raise ModelError(str(exc), 'invalid_prompt', 0) from exc
        payload = {"model": self.config.name, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"prompt_version": prompt_version, "confirmed_snapshot": snapshot}, ensure_ascii=False)}],
            "response_format": {"type": "json_object"}, "max_tokens": 1000, "stream": False}
        payload.update(self.extra_payload())
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                response = self.post(self.config.endpoint, headers={"Authorization": "Bearer " + self.config.api_key},
                                     json=payload, timeout=(10, 45))
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < self.policy.max_attempts:
                    self.sleep(self.policy.delay(attempt))
                    continue
                raise ModelError("接口连接或读取超时，请检查网络后手动重试。", "network_timeout", attempt) from exc
            status = response.status_code
            if status == 429 or status in (500, 502, 503, 504):
                if attempt < self.policy.max_attempts:
                    retry_after = getattr(response, 'headers', {}).get('Retry-After') if status == 429 else None
                    delay = self.policy.delay(attempt, retry_after)
                    if delay is not None:
                        self.sleep(delay)
                        continue
            if status != 200:
                messages = {401: "密钥无效，请检查本机配置。", 402: "API 余额不足，请在控制台处理。",
                            429: "接口限流，已停止重试，请稍后再试。", 400: "接口参数错误，请检查模型配置。",
                            422: "接口参数不受支持，请检查模型配置。"}
                raise ModelError(messages.get(status, "模型服务失败，请稍后手动重试。"), f"http_{status}", attempt)
            try:
                data = response.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise ModelError("模型输出未正常结束，未保存为成功。", "truncated", attempt)
                raw = choice["message"]["content"]
                if not isinstance(raw, str) or not raw.strip():
                    raise ModelError("模型返回空白内容。", "empty_content", attempt)
                parsed = json.loads(raw)
                result = validate_result(parsed, snapshot)
            except ModelError as exc:
                exc.attempts = attempt
                raise
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ModelError("模型响应无法按约定 JSON 读取。", "invalid_json", attempt) from exc
            usage = data.get("usage", {})
            safe_usage = {k: v for k, v in usage.items() if k in ("prompt_tokens", "completion_tokens", "total_tokens") and type(v) is int} if isinstance(usage, dict) else {}
            return {"result": result, "attempts": attempt, "usage": safe_usage}


class DeepSeekClient(CompatibleModelClient):
    provider = "DeepSeek"
    allowed_endpoint = "https://api.deepseek.com/chat/completions"

    def __init__(self, config: ModelConfig, post=None, sleep=None, policy=None):
        super().__init__(config, post, sleep, policy)

    def extra_payload(self):
        return {"thinking": {"type": "disabled"}}


class QwenClient(CompatibleModelClient):
    provider = "通义千问"
    allowed_endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def __init__(self, config: QwenConfig, post=None, sleep=None, policy=None):
        super().__init__(config, post, sleep, policy)

    def extra_payload(self):
        return {"enable_thinking": False}
