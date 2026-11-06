"""Validation and persistence of the settings form. No UI toolkit here."""
from __future__ import annotations

import config
from llm_client import validate_endpoint
from llm_store import LlmStore
from ui_utils import UserError

_MODIFIERS = {"ctrl", "alt", "shift", "windows"}
MIN_PASSPHRASE = 8


def _checked_passphrase(form: dict) -> str:
    passphrase = str(form.get("sync_passphrase", ""))
    if len(passphrase) < MIN_PASSPHRASE:
        raise UserError(f"使用 WebDAV 需要设置至少 {MIN_PASSPHRASE} 位的同步口令。")
    return passphrase


def load_form() -> dict:
    s = config.load_all()
    llm = config.get_llm()
    wd = config.get_webdav()
    prices = config.get_llm_prices()
    models = sorted({llm["model"], *prices, *LlmStore().models()})
    return {
        "image_provider": config.get_provider("image"),
        "pdf_provider": config.get_provider("pdf"),
        "app_id": s.get("app_id", ""),
        "app_key": s.get("app_key", ""),
        "llm_api_key": llm["api_key"],
        "llm_model": llm["model"],
        "llm_base_url": llm["base_url"],
        "llm_prices": [{"model": m, **prices.get(m, {})} for m in models],
        "hotkey": config.keyboard_to_qt(config.get_hotkey()),
        "default_hotkey": config.keyboard_to_qt(config.DEFAULT_HOTKEY),
        "cache_retention_days": config.get_cache_retention(),
        "image_price_usd": config.get_image_price(),
        "pdf_price_usd": config.get_pdf_price(),
        "default_image_price": config.DEFAULT_IMAGE_PRICE,
        "default_pdf_price": config.DEFAULT_PDF_PRICE,
        "usd_cny_rate": config.get_usd_cny_rate(),
        "webdav_url": wd["url"],
        "webdav_user": wd["user"],
        "webdav_password": wd["password"],
        "sync_passphrase": wd["passphrase"],
        "plaintext_left": s.get("ui_state", {}).get("remote_plaintext_left") or [],
        "webdav_path": wd["path"],
        "webdav_sync_interval": wd["interval"],
        "last_synced_at": config.get_last_synced(),
    }


def _number(form: dict, key: str, label: str, low: float, high: float) -> float:
    try:
        value = float(str(form.get(key, "")).strip().lstrip("$"))
    except ValueError:
        raise UserError(f"{label}需要填写数字。") from None
    if not low <= value <= high:
        raise UserError(f"{label}应在 {low:g} 到 {high:g} 之间。")
    return value


def _llm_prices(rows: list) -> dict:
    prices = {}
    for row in rows or []:
        model = str(row.get("model", "")).strip()
        values = [str(row.get(k, "")).strip() for k in ("input", "cached", "output")]
        if not model or not any(values):
            continue   # all blank: this model stays unpriced
        if not all(values):
            raise UserError(f"{model} 的单价要填写完整，或全部留空。")
        try:
            numbers = [float(v) for v in values]
        except ValueError:
            raise UserError(f"{model} 的单价需要填写数字。") from None
        if any(not 0 <= n < 1_000_000 for n in numbers):
            raise UserError(f"{model} 的单价超出范围。")
        prices[model] = dict(zip(("input", "cached", "output"), numbers))
    return prices


def validate_hotkey(pretty: str) -> str:
    """Return the keyboard-library form, refusing keys that would trap typing."""
    hotkey = config.qt_to_keyboard(pretty) or config.DEFAULT_HOTKEY
    parts = hotkey.split("+")
    last = parts[-1]
    if not any(p in _MODIFIERS for p in parts[:-1]) and not (
            last.startswith("f") and last[1:].isdigit()):
        raise UserError(f"快捷键 {config.keyboard_to_qt(hotkey)} 没有修饰键，会拦截普通输入。"
                        "请加上 Ctrl、Alt 或 Shift。")
    return hotkey


def save_form(form: dict) -> tuple[str, str]:
    """Persist the form; returns (old_hotkey, new_hotkey)."""
    app_id = str(form.get("app_id", "")).strip()
    app_key = str(form.get("app_key", "")).strip()
    llm_key = str(form.get("llm_api_key", "")).strip()
    llm_model = str(form.get("llm_model", "")).strip()
    providers = (form.get("image_provider"), form.get("pdf_provider"))
    if any(p not in ("mathpix", "llm") for p in providers):
        raise UserError("识别服务无效。")
    if "mathpix" in providers and (not app_id or not app_key):
        raise UserError("App ID 和 App Key 都不能为空。")
    if "llm" in providers and (not llm_key or not llm_model):
        raise UserError("请填写大模型 API Key 和模型名称。")
    try:
        llm_url = validate_endpoint(str(form.get("llm_base_url", "")))
    except ValueError as exc:
        raise UserError(str(exc)) from None
    old_hotkey = config.get_hotkey()
    new_hotkey = validate_hotkey(str(form.get("hotkey", "")))
    wd_url = str(form.get("webdav_url", "")).strip()
    wd_user = str(form.get("webdav_user", "")).strip()
    if wd_url and not wd_user:
        raise UserError("填写 WebDAV URL 后必须同时提供用户名。")
    passphrase = _checked_passphrase(form) if wd_url else str(form.get("sync_passphrase", ""))
    values = {
        "image_provider": providers[0],
        "pdf_provider": providers[1],
        "app_id": app_id,
        "app_key": app_key,
        "llm_api_key": llm_key,
        "llm_model": llm_model or config.DEFAULT_LLM_MODEL,
        "llm_base_url": llm_url,
        "llm_prices": _llm_prices(form.get("llm_prices")),
        "image_price_usd": _number(form, "image_price_usd", "截图单价", 0, 1),
        "pdf_price_usd": _number(form, "pdf_price_usd", "PDF 单价", 0, 1),
        "usd_cny_rate": _number(form, "usd_cny_rate", "汇率", .1, 100),
        "hotkey": new_hotkey,
        "webdav_url": wd_url,
        "webdav_user": wd_user,
        "webdav_password": str(form.get("webdav_password", "")),
        "sync_passphrase": passphrase,
        "webdav_path": str(form.get("webdav_path", "")).strip() or config.DEFAULT_WEBDAV_PATH,
        "webdav_sync_interval": int(_number(form, "webdav_sync_interval", "同步间隔", 0, 1440)),
        "cache_retention_days": int(_number(form, "cache_retention_days", "保留天数", 0, 3650)),
    }
    try:
        # Deprecated bool field from older configs.
        config.save_settings(values, drop=("webdav_auto_sync",))
    except Exception as exc:
        raise UserError(f"无法写入配置：{exc}") from None
    return old_hotkey, new_hotkey


def webdav_from_form(form: dict) -> dict:
    """Connection values from the unsaved form, so "sync now" can try them
    without persisting anything."""
    url = str(form.get("webdav_url", "")).strip()
    user = str(form.get("webdav_user", "")).strip()
    if not url or not user:
        raise UserError("请先填写 WebDAV URL 和用户名。")
    return {"url": url, "user": user, "password": str(form.get("webdav_password", "")),
            "passphrase": _checked_passphrase(form),
            "path": str(form.get("webdav_path", "")).strip() or config.DEFAULT_WEBDAV_PATH,
            "interval": 0}
