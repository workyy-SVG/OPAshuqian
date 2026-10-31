import sqlite3
from decimal import Decimal
import streamlit as st
from config import FIELDS, ModelConfig, QwenConfig
from repository import BusinessError
from services import query_service as queries

STATES = {"pending": "待确认", "adopted": "已采纳", "excluded": "已排除", "duplicate": "重复证据",
          "error": "格式错误", "current": "当前确认", "superseded": "已替代", "withdrawn": "已撤回",
          "draft": "草稿", "review": "待审核", "ready": "可导出", "stale": "待复查", "archived": "历史归档"}


def display_value(field, value):
    if value is None:
        return "已撤回 / 无当前值"
    if field == "price_cent":
        return f"{Decimal(value) / 100:.2f} 元"
    if field == "net_weight_g":
        return value + " 克"
    return value


def display_context(value):
    return {'general': '通用资料', 'retail': '零售', 'wholesale': '批发'}.get(value, value)


def available_channels(repo, product_id):
    return queries.channels(repo, product_id)


def action(callback, success="操作已保存。"):
    try:
        result = callback()
    except BusinessError as exc:
        st.error(str(exc))
        return False, None
    except sqlite3.OperationalError:
        st.error("数据库暂时不可写，请关闭数据库查看器的编辑事务，稍后重试。")
        return False, None
    st.session_state["notice"] = success
    from services.bootstrap_service import cached_products
    cached_products.clear()
    return True, result


def model_configs():
    import os
    deepseek_values = {}
    qwen_values = {}
    try:
        # Keep reading [model] so existing local DeepSeek configurations continue to work.
        deepseek_values = dict(st.secrets.get("deepseek", st.secrets.get("model", {})))
        qwen_values = dict(st.secrets.get("qwen", {}))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    deepseek = ModelConfig(api_key=os.environ.get("DEEPSEEK_API_KEY", deepseek_values.get("api_key", "")),
                           endpoint=deepseek_values.get("endpoint", ModelConfig().endpoint),
                           name=deepseek_values.get("name", ModelConfig().name))
    qwen = QwenConfig(api_key=os.environ.get("DASHSCOPE_API_KEY", qwen_values.get("api_key", "")),
                      endpoint=qwen_values.get("endpoint", QwenConfig().endpoint),
                      name=qwen_values.get("name", QwenConfig().name))
    return {"deepseek": deepseek, "qwen": qwen}


def model_config():
    """Compatibility helper for callers that still expect only DeepSeek."""
    return model_configs()["deepseek"]


def fact_table(repo, product_id):
    rows = queries.current_facts(repo, product_id)
    if rows:
        st.dataframe([{"字段": FIELDS.get(r["field"], r["field"]), "范围": display_context(r["context"]),
                       "确认值": display_value(r["field"], r["value"]), "修订编号": r["id"],
                       "来源": r["source_label"], "来源位置": r["source_locator"], "CSV行号": r["row_no"]} for r in rows], hide_index=True, width="stretch")
    else:
        st.info("尚无确认资料。先导入资料，再到数据核对页处理候选。")
    return rows
