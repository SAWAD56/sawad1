import asyncio
import json
import os
import random
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import tgcrypto  # type: ignore  # noqa: F401
    TGCRYPTO_INSTALLED = True
except ImportError:
    TGCRYPTO_INSTALLED = False

try:
    MAIN_LOOP = asyncio.get_event_loop()
except RuntimeError:
    MAIN_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(MAIN_LOOP)

from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram import utils as pyrogram_utils
from pyrogram.handlers import MessageHandler
from pyrogram.errors import (
    ChatWriteForbidden,
    FloodWait,
    PasswordHashInvalid,
    PeerIdInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
    UserNotParticipant,
)
from pyrogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton as Button,
    InlineKeyboardMarkup as Markup,
    Message,
)
from pyrolistener import Listener, exceptions
from pyrolistener import listener as listener_module
from pytz import timezone

pyrogram_utils.MIN_CHANNEL_ID = -1009999999999

API_ID = 20769091
API_HASH = "0a3c7b2d7c8132bbafd4ffe9eb516968"
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 1411672636
OWNERS = [OWNER_ID]
SESSION_TITLE = "نشر تلقائي"
DEVELOPER_USERNAME = "rrry_r"
DEVELOPER_URL = f"https://t.me/{DEVELOPER_USERNAME}"
MANDATORY_BOT_CHANNEL = "EP_HP"
MANDATORY_ACCOUNT_CHANNEL = "EP_HP"
CLIENT_PROFILE = {
    "app_version": SESSION_TITLE,
    "device_model": SESSION_TITLE,
    "lang_code": "ar",
}
TZ = timezone("Asia/Baghdad")
GROUPS_PAGE_SIZE = 8
TEMPLATES_PAGE_SIZE = 6
MIN_DELAY = 5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DB = os.path.join(BASE_DIR, "users.json")
CHANNELS_DB = os.path.join(BASE_DIR, "channels.json")
ADMINS_DB = os.path.join(BASE_DIR, "admins.json")
BOT_SESSION = os.path.join(BASE_DIR, "autoPost_bot")
STATUS_DB = os.path.join(BASE_DIR, "bot_status.json")

DEFAULT_POSTING_SETTINGS = {
    "mode": "safe",
    "random_order": True,
    "random_delay_min": 0,
    "random_delay_max": 10,
    "retry_attempts": 3,
    "retry_delay": 3,
    "skip_failed": True,
}
DEFAULT_STATS = {
    "session": {"success": 0, "failed": 0, "messages": 0, "runs": 0},
    "total": {"success": 0, "failed": 0, "messages": 0, "runs": 0},
    "last_run": {},
}
ANTI_BAN_DELAYS = {
    "normal": (0.2, 0.8),
    "safe": (1.0, 2.0),
    "hidden": (2.0, 4.0),
}
MAX_USER_LOGS = 200

app = Client(BOT_SESSION, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, **CLIENT_PROFILE)
listener = Listener(client=app)
posting_tasks: Dict[str, asyncio.Task] = {}
ai_workers: Dict[str, asyncio.Task] = {}
ACCOUNT_COMPAT_FIELDS = (
    "session",
    "account_number",
    "groups",
    "available_groups",
    "last_groups_sync",
    "posting",
    "ai",
)


def now_local() -> datetime:
    return datetime.now(TZ)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        write_json(path, default)
        return default
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        write_json(path, default)
        return default


def set_bot_status(state: str, details: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {
        "state": state,
        "updated_at": now_local().isoformat(),
    }
    if details:
        payload.update(details)
    write_json(STATUS_DB, payload)


users = read_json(USERS_DB, {})
channels = read_json(CHANNELS_DB, [])
admins = read_json(ADMINS_DB, [])

if not isinstance(users, dict):
    users = {}
if not isinstance(channels, list):
    channels = []
if not isinstance(admins, list):
    admins = []
admins = [int(item) for item in admins if str(item).isdigit() and int(item) != OWNER_ID]


def user_defaults(user_id: Optional[int] = None) -> Dict[str, Any]:
    return {
        "vip": bool(user_id == OWNER_ID),
        "vip_until": None,
        "limitation": {},
        "accounts": {"acc1": account_defaults(1)},
        "active_account_id": "acc1",
        "next_account_index": 2,
        "session": "",
        "account_number": "",
        "groups": [],
        "available_groups": [],
        "last_groups_sync": None,
        "templates": [],
        "default_delay": 60,
        "posting_settings": deepcopy(DEFAULT_POSTING_SETTINGS),
        "stats": deepcopy(DEFAULT_STATS),
        "logs": [],
        "trial_used": False,
        "posting": False,
        "ai": {
            "enabled": False,
            "reply": "- تم استلام المنشن أو الرد.",
            "target_username": "",
        },
    }


def account_defaults(index: int = 1) -> Dict[str, Any]:
    return {
        "label": f"الحساب {index}",
        "session": "",
        "account_number": "",
        "groups": [],
        "available_groups": [],
        "last_groups_sync": None,
        "posting": False,
        "ai": {
            "enabled": False,
            "reply": "- تم استلام المنشن أو الرد.",
            "target_username": "",
        },
    }


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    for parser in (
        lambda text: datetime.fromisoformat(text),
        lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M"),
    ):
        try:
            result = parser(value)
            if result.tzinfo is None:
                result = TZ.localize(result)
            return result.astimezone(TZ)
        except ValueError:
            continue
    return None


def normalize_channel(value: str) -> Optional[str]:
    channel = value.strip().replace("@", "")
    if channel.startswith("https://t.me/") or channel.startswith("http://t.me/"):
        channel = channel.split("t.me/", 1)[1]
    elif channel.startswith("t.me/"):
        channel = channel.split("t.me/", 1)[1]
    channel = channel.strip("/")
    if not channel or "/" in channel or " " in channel:
        return None
    return channel


def normalize_target(target: Any) -> Optional[Union[int, str]]:
    if isinstance(target, int):
        return target
    if not isinstance(target, str):
        return None
    value = target.strip()
    if not value:
        return None
    if value.startswith("https://t.me/") or value.startswith("http://t.me/"):
        value = value.split("t.me/", 1)[1]
    elif value.startswith("t.me/"):
        value = value.split("t.me/", 1)[1]
    value = value.strip("/")
    if "/" in value:
        value = value.split("/", 1)[0]
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def dedupe(values: List[Any]) -> List[Any]:
    result: List[Any] = []
    seen = set()
    for value in values:
        key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def account_sort_key(account_id: str) -> Tuple[int, str]:
    suffix = account_id[3:] if account_id.startswith("acc") else account_id
    return (int(suffix), account_id) if suffix.isdigit() else (10**9, account_id)


def account_display_name(account: Dict[str, Any]) -> str:
    return str(account.get("account_number") or account.get("label") or "حساب غير مسجل")


def ensure_account_payload(account: Any, index: int) -> Dict[str, Any]:
    payload = account if isinstance(account, dict) else {}
    default = account_defaults(index)

    for key, value in default.items():
        if key not in payload:
            payload[key] = deepcopy(value)

    if not isinstance(payload.get("label"), str) or not payload["label"].strip():
        payload["label"] = default["label"]
    payload["session"] = str(payload.get("session") or "")
    payload["account_number"] = str(payload.get("account_number") or "")

    if not isinstance(payload.get("groups"), list):
        payload["groups"] = []
    if not isinstance(payload.get("available_groups"), list):
        payload["available_groups"] = []
    payload["groups"] = dedupe([normalize_target(item) for item in payload["groups"] if normalize_target(item) is not None])

    if not isinstance(payload.get("posting"), bool):
        payload["posting"] = bool(payload.get("posting"))

    if not isinstance(payload.get("ai"), dict):
        payload["ai"] = {}
    ai_cfg = payload["ai"]
    if "enabled" not in ai_cfg:
        ai_cfg["enabled"] = False
    if "reply" not in ai_cfg:
        ai_cfg["reply"] = "- تم استلام المنشن أو الرد."
    if "target_username" not in ai_cfg:
        ai_cfg["target_username"] = ""

    return payload


def ensure_accounts_structure(data: Dict[str, Any]) -> Dict[str, Any]:
    accounts = data.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        legacy = account_defaults(1)
        for key in ACCOUNT_COMPAT_FIELDS:
            if key in data:
                legacy[key] = deepcopy(data.get(key))
        if str(legacy.get("account_number") or "").strip():
            legacy["label"] = str(legacy["account_number"])
        accounts = {"acc1": legacy}
        data["accounts"] = accounts

    normalized: Dict[str, Dict[str, Any]] = {}
    for idx, account_id in enumerate(sorted(accounts.keys(), key=account_sort_key), start=1):
        normalized[account_id] = ensure_account_payload(accounts.get(account_id), idx)
    data["accounts"] = normalized

    active_account_id = str(data.get("active_account_id") or "")
    if active_account_id not in normalized:
        active_account_id = next(iter(normalized.keys()))
    data["active_account_id"] = active_account_id

    if not isinstance(data.get("next_account_index"), int) or data["next_account_index"] < 2:
        max_index = 1
        for account_id in normalized:
            suffix = account_id[3:] if account_id.startswith("acc") else ""
            if suffix.isdigit():
                max_index = max(max_index, int(suffix))
        data["next_account_index"] = max_index + 1

    return normalized


def active_account_id(data: Dict[str, Any]) -> str:
    ensure_accounts_structure(data)
    return str(data["active_account_id"])


def account_data(data: Dict[str, Any], account_id: Optional[str] = None) -> Dict[str, Any]:
    accounts = ensure_accounts_structure(data)
    account_id = account_id or active_account_id(data)
    if account_id not in accounts:
        index = data.get("next_account_index", len(accounts) + 1)
        accounts[account_id] = ensure_account_payload({}, index)
        data["next_account_index"] = max(index + 1, data.get("next_account_index", 2))
    return accounts[account_id]


def expose_active_account(data: Dict[str, Any]) -> Dict[str, Any]:
    active = account_data(data, active_account_id(data))
    for key in ACCOUNT_COMPAT_FIELDS:
        data[key] = active[key]
    return active


def create_account_slot(user_id: Union[int, str]) -> str:
    data = ensure_user(user_id)
    active = account_data(data)
    if not active.get("session") and not active.get("account_number") and not active.get("groups") and not active.get("available_groups"):
        expose_active_account(data)
        return active_account_id(data)

    index = data.get("next_account_index", len(data.get("accounts", {})) + 1)
    account_id = f"acc{index}"
    while account_id in data.get("accounts", {}):
        index += 1
        account_id = f"acc{index}"

    data["accounts"][account_id] = ensure_account_payload({}, index)
    data["next_account_index"] = index + 1
    data["active_account_id"] = account_id
    expose_active_account(data)
    return account_id


def switch_account_slot(user_id: Union[int, str], account_id: str) -> bool:
    data = ensure_user(user_id)
    if account_id not in data.get("accounts", {}):
        return False
    data["active_account_id"] = account_id
    expose_active_account(data)
    return True


def delete_account_slot(user_id: Union[int, str], account_id: Optional[str] = None) -> str:
    data = ensure_user(user_id)
    account_id = account_id or active_account_id(data)
    accounts = data.get("accounts", {})
    if account_id not in accounts:
        expose_active_account(data)
        return active_account_id(data)

    if len(accounts) <= 1:
        accounts[account_id] = ensure_account_payload({}, 1)
        data["active_account_id"] = account_id
        expose_active_account(data)
        return account_id

    accounts.pop(account_id, None)
    next_active = next(iter(sorted(accounts.keys(), key=account_sort_key)))
    data["active_account_id"] = next_active
    expose_active_account(data)
    return next_active


def ensure_user(user_id: Union[int, str]) -> Dict[str, Any]:
    user_key = str(user_id)
    if user_key not in users or not isinstance(users[user_key], dict):
        users[user_key] = user_defaults(int(user_key))

    data = users[user_key]
    for key, default in user_defaults(int(user_key)).items():
        if key not in data:
            data[key] = [] if isinstance(default, list) else {} if isinstance(default, dict) else default

    ensure_accounts_structure(data)

    if int(user_key) == OWNER_ID:
        data["vip"] = True

    if not isinstance(data.get("templates"), list):
        data["templates"] = []
    if not isinstance(data.get("limitation"), dict):
        data["limitation"] = {}
    if not isinstance(data.get("default_delay"), int):
        data["default_delay"] = 60
    if not isinstance(data.get("posting_settings"), dict):
        data["posting_settings"] = deepcopy(DEFAULT_POSTING_SETTINGS)
    posting_settings = data["posting_settings"]
    for key, default in DEFAULT_POSTING_SETTINGS.items():
        if key not in posting_settings:
            posting_settings[key] = default
    if posting_settings.get("mode") not in ANTI_BAN_DELAYS:
        posting_settings["mode"] = DEFAULT_POSTING_SETTINGS["mode"]
    for key in ("random_delay_min", "random_delay_max", "retry_attempts", "retry_delay"):
        try:
            posting_settings[key] = int(posting_settings.get(key, DEFAULT_POSTING_SETTINGS[key]))
        except (TypeError, ValueError):
            posting_settings[key] = DEFAULT_POSTING_SETTINGS[key]
    posting_settings["random_delay_min"] = max(0, posting_settings["random_delay_min"])
    posting_settings["random_delay_max"] = max(posting_settings["random_delay_min"], posting_settings["random_delay_max"])
    posting_settings["retry_attempts"] = min(max(1, posting_settings["retry_attempts"]), 3)
    posting_settings["retry_delay"] = max(1, posting_settings["retry_delay"])
    posting_settings["random_order"] = bool(posting_settings.get("random_order", True))
    posting_settings["skip_failed"] = bool(posting_settings.get("skip_failed", True))

    if not isinstance(data.get("stats"), dict):
        data["stats"] = deepcopy(DEFAULT_STATS)
    stats = data["stats"]
    for scope in ("session", "total"):
        if not isinstance(stats.get(scope), dict):
            stats[scope] = {}
        for key in ("success", "failed", "messages", "runs"):
            try:
                stats[scope][key] = int(stats[scope].get(key, 0))
            except (TypeError, ValueError):
                stats[scope][key] = 0
    if not isinstance(stats.get("last_run"), dict):
        stats["last_run"] = {}

    if not isinstance(data.get("logs"), list):
        data["logs"] = []
    if "trial_used" not in data:
        data["trial_used"] = False

    if data.get("vip") and not data.get("vip_until"):
        limitation = data.get("limitation") or {}
        if limitation.get("endDate") and limitation.get("endTime"):
            legacy_until = parse_dt(f"{limitation['endDate']} {limitation['endTime']}")
            if legacy_until:
                data["vip_until"] = legacy_until.isoformat()

    if not data["templates"]:
        legacy_delay = data.get("waitTime") if isinstance(data.get("waitTime"), int) else data.get("default_delay", 60)
        for key in ("caption", "caption2"):
            text = (data.get(key) or "").strip()
            if text:
                data["templates"].append({"text": text, "delay": max(legacy_delay, MIN_DELAY)})

    if data.get("posting2"):
        data["posting"] = True

    for template in data["templates"]:
        if not isinstance(template, dict):
            continue
        if not isinstance(template.get("delay"), int) or template["delay"] < MIN_DELAY:
            template["delay"] = max(data.get("default_delay", 60), MIN_DELAY)
        template["text"] = str(template.get("text") or "")
        template["kind"] = str(template.get("kind") or "text")
        template["file_id"] = str(template.get("file_id") or "")

    expose_active_account(data)
    return data


def save_users() -> None:
    write_json(USERS_DB, users)


def save_channels() -> None:
    write_json(CHANNELS_DB, channels)


def save_admins() -> None:
    write_json(ADMINS_DB, admins)


def ensure_owner() -> None:
    ensure_user(OWNER_ID)
    save_users()
    save_admins()


def required_channels_list() -> List[str]:
    result: List[str] = []
    for raw in [MANDATORY_BOT_CHANNEL, *channels]:
        channel = normalize_channel(str(raw or ""))
        if channel and channel not in result:
            result.append(channel)
    return result


def is_admin_id(user_id: Union[int, str]) -> bool:
    return int(user_id) in admins


def is_vip_manager_id(user_id: Union[int, str]) -> bool:
    return int(user_id) == OWNER_ID or is_admin_id(user_id)


def developer_contact_markup() -> Markup:
    return Markup([[Button("التواصل مع المطور", url=DEVELOPER_URL)]])


def required_subscription_markup(channel: Optional[str] = None, back_to_home: bool = False) -> Markup:
    rows: List[List[Button]] = []
    if channel:
        rows.append([Button(f"الاشتراك في @{channel}", url=f"https://t.me/{channel}")])
    rows.append([Button("التواصل مع المطور", url=DEVELOPER_URL)])
    rows.append([Button("تحقق من الاشتراك", callback_data="verifySubscription")])
    if back_to_home:
        rows.append([Button("- الرئيسية -", callback_data="toHome")])
    return Markup(rows)


def posting_settings_for(user_id: Union[int, str]) -> Dict[str, Any]:
    return ensure_user(user_id)["posting_settings"]


def stats_for(user_id: Union[int, str]) -> Dict[str, Any]:
    return ensure_user(user_id)["stats"]


def append_user_log(user_id: Union[int, str], action: str, account_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
    data = ensure_user(user_id)
    logs = data.get("logs", [])
    entry: Dict[str, Any] = {
        "at": now_local().isoformat(),
        "action": action,
    }
    if account_id:
        entry["account"] = account_display_name(account_data(data, account_id))
    if details:
        entry["details"] = details
    logs.append(entry)
    data["logs"] = logs[-MAX_USER_LOGS:]


def reset_session_stats(user_id: Union[int, str]) -> None:
    stats_for(user_id)["session"] = {"success": 0, "failed": 0, "messages": 0, "runs": 0}


def register_posting_stats(user_id: Union[int, str], account_id: str, success: int, failed: int) -> None:
    stats = stats_for(user_id)
    for scope in ("session", "total"):
        stats[scope]["success"] += success
        stats[scope]["failed"] += failed
        stats[scope]["messages"] += success + failed
    stats["last_run"] = {
        "account": account_display_name(account_data(ensure_user(user_id), account_id)),
        "success": success,
        "failed": failed,
        "at": now_local().isoformat(),
    }


def format_stats_caption(user_id: Union[int, str]) -> str:
    stats = stats_for(user_id)
    session = stats.get("session", {})
    total = stats.get("total", {})
    last_run = stats.get("last_run", {})
    last_text = "لا توجد عملية نشر بعد."
    if last_run:
        last_text = (
            f"- الحساب: {last_run.get('account', 'غير محدد')}\n"
            f"- نجاح: {last_run.get('success', 0)}\n"
            f"- فشل: {last_run.get('failed', 0)}\n"
            f"- الوقت: {format_dt(parse_dt(last_run.get('at')))}"
        )
    return (
        "📊 إحصائيات النشر\n\n"
        "الجلسة الحالية:\n"
        f"- نجاح: {session.get('success', 0)}\n"
        f"- فشل: {session.get('failed', 0)}\n"
        f"- الرسائل: {session.get('messages', 0)}\n"
        f"- مرات التشغيل: {session.get('runs', 0)}\n\n"
        "الإجمالي:\n"
        f"- نجاح: {total.get('success', 0)}\n"
        f"- فشل: {total.get('failed', 0)}\n"
        f"- الرسائل: {total.get('messages', 0)}\n"
        f"- مرات التشغيل: {total.get('runs', 0)}\n\n"
        "آخر تشغيل:\n"
        f"{last_text}"
    )


def template_body(template: Dict[str, Any]) -> str:
    return str(template.get("text") or "")


def template_preview(template: Dict[str, Any]) -> str:
    kind = str(template.get("kind") or "text")
    body = template_body(template).replace("\n", " ").strip()
    if not body:
        labels = {
            "photo": "صورة",
            "video": "فيديو",
            "animation": "GIF",
            "document": "ملف",
        }
        body = f"[{labels.get(kind, 'وسائط')} بدون تعليق]"
    return body


def apply_template_variables(text: str, group_name: str) -> str:
    current = now_local()
    return (
        str(text or "")
        .replace("{time}", current.strftime("%H:%M"))
        .replace("{date}", current.strftime("%Y-%m-%d"))
        .replace("{group}", group_name or "المجموعة")
    )


def mode_label(mode: str) -> str:
    return {
        "normal": "عادي",
        "safe": "آمن",
        "hidden": "خفي",
    }.get(mode, "آمن")


async def missing_subscription_channel(user_id: Union[int, str]) -> Optional[str]:
    for channel in required_channels_list():
        try:
            await app.get_chat_member(f"@{channel}", int(user_id))
        except UserNotParticipant:
            return channel
        except Exception:
            continue
    return None


async def ensure_account_channel_membership(client: Client) -> None:
    try:
        await client.join_chat(f"@{MANDATORY_ACCOUNT_CHANNEL}")
    except Exception:
        pass


def posting_settings_markup(user_id: Union[int, str]) -> Markup:
    settings = posting_settings_for(user_id)
    return Markup(
        [
            [Button(f"- الوضع: {mode_label(settings.get('mode', 'safe'))} -", callback_data="cyclePostingMode")],
            [Button(f"- ترتيب عشوائي: {'نعم' if settings.get('random_order') else 'لا'} -", callback_data="toggleRandomOrder")],
            [Button(f"- تأخير عشوائي: {settings.get('random_delay_min', 0)}-{settings.get('random_delay_max', 0)} ث -", callback_data="setRandomDelay")],
            [Button(f"- إعادة المحاولة: {settings.get('retry_attempts', 3)} -", callback_data="setRetryAttempts"), Button(f"- تخطي الفاشل: {'نعم' if settings.get('skip_failed') else 'لا'} -", callback_data="toggleSkipFailed")],
            [Button("- إحصائيات النشر -", callback_data="postingStats"), Button("- السجل الأخير -", callback_data="postingLogs")],
            [Button("- رجوع -", callback_data="toHome")],
        ]
    )


def template_text_from_message(message: Message) -> str:
    if message.text is not None:
        return str(getattr(message.text, "html", message.text) or "")
    if message.caption is not None:
        return str(getattr(message.caption, "html", message.caption) or "")
    return ""


def build_template_payload(message: Message, delay: int) -> Dict[str, Any]:
    payload = {
        "kind": "text",
        "text": template_text_from_message(message),
        "file_id": "",
        "delay": delay,
    }
    if message.photo:
        payload["kind"] = "photo"
        payload["file_id"] = message.photo.file_id
    elif message.video:
        payload["kind"] = "video"
        payload["file_id"] = message.video.file_id
    elif message.animation:
        payload["kind"] = "animation"
        payload["file_id"] = message.animation.file_id
    elif message.document:
        payload["kind"] = "document"
        payload["file_id"] = message.document.file_id
    return payload


def group_title_for(account: Dict[str, Any], group: Union[int, str]) -> str:
    for item in account.get("available_groups", []):
        if item.get("id") == group:
            return str(item.get("title") or group)
    return str(group)


async def send_template_to_group(client: Client, group: Union[int, str], template: Dict[str, Any], group_name: str) -> None:
    kind = str(template.get("kind") or "text")
    text = apply_template_variables(template_body(template), group_name)
    if kind == "photo" and template.get("file_id"):
        await client.send_photo(group, template["file_id"], caption=text or None, parse_mode=ParseMode.HTML)
        return
    if kind == "video" and template.get("file_id"):
        await client.send_video(group, template["file_id"], caption=text or None, parse_mode=ParseMode.HTML)
        return
    if kind == "animation" and template.get("file_id"):
        await client.send_animation(group, template["file_id"], caption=text or None, parse_mode=ParseMode.HTML)
        return
    if kind == "document" and template.get("file_id"):
        await client.send_document(group, template["file_id"], caption=text or None, parse_mode=ParseMode.HTML)
        return
    await client.send_message(group, text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)


def is_vip_active(user_id: Union[int, str]) -> bool:
    if int(user_id) == OWNER_ID:
        return True
    data = ensure_user(user_id)
    if not data.get("vip"):
        return False
    vip_until = parse_dt(data.get("vip_until"))
    if vip_until and vip_until <= now_local():
        data["vip"] = False
        data["vip_until"] = None
        data["limitation"] = {}
        data["posting"] = False
        save_users()
        return False
    return True


def vip_payload(start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
    delta = max(end_dt - start_dt, timedelta())
    total_minutes = int(delta.total_seconds() // 60)
    return {
        "current_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "endTime": end_dt.strftime("%H:%M"),
        "hours": total_minutes // 60,
        "minutes": total_minutes,
    }


def activate_vip(user_id: int, days: int) -> Dict[str, Any]:
    data = ensure_user(user_id)
    start_dt = now_local()
    old_until = parse_dt(data.get("vip_until"))
    if data.get("vip") and old_until and old_until > start_dt:
        start_dt = old_until
    end_dt = start_dt + timedelta(days=days)
    payload = vip_payload(now_local(), end_dt)
    data["vip"] = True
    data["vip_until"] = end_dt.isoformat()
    data["limitation"] = {
        "days": days,
        "startDate": payload["current_date"],
        "endDate": payload["end_date"],
        "endTime": payload["endTime"],
    }
    append_user_log(user_id, "activate_vip", details={"days": days, "end_date": payload["end_date"]})
    save_users()
    return payload


def activate_trial(user_id: int, hours: int = 2) -> Dict[str, Any]:
    data = ensure_user(user_id)
    start_dt = now_local()
    end_dt = start_dt + timedelta(hours=hours)
    payload = vip_payload(start_dt, end_dt)
    data["vip"] = True
    data["vip_until"] = end_dt.isoformat()
    data["trial_used"] = True
    data["limitation"] = {
        "hours": hours,
        "trial": True,
        "startDate": payload["current_date"],
        "endDate": payload["end_date"],
        "endTime": payload["endTime"],
    }
    append_user_log(user_id, "activate_trial", details={"hours": hours})
    save_users()
    return payload


def truncate(text: str, size: int = 38) -> str:
    return text if len(text) <= size else text[: size - 3] + "..."


def format_dt(dt_value: Optional[datetime]) -> str:
    return dt_value.strftime("%Y-%m-%d %H:%M") if dt_value else "غير محدد"


BOT_FEATURES_TEXT = """━━━━━━━━━━━━━━━━━━━━━ 🌟 مميزات البوت 🌟 ━━━━━━━━━━━━━━━━━━━━━
━━━━━━━━━━━━━━━━━━━━━ 🎬 النشر التلقائي:
• نشر جميع الكليشات في جميع المجموعات دفعة واحدة
• فاصل زمني قابل للتخصيص (60 ثانية فما فوق)
• تأخير ذكي بين الكليشات (0-30 ثانية)
• نشر متزامن فوري في كل المجموعات
• إعادة محاولة تلقائية 3 مرات عند الفشل
• توقف تلقائي عند انتهاء VIP
━━━━━━━━━━━━━━━━━━━━━ 🎯 النشر المخصص:
• اختيار مجموعات محددة لكل نشر
• اختيار كليشة محددة أو رفع جديدة
• وقت خاص مستقل لكل نشر مخصص
• تشغيل عدة نشرات مخصصة بنفس الوقت
• تعديل وإيقاف وحذف كل نشر بشكل مستقل
━━━━━━━━━━━━━━━━━━━━━ 📅 جدولة النشر الأسبوعية:
• تحديد أيام وساعات النشر بدقة (الأحد - السبت)
• توقيت بغداد GMT+3 تلقائياً
• تفعيل/تعطيل الجدولة بضغطة واحدة
━━━━━━━━━━━━━━━━━━━━━ 👥 المجموعات:
• فحص تلقائي لكل مجموعاتك دفعة واحدة
• تفعيل/تعطيل مجموعات بشكل فردي أو جماعي
• عرض مجموعات مضافة ومجموعات غير مضافة منفصلة
• بحث عن مجموعة بالاسم
• إشعار فوري عند دخول مجموعة جديدة مع زر إضافة سريع
• إشعار فوري عند الخروج من مجموعة وحذفها تلقائياً
━━━━━━━━━━━━━━━━━━━━━ 🤖 اشتراك تلقائي في المجموعات (VIP):
• لما بوت مجموعة يطلب منك الاشتراك في قناة
• الحساب يكتشف الطلب ويشترك تلقائياً بدون تدخلك
• يشتغل في حالتين:
— البوت رد مباشرة على كليشتك بزر قناة
— البوت ذكر اسمك أو يوزرك في رسالة + زر قناة
• يدعم روابط t.me وروابط الدعوة الخاصة و@يوزر
• بعد الاشتراك يرجع ينشر الكليشة تلقائياً
• يرسلك إشعار باسم القناة التي انضم إليها
━━━━━━━━━━━━━━━━━━━━━ 📊 الإحصائيات:
• إحصائيات لحظية دقيقة (نجاح/فشل)
• إحصائيات الجلسة الحالية منفصلة
• إحصائيات إجمالية منذ البداية
• تقرير يومي تلقائي
━━━━━━━━━━━━━━━━━━━━━ 💾 مجموعة التخزين الذكية:
• إنشاء تلقائي عند إضافة الحساب
• حفظ كل رسالة تُنشر تلقائياً
• حفظ الردود والرسائل الواردة
━━━━━━━━━━━━━━━━━━━━━ 📢 الإذاعة للخاص (VIP):
• إرسال رسالة لكل محادثاتك الخاصة عبر حسابك
• دعم النصوص والصور والفيديوهات
• تقرير مفصل + زر إيقاف فوري
• حفظ إحصائيات كل إذاعة
━━━━━━━━━━━━━━━━━━━━━ 💬 الردود الذكية بالكلمات:
• رد تلقائي عند ذكر كلمة معينة في مجموعاتك
• كلمات مخصصة ورد مخصص لكل كلمة
━━━━━━━━━━━━━━━━━━━━━ 🛡 حماية الحساب (Anti-Ban):
• ثلاثة أوضاع: عادي / آمن / خفي
• تأخيرات ذكية تلقائية
• حماية من FloodWait وPeerFlood
• إشعار فوري عند تقييد مجموعة (لا يوقف الباقي)
━━━━━━━━━━━━━━━━━━━━━ ⏱ اشتراك تجريبي مجاني:
• 2 ساعة كاملة من مميزات VIP
• مرة واحدة فقط لكل مستخدم
━━━━━━━━━━━━━━━━━━━━━ 🔒 العزل والأمان:
• عزل كامل 100% بين جميع المستخدمين
• كل مستخدم له داتابيس مستقل
• تشفير AES-256 للبيانات الحساسة
━━━━━━━━━━━━━━━━━━━━━ 📞 للمساعدة:
@rrry_r
━━━━━━━━━━━━━━━━━━━━━"""

TIPS_TEXT = """نصائح الاستخدام

• لا ترسل نفس الرسالة بسرعة
• لا تستخدم حساب جديد
• استخدم Delay مناسب (30-60 ثانية)
• لا تنشر في عدد كبير دفعة واحدة
• تجنب السبام
• توقف إذا ظهر تحذير"""


def home_markup() -> Markup:
    return Markup(
        [
            [Button("مميزات البوت ⚠️", callback_data="botFeatures")],
            [Button("نصائح", callback_data="tips")],
            [Button("- حسابك -", callback_data="account")],
            [Button("- السوبرات الحالية -", callback_data="manageGroups"), Button("- مزامنة السوبرات -", callback_data="refreshGroups")],
            [Button("- إضافة كليشة -", callback_data="addTemplate"), Button("- إدارة الكلايش -", callback_data="manageTemplates")],
            [Button("- المدة الافتراضية -", callback_data="waitTime")],
            [Button("- إعدادات النشر -", callback_data="postingSettings"), Button("- إحصائيات النشر -", callback_data="postingStats")],
            [Button("- بدء النشر -", callback_data="startPosting"), Button("- إيقاف النشر -", callback_data="stopPosting")],
            [Button("- إعدادات /ai -", callback_data="aiMenu")],
        ]
    )


def account_markup() -> Markup:
    return Markup(
        [
            [Button("- إضافة حساب برقم -", callback_data="login"), Button("- إضافة حساب بجلسة -", callback_data="loginses")],
            [Button("- التبديل بين الحسابات -", callback_data="switchAccounts"), Button("- مغادرة كل المجموعات -", callback_data="leaveAllChats")],
            [Button("- حذف الحساب الحالي -", callback_data="deleteCurrentAccount")],
            [Button("- رجوع -", callback_data="toHome")],
        ]
    )


def admin_markup(user_id: Union[int, str]) -> Markup:
    rows: List[List[Button]] = [
        [Button("- إلغاء اشتراك (ID) -", callback_data="cancelVIP"), Button("- تفعيل اشتراك (ID DAYS) -", callback_data="addVIP")],
    ]
    if int(user_id) == OWNER_ID:
        rows.extend(
            [
                [Button("- إضافة أدمن -", callback_data="addAdmin"), Button("- حذف أدمن -", callback_data="removeAdmin")],
                [Button("- عرض الأدمن -", callback_data="listAdmins"), Button("- الإحصائيات -", callback_data="statics")],
                [Button("- قنوات الاشتراك -", callback_data="channels"), Button("- الجلسات -", callback_data="viewsession")],
                [Button("- إرسال إذاعة -", callback_data="broadcast"), Button("- المستخدمون -", callback_data="viewUsers")],
                [Button("- الكلايش -", callback_data="viewcaption"), Button("- جلب التخزين -", callback_data="sendFiles")],
            ]
        )
    else:
        rows.append([Button("- رجوع -", callback_data="toHome")])
        return Markup(rows)
    rows.append([Button("- رجوع -", callback_data="toHome")])
    return Markup(rows)


def back(callback_data: str) -> Markup:
    return Markup([[Button("- رجوع -", callback_data=callback_data)]])


def cancel_prompt_markup() -> Markup:
    return Markup([[Button("- إلغاء -", callback_data="cancelTemplatePrompt")]])


def current_account_name(user_id: Union[int, str]) -> str:
    return account_display_name(account_data(ensure_user(user_id)))


def accounts_count(user_id: Union[int, str]) -> int:
    return len(ensure_user(user_id).get("accounts", {}))


def switch_accounts_markup(user_id: Union[int, str]) -> Markup:
    data = ensure_user(user_id)
    active_id = active_account_id(data)
    rows: List[List[Button]] = []
    for account_id in sorted(data.get("accounts", {}).keys(), key=account_sort_key):
        account = account_data(data, account_id)
        prefix = "✅" if account_id == active_id else "◽"
        rows.append([Button(f"{prefix} {truncate(account_display_name(account), 38)}", callback_data=f"switchAccount:{account_id}")])
    rows.append([Button("- رجوع -", callback_data="account")])
    return Markup(rows)


def cancel_pending_listens(chat_id: int, from_id: int) -> bool:
    client_cache = listener_module._cache.get(app.name)
    if not client_cache:
        return False

    canceled = False
    for data in list(client_cache.get("list", [])):
        if data.get("chat_id") != chat_id:
            continue

        allowed = data.get("from_id")
        if isinstance(allowed, list):
            matches = from_id in allowed
        else:
            matches = allowed in {None, from_id}

        if not matches:
            continue

        key = json.dumps(data, ensure_ascii=False)
        client_cache[key] = None
        client_cache["list"].remove(data)
        canceled = True

    return canceled


async def ensure_access(update: Union[Message, CallbackQuery], require_vip: bool = True) -> bool:
    user_id = update.from_user.id
    ensure_user(user_id)
    if user_id == OWNER_ID:
        return True
    missing_channel = await missing_subscription_channel(user_id)
    if missing_channel:
        text = f"يجب عليك الاشتراك في قناة البوت أولاً: @{missing_channel}"
        if isinstance(update, CallbackQuery):
            await update.answer(text, show_alert=True)
        else:
            await update.reply(text, reply_markup=required_subscription_markup(missing_channel))
        return False
    if require_vip and not is_vip_active(user_id):
        text = "لا يمكنك استخدام البوت حالياً، يجب عليك شراء اشتراك من المطور"
        if isinstance(update, CallbackQuery):
            await update.answer(text, show_alert=True)
        else:
            await update.reply(text, reply_markup=developer_contact_markup())
        return False
    return True


async def render_home(target: Union[Message, CallbackQuery]) -> None:
    user_id = target.from_user.id
    data = ensure_user(user_id)
    vip_text = "مفتوح لك كمالك البوت." if user_id == OWNER_ID else ("مفعل حتى " + format_dt(parse_dt(data.get("vip_until"))) if data.get("vip") else "غير مفعل")
    caption = (
        f"- مرحبا بك عزيزي {target.from_user.first_name} في بوت النشر التلقائي\n\n"
        f"- الاشتراك: {vip_text}\n"
        f"- السوبرات المحددة: {len(data.get('groups', []))}\n"
        f"- عدد الكلايش: {len(data.get('templates', []))}\n"
        f"- المدة الافتراضية: {data.get('default_delay', 60)} ثانية\n\n"
        "- الكلايش الآن تدعم أكثر من نص، ولكل كليشة وقتها الخاص.\n"
        "- استخدم الأزرار التالية للتحكم:"
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(caption, reply_markup=home_markup())
    else:
        await target.reply(caption, reply_markup=home_markup(), reply_to_message_id=target.id)


async def render_account(callback: CallbackQuery) -> None:
    data = ensure_user(callback.from_user.id)
    caption = (
        f"- رقم الحساب الحالي: {data.get('account_number') or 'غير مسجل'}\n"
        f"- آخر مزامنة للسوبرات: {format_dt(parse_dt(data.get('last_groups_sync')))}\n"
        f"- عدد السوبرات المحددة: {len(data.get('groups', []))}\n"
        "- استخدم الأزرار التالية للتحكم بحسابك:"
    )
    await callback.message.edit_text(caption, reply_markup=account_markup())


async def render_home(target: Union[Message, CallbackQuery]) -> None:
    user_id = target.from_user.id
    data = ensure_user(user_id)
    vip_text = "مفتوح لك كمالك البوت." if user_id == OWNER_ID else ("مفعل حتى " + format_dt(parse_dt(data.get("vip_until"))) if data.get("vip") else "غير مفعل")
    caption = (
        f"- مرحباً بك عزيزي {target.from_user.first_name} في بوت النشر التلقائي\n\n"
        f"- الاشتراك: {vip_text}\n"
        f"- الحساب النشط: {current_account_name(user_id)}\n"
        f"- عدد الحسابات: {accounts_count(user_id)}\n"
        f"- السوبرات المحددة: {len(data.get('groups', []))}\n"
        f"- عدد الكلايش: {len(data.get('templates', []))}\n"
        f"- المدة الافتراضية: {data.get('default_delay', 60)} ثانية\n\n"
        f"- وضع الحماية: {mode_label(posting_settings_for(user_id).get('mode', 'safe'))}\n"
        "- الكلايش الآن تدعم أكثر من نص ووسائط، ولكل كليشة وقتها الخاص.\n"
        "- استخدم الأزرار التالية للتحكم:"
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(caption, reply_markup=home_markup())
    else:
        await target.reply(caption, reply_markup=home_markup(), reply_to_message_id=target.id)


async def render_account(callback: CallbackQuery) -> None:
    data = ensure_user(callback.from_user.id)
    caption = (
        f"- الحساب النشط: {current_account_name(callback.from_user.id)}\n"
        f"- عدد الحسابات: {accounts_count(callback.from_user.id)}\n"
        f"- رقم الحساب الحالي: {data.get('account_number') or 'غير مسجل'}\n"
        f"- آخر مزامنة للسوبرات: {format_dt(parse_dt(data.get('last_groups_sync')))}\n"
        f"- عدد السوبرات المحددة: {len(data.get('groups', []))}\n"
        "- استخدم الأزرار التالية للتحكم بحسابك:"
    )
    await callback.message.edit_text(caption, reply_markup=account_markup())


async def render_accounts_switcher(callback: CallbackQuery) -> None:
    caption = (
        "- اختر الحساب الذي تريد التبديل إليه.\n"
        "- الكلايش مشتركة بين كل الحسابات.\n"
        "- السوبرات والجلسة تبقى خاصة بكل حساب."
    )
    await callback.message.edit_text(caption, reply_markup=switch_accounts_markup(callback.from_user.id))


def ensure_ai_config(user_id: Union[int, str]) -> Dict[str, Any]:
    data = ensure_user(user_id)
    if not isinstance(data.get("ai"), dict):
        data["ai"] = {}

    ai_cfg = data["ai"]
    if "enabled" not in ai_cfg:
        ai_cfg["enabled"] = False
    if "reply" not in ai_cfg:
        ai_cfg["reply"] = "- تم استلام المنشن أو الرد."
    if "target_username" not in ai_cfg:
        ai_cfg["target_username"] = ""
    return ai_cfg


def ai_menu_markup() -> Markup:
    return Markup(
        [
            [Button("- تشغيل /ai -", callback_data="aiEnable"), Button("- إيقاف /ai -", callback_data="aiDisable")],
            [Button("- تعيين الرد -", callback_data="aiSetReply"), Button("- تعيين يوزر المنشن -", callback_data="aiSetUsername")],
            [Button("- رجوع -", callback_data="toHome")],
        ]
    )


def ai_menu_caption(user_id: Union[int, str]) -> str:
    cfg = ensure_ai_config(user_id)
    enabled = "مفعل ✅" if cfg.get("enabled") else "معطل ❌"
    running = "شغال" if (ai_workers.get(str(user_id)) and not ai_workers[str(user_id)].done()) else "متوقف"
    reply_text = str(cfg.get("reply") or "").strip()
    target_username = str(cfg.get("target_username") or "").strip().lstrip("@")
    preview = reply_text if len(reply_text) <= 200 else (reply_text[:200] + "...")
    return (
        "- إعدادات /ai\n\n"
        f"- الحالة: {enabled}\n"
        f"- العامل: {running}\n"
        f"- يوزر المنشن: @{target_username if target_username else 'غير محدد'}\n\n"
        "- الرد الحالي:\n"
        f"{preview if preview else '- لا يوجد رد محدد'}\n\n"
        "- يعمل داخل المجموعات عند:\n"
        "1) الرد على رسالتك\n"
        "2) منشن @username"
    )


async def render_ai_menu_message(message: Message) -> None:
    await message.reply(ai_menu_caption(message.from_user.id), reply_markup=ai_menu_markup(), reply_to_message_id=message.id)


async def render_ai_menu_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ai_menu_caption(callback.from_user.id), reply_markup=ai_menu_markup())


def stop_ai_worker(user_id: Union[int, str]) -> None:
    key = str(user_id)
    task = ai_workers.get(key)
    if task and not task.done():
        task.cancel()
    ai_workers.pop(key, None)


def start_ai_worker(user_id: Union[int, str]) -> None:
    key = str(user_id)
    task = ai_workers.get(key)
    if task and not task.done():
        return
    ai_workers[key] = asyncio.create_task(ai_worker(int(user_id)))


async def ai_worker(user_id: int) -> None:
    user_key = str(user_id)
    user_data = ensure_user(user_id)
    if not user_data.get("session") or not is_vip_active(user_id):
        return

    client = build_user_client(user_id, "ai_worker")

    try:
        await client.start()
        me = await client.get_me()
        my_id = me.id
        my_username = (me.username or "").lower()

        async def _on_group_message(_: Client, msg: Message) -> None:
            cfg = ensure_ai_config(user_id)
            if not cfg.get("enabled"):
                return
            if msg.from_user and msg.from_user.is_bot:
                return
            if msg.from_user and msg.from_user.id == my_id:
                return

            is_reply_to_me = bool(
                msg.reply_to_message
                and msg.reply_to_message.from_user
                and msg.reply_to_message.from_user.id == my_id
            )

            text = (msg.text or msg.caption or "")
            target_username = str(cfg.get("target_username") or my_username).strip().lstrip("@").lower()
            is_mention_me = bool(target_username and f"@{target_username}" in text.lower())
            if not (is_reply_to_me or is_mention_me):
                return

            reply_text = str(cfg.get("reply") or "").strip()
            if not reply_text:
                return

            try:
                await msg.reply(reply_text)
            except Exception:
                pass

        handler = MessageHandler(_on_group_message, filters.group & filters.incoming)
        client.add_handler(handler, group=0)

        while ensure_ai_config(user_id).get("enabled"):
            await asyncio.sleep(5)

    except Exception as error:
        cfg = ensure_ai_config(user_id)
        cfg["enabled"] = False
        save_users()
        try:
            await app.send_message(user_id, f"- تم إيقاف /ai بسبب خطأ:\n{error}")
        except Exception:
            pass
    finally:
        ai_workers.pop(user_key, None)
        try:
            await client.stop()
        except Exception:
            pass


def ensure_ai_config(user_id: Union[int, str], account_id: Optional[str] = None) -> Dict[str, Any]:
    user_data = ensure_user(user_id)
    data = account_data(user_data, account_id)
    if not isinstance(data.get("ai"), dict):
        data["ai"] = {}

    ai_cfg = data["ai"]
    if "enabled" not in ai_cfg:
        ai_cfg["enabled"] = False
    if "reply" not in ai_cfg:
        ai_cfg["reply"] = "- تم استلام المنشن أو الرد."
    if "target_username" not in ai_cfg:
        ai_cfg["target_username"] = ""
    if account_id is None:
        expose_active_account(user_data)
    return ai_cfg


def ai_worker_key(user_id: Union[int, str], account_id: Optional[str] = None) -> str:
    data = ensure_user(user_id)
    account_id = account_id or active_account_id(data)
    return f"{user_id}:{account_id}"


def ai_menu_caption(user_id: Union[int, str]) -> str:
    data = ensure_user(user_id)
    account_id = active_account_id(data)
    cfg = ensure_ai_config(user_id, account_id)
    enabled = "مفعل ✅" if cfg.get("enabled") else "معطل ⛔"
    key = ai_worker_key(user_id, account_id)
    running = "شغال" if (ai_workers.get(key) and not ai_workers[key].done()) else "متوقف"
    reply_text = str(cfg.get("reply") or "").strip()
    target_username = str(cfg.get("target_username") or "").strip().lstrip("@")
    preview = reply_text if len(reply_text) <= 200 else (reply_text[:200] + "...")
    return (
        "- إعدادات /ai\n\n"
        f"- الحساب: {current_account_name(user_id)}\n"
        f"- الحالة: {enabled}\n"
        f"- العامل: {running}\n"
        f"- يوزر المنشن: @{target_username if target_username else 'غير محدد'}\n\n"
        "- الرد الحالي:\n"
        f"{preview if preview else '- لا يوجد رد محدد'}\n\n"
        "- يعمل داخل المجموعات عند:\n"
        "1) الرد على رسالتك\n"
        "2) منشن @username"
    )


def stop_ai_worker(user_id: Union[int, str], account_id: Optional[str] = None) -> None:
    key = ai_worker_key(user_id, account_id)
    task = ai_workers.get(key)
    if task and not task.done():
        task.cancel()
    ai_workers.pop(key, None)


def start_ai_worker(user_id: Union[int, str], account_id: Optional[str] = None) -> None:
    key = ai_worker_key(user_id, account_id)
    task = ai_workers.get(key)
    if task and not task.done():
        return
    account_id = account_id or active_account_id(ensure_user(user_id))
    ai_workers[key] = asyncio.create_task(ai_worker(int(user_id), account_id))


async def ai_worker(user_id: int, account_id: str) -> None:
    worker_key = ai_worker_key(user_id, account_id)
    user_account = account_data(ensure_user(user_id), account_id)
    if not user_account.get("session") or not is_vip_active(user_id):
        return

    client = build_user_client(user_id, "ai_worker", account_id)

    try:
        await client.start()
        me = await client.get_me()
        my_id = me.id
        my_username = (me.username or "").lower()

        async def _on_group_message(_: Client, msg: Message) -> None:
            cfg = ensure_ai_config(user_id, account_id)
            if not cfg.get("enabled"):
                return
            if msg.from_user and msg.from_user.is_bot:
                return
            if msg.from_user and msg.from_user.id == my_id:
                return

            is_reply_to_me = bool(
                msg.reply_to_message
                and msg.reply_to_message.from_user
                and msg.reply_to_message.from_user.id == my_id
            )

            text = (msg.text or msg.caption or "")
            target_username = str(cfg.get("target_username") or my_username).strip().lstrip("@").lower()
            is_mention_me = bool(target_username and f"@{target_username}" in text.lower())
            if not (is_reply_to_me or is_mention_me):
                return

            reply_text = str(cfg.get("reply") or "").strip()
            if not reply_text:
                return

            try:
                await msg.reply(reply_text)
            except Exception:
                pass

        handler = MessageHandler(_on_group_message, filters.group & filters.incoming)
        client.add_handler(handler, group=0)

        while ensure_ai_config(user_id, account_id).get("enabled"):
            await asyncio.sleep(5)

    except Exception as error:
        cfg = ensure_ai_config(user_id, account_id)
        cfg["enabled"] = False
        save_users()
        try:
            await app.send_message(user_id, f"- تم إيقاف /ai في {account_display_name(user_account)} بسبب خطأ:\n{error}")
        except Exception:
            pass
    finally:
        ai_workers.pop(worker_key, None)
        try:
            await client.stop()
        except Exception:
            pass


def build_user_client(user_id: Union[int, str], purpose: str, account_id: Optional[str] = None) -> Client:
    data = account_data(ensure_user(user_id), account_id)
    account_key = account_id or active_account_id(ensure_user(user_id))
    return Client(
        name=f"{purpose}_{user_id}_{account_key}",
        session_string=data.get("session") or "",
        api_id=app.api_id,
        api_hash=app.api_hash,
        in_memory=True,
        **CLIENT_PROFILE,
    )


async def sync_user_groups(user_id: int, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
    user_data = ensure_user(user_id)
    data = account_data(user_data, account_id)
    if not data.get("session"):
        raise ValueError("لا يوجد حساب مسجل.")
    client = build_user_client(user_id, "groups", account_id)
    groups_cache: List[Dict[str, Any]] = []
    selected = {group for group in data.get("groups", []) if isinstance(group, int)}
    try:
        await client.start()
        await ensure_account_channel_membership(client)
        async for dialog in client.get_dialogs():
            chat = dialog.chat
            chat_type = getattr(chat.type, "value", str(chat.type))
            if chat_type not in {"group", "supergroup"}:
                continue
            groups_cache.append({"id": chat.id, "title": chat.title or str(chat.id)})
    finally:
        try:
            await client.stop()
        except Exception:
            pass
    groups_cache.sort(key=lambda item: item["title"].lower())
    data["available_groups"] = groups_cache
    data["groups"] = [item["id"] for item in groups_cache if item["id"] in selected]
    data["last_groups_sync"] = now_local().isoformat()
    expose_active_account(user_data)
    save_users()
    return groups_cache


def groups_markup(user_id: int, page: int = 0) -> Markup:
    data = ensure_user(user_id)
    available_groups = data.get("available_groups", [])
    selected = set(data.get("groups", []))
    total_pages = max((len(available_groups) - 1) // GROUPS_PAGE_SIZE + 1, 1)
    page = max(0, min(page, total_pages - 1))
    start = page * GROUPS_PAGE_SIZE
    end = start + GROUPS_PAGE_SIZE
    rows: List[List[Button]] = []
    for item in available_groups[start:end]:
        prefix = "✅" if item["id"] in selected else "➕"
        rows.append([Button(f"{prefix} {truncate(item['title'], 45)}", callback_data=f"toggleGroup:{item['id']}:{page}")])
    rows.append([Button("- تحديد الكل -", callback_data="selectAllGroups"), Button("- إلغاء الكل -", callback_data="clearAllGroups")])
    nav = []
    if page > 0:
        nav.append(Button("- السابق -", callback_data=f"groupsPage:{page - 1}"))
    nav.append(Button(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(Button("- التالي -", callback_data=f"groupsPage:{page + 1}"))
    rows.append(nav)
    rows.append([Button("- تحديث القائمة -", callback_data="refreshGroups"), Button("- الرئيسية -", callback_data="toHome")])
    return Markup(rows)


async def render_groups(callback: CallbackQuery, page: int = 0, refresh: bool = False) -> None:
    data = ensure_user(callback.from_user.id)
    if not data.get("session"):
        await callback.message.edit_text("- عليك تسجيل حسابك أولاً حتى أستطيع سحب المجموعات تلقائياً.", reply_markup=Markup([[Button("- تسجيل حساب -", callback_data="login")], [Button("- رجوع -", callback_data="toHome")]]))
        return
    if refresh or not data.get("available_groups"):
        try:
            await sync_user_groups(callback.from_user.id)
        except Exception as error:
            await callback.message.edit_text(f"- تعذر سحب المجموعات:\n{error}", reply_markup=Markup([[Button("- إعادة المحاولة -", callback_data="refreshGroups")], [Button("- رجوع -", callback_data="toHome")]]))
            return
    data = ensure_user(callback.from_user.id)
    if not data.get("available_groups"):
        await callback.message.edit_text("- لم أجد أي مجموعات في هذا الحساب.", reply_markup=back("toHome"))
        return
    caption = (
        "- هذه المجموعات تم سحبها تلقائياً من الحساب المسجل.\n"
        "- اضغط على اسم المجموعة لإضافتها أو إزالتها من النشر.\n"
        f"- المحدد حالياً: {len(data.get('groups', []))}"
    )
    await callback.message.edit_text(caption, reply_markup=groups_markup(callback.from_user.id, page))


def templates_markup(user_id: int, page: int = 0) -> Markup:
    data = ensure_user(user_id)
    templates = data.get("templates", [])
    total_pages = max((len(templates) - 1) // TEMPLATES_PAGE_SIZE + 1, 1)
    page = max(0, min(page, total_pages - 1))
    start = page * TEMPLATES_PAGE_SIZE
    end = start + TEMPLATES_PAGE_SIZE
    rows: List[List[Button]] = []
    for index in range(start, min(end, len(templates))):
        template = templates[index]
        rows.append([
            Button(f"{index + 1}. {truncate(template_preview(template), 28)}", callback_data=f"showTemplate:{index}:{page}"),
            Button(f"{template['delay']}s", callback_data="noop"),
            Button("🗑", callback_data=f"delTemplate:{index}:{page}"),
        ])
    nav = []
    if page > 0:
        nav.append(Button("- السابق -", callback_data=f"templatesPage:{page - 1}"))
    nav.append(Button(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(Button("- التالي -", callback_data=f"templatesPage:{page + 1}"))
    rows.append(nav)
    rows.append([Button("- إضافة كليشة -", callback_data="addTemplate"), Button("- الرئيسية -", callback_data="toHome")])
    return Markup(rows)


async def render_templates(callback: CallbackQuery, page: int = 0) -> None:
    data = ensure_user(callback.from_user.id)
    if not data.get("templates"):
        await callback.message.edit_text("- لا توجد كلايش محفوظة حالياً.", reply_markup=Markup([[Button("- إضافة كليشة -", callback_data="addTemplate")], [Button("- رجوع -", callback_data="toHome")]]))
        return
    caption = "- هذه هي الكلايش الحالية. كل كليشة تملك وقتاً خاصاً بعدها، وتدعم النصوص والوسائط."
    await callback.message.edit_text(caption, reply_markup=templates_markup(callback.from_user.id, page))


async def registration(message: Message) -> None:
    user_id = message.from_user.id
    phone_number = message.text.strip()
    status = await message.reply("- جارٍ تسجيل الدخول إلى حسابك.")
    client = Client(name=f"login_{user_id}", in_memory=True, api_id=app.api_id, api_hash=app.api_hash, **CLIENT_PROFILE)
    await client.connect()
    try:
        code_hash = await client.send_code(phone_number)
    except PhoneNumberInvalid:
        await client.disconnect()
        await status.edit_text("- رقم الهاتف غير صحيح.", reply_markup=back("account"))
        return
    try:
        code = await listener.listen(from_id=user_id, chat_id=user_id, text="- تم إرسال الكود. أرسله الآن.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="1 2 3 4 5"))
    except exceptions.TimeOut:
        await client.disconnect()
        await status.edit_text("- انتهى وقت استلام الكود.", reply_markup=back("account"))
        return
    try:
        await client.sign_in(phone_number, code_hash.phone_code_hash, code.text.replace(" ", ""))
    except PhoneCodeInvalid:
        await client.disconnect()
        await code.reply("- الكود غير صحيح.", reply_markup=back("account"), reply_to_message_id=code.id)
        return
    except PhoneCodeExpired:
        await client.disconnect()
        await code.reply("- الكود منتهي الصلاحية.", reply_markup=back("account"), reply_to_message_id=code.id)
        return
    except SessionPasswordNeeded:
        try:
            password = await listener.listen(from_id=user_id, chat_id=user_id, text="- أدخل كلمة مرور التحقق بخطوتين.", timeout=180, reply_markup=ForceReply(selective=True, placeholder="- Password"))
        except exceptions.TimeOut:
            await client.disconnect()
            await status.edit_text("- انتهى وقت استلام كلمة المرور.", reply_markup=back("account"))
            return
        try:
            await client.check_password(password.text)
        except PasswordHashInvalid:
            await client.disconnect()
            await password.reply("- كلمة المرور غير صحيحة.", reply_markup=back("account"))
            return
    session = await client.export_session_string()
    me = await client.get_me()
    await ensure_account_channel_membership(client)
    await client.disconnect()
    data = ensure_user(user_id)
    data["session"] = session
    data["account_number"] = f"+{me.phone_number}" if getattr(me, "phone_number", None) else phone_number
    data["available_groups"] = []
    data["groups"] = []
    data["last_groups_sync"] = None
    save_users()
    try:
        await sync_user_groups(user_id)
        text = "- تم تسجيل الحساب وسحب المجموعات تلقائياً."
    except Exception:
        text = "- تم تسجيل الحساب بنجاح. يمكنك مزامنة المجموعات من الزر المخصص."
    await app.send_message(user_id, text, reply_markup=back("toHome"))


async def registration_via_session(message: Message) -> None:
    user_id = message.from_user.id
    session = message.text.strip()
    status = await message.reply("- جارٍ تسجيل الدخول بكود الجلسة.")
    client = Client(name=f"session_{user_id}", session_string=session, in_memory=True, api_id=app.api_id, api_hash=app.api_hash, **CLIENT_PROFILE)
    try:
        await client.connect()
        me = await client.get_me()
    except Exception as error:
        try:
            await client.disconnect()
        except Exception:
            pass
        await status.edit_text(f"- فشل تسجيل الدخول بكود الجلسة:\n{error}", reply_markup=back("account"))
        return
    await client.disconnect()
    data = ensure_user(user_id)
    data["session"] = session
    data["account_number"] = f"+{me.phone_number}" if getattr(me, "phone_number", None) else data.get("account_number") or "غير معروف"
    data["available_groups"] = []
    data["groups"] = []
    data["last_groups_sync"] = None
    save_users()
    try:
        await sync_user_groups(user_id)
        text = "- تم تسجيل الجلسة وسحب المجموعات تلقائياً."
    except Exception:
        text = "- تم تسجيل الجلسة بنجاح. يمكنك مزامنة المجموعات من الزر المخصص."
    await app.send_message(user_id, text, reply_markup=back("toHome"))


async def registration(message: Message) -> None:
    user_id = message.from_user.id
    user_data = ensure_user(user_id)
    active_id = active_account_id(user_data)
    active = account_data(user_data, active_id)
    phone_number = message.text.strip()
    status = await message.reply("- جاري تسجيل الدخول إلى حسابك.")
    client = Client(name=f"login_{user_id}", in_memory=True, api_id=app.api_id, api_hash=app.api_hash, **CLIENT_PROFILE)
    await client.connect()
    try:
        code_hash = await client.send_code(phone_number)
    except PhoneNumberInvalid:
        await client.disconnect()
        await status.edit_text("- رقم الهاتف غير صحيح.", reply_markup=back("account"))
        return
    try:
        code = await listener.listen(from_id=user_id, chat_id=user_id, text="- تم إرسال الكود. أرسله الآن.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="1 2 3 4 5"))
    except exceptions.TimeOut:
        await client.disconnect()
        await status.edit_text("- انتهى وقت استلام الكود.", reply_markup=back("account"))
        return
    try:
        await client.sign_in(phone_number, code_hash.phone_code_hash, code.text.replace(" ", ""))
    except PhoneCodeInvalid:
        await client.disconnect()
        await code.reply("- الكود غير صحيح.", reply_markup=back("account"), reply_to_message_id=code.id)
        return
    except PhoneCodeExpired:
        await client.disconnect()
        await code.reply("- الكود منتهي الصلاحية.", reply_markup=back("account"), reply_to_message_id=code.id)
        return
    except SessionPasswordNeeded:
        try:
            password = await listener.listen(from_id=user_id, chat_id=user_id, text="- أدخل كلمة مرور التحقق بخطوتين.", timeout=180, reply_markup=ForceReply(selective=True, placeholder="- Password"))
        except exceptions.TimeOut:
            await client.disconnect()
            await status.edit_text("- انتهى وقت استلام كلمة المرور.", reply_markup=back("account"))
            return
        try:
            await client.check_password(password.text)
        except PasswordHashInvalid:
            await client.disconnect()
            await password.reply("- كلمة المرور غير صحيحة.", reply_markup=back("account"))
            return
    session = await client.export_session_string()
    me = await client.get_me()
    await client.disconnect()
    active["session"] = session
    active["account_number"] = f"+{me.phone_number}" if getattr(me, "phone_number", None) else phone_number
    active["label"] = active["account_number"] or active.get("label") or f"الحساب {active_id}"
    active["available_groups"] = []
    active["groups"] = []
    active["last_groups_sync"] = None
    expose_active_account(user_data)
    append_user_log(user_id, "login_phone", active_id, {"account_number": active["account_number"]})
    save_users()
    try:
        await sync_user_groups(user_id, active_id)
        text = "- تم تسجيل الحساب وسحب المجموعات تلقائياً."
    except Exception:
        text = "- تم تسجيل الحساب بنجاح. يمكنك مزامنة المجموعات من الزر المخصص."
    await app.send_message(user_id, text, reply_markup=back("toHome"))


async def registration_via_session(message: Message) -> None:
    user_id = message.from_user.id
    user_data = ensure_user(user_id)
    active_id = active_account_id(user_data)
    active = account_data(user_data, active_id)
    session = message.text.strip()
    status = await message.reply("- جاري تسجيل الدخول بكود الجلسة.")
    client = Client(name=f"session_{user_id}", session_string=session, in_memory=True, api_id=app.api_id, api_hash=app.api_hash, **CLIENT_PROFILE)
    try:
        await client.connect()
        me = await client.get_me()
        await ensure_account_channel_membership(client)
    except Exception as error:
        try:
            await client.disconnect()
        except Exception:
            pass
        await status.edit_text(f"- فشل تسجيل الدخول بكود الجلسة:\n{error}", reply_markup=back("account"))
        return
    await client.disconnect()
    active["session"] = session
    active["account_number"] = f"+{me.phone_number}" if getattr(me, "phone_number", None) else active.get("account_number") or "غير معروف"
    active["label"] = active["account_number"] or active.get("label") or f"الحساب {active_id}"
    active["available_groups"] = []
    active["groups"] = []
    active["last_groups_sync"] = None
    expose_active_account(user_data)
    append_user_log(user_id, "login_session", active_id, {"account_number": active["account_number"]})
    save_users()
    try:
        await sync_user_groups(user_id, active_id)
        text = "- تم تسجيل الجلسة وسحب المجموعات تلقائياً."
    except Exception:
        text = "- تم تسجيل الجلسة بنجاح. يمكنك مزامنة المجموعات من الزر المخصص."
    await app.send_message(user_id, text, reply_markup=back("toHome"))


FORMAT_GUIDE = (
    "📝 تعيين الكليشة\n\n"
    "أرسل لي النص الذي تريد نشره في المجموعات\n\n"
    "التنسيقات المدعومة (اضغط على الكود للنسخ):\n"
    "- عريض: <code>&lt;b&gt;نص&lt;/b&gt;</code>\n"
    "- مائل: <code>&lt;i&gt;نص&lt;/i&gt;</code>\n"
    "- تحته خط: <code>&lt;u&gt;نص&lt;/u&gt;</code>\n"
    "- مشطوب: <code>&lt;s&gt;نص&lt;/s&gt;</code>\n"
    "- مقتبس: <code>&lt;blockquote&gt;نص&lt;/blockquote&gt;</code>\n"
    "- كود: <code>&lt;code&gt;نص&lt;/code&gt;</code>\n\n"
    "أرسل نص الكليشة الآن."
)


async def prompt_new_template(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    await callback.answer()
    try:
        template_message = await listener.listen(
            from_id=user_id,
            chat_id=user_id,
            text=FORMAT_GUIDE,
            timeout=300,
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_prompt_markup(),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الكليشة.", reply_markup=back("toHome"))
        return
    if template_message is None:
        return

    if (template_message.text or "").strip() == "/cancel":
        await template_message.reply("- تم إلغاء العملية.", reply_to_message_id=template_message.id, reply_markup=back("toHome"))
        return
    if not any([template_message.text, template_message.photo, template_message.video, template_message.animation, template_message.document]):
        await template_message.reply("- أرسل نصاً أو صورة أو فيديو أو GIF أو ملفاً.", reply_to_message_id=template_message.id, reply_markup=back("toHome"))
        return

    data = ensure_user(user_id)
    try:
        delay_message = await listener.listen(
            from_id=user_id,
            chat_id=user_id,
            text=(
                f"- أرسل الوقت بعد هذه الكليشة بالثواني.\n"
                f"- إذا أردت استخدام المدة الافتراضية الحالية ({data.get('default_delay', 60)} ثانية) أرسل /skip."
            ),
            timeout=120,
            reply_markup=cancel_prompt_markup(),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الوقت.", reply_markup=back("toHome"))
        return
    if delay_message is None:
        return

    if delay_message.text.strip() == "/cancel":
        await delay_message.reply("- تم إلغاء العملية.", reply_to_message_id=delay_message.id, reply_markup=back("toHome"))
        return

    if delay_message.text.strip() == "/skip":
        delay = max(data.get("default_delay", 60), MIN_DELAY)
    else:
        try:
            delay = int(delay_message.text.strip())
        except ValueError:
            await delay_message.reply("- الوقت يجب أن يكون رقماً صحيحاً.", reply_to_message_id=delay_message.id, reply_markup=back("toHome"))
            return
        if delay < MIN_DELAY:
            await delay_message.reply(f"- أقل مدة مسموحة هي {MIN_DELAY} ثوانٍ.", reply_to_message_id=delay_message.id, reply_markup=back("toHome"))
            return

    template_payload = build_template_payload(template_message, delay)
    data["templates"].append(template_payload)
    append_user_log(user_id, "add_template", details={"kind": template_payload.get("kind"), "delay": delay})
    save_users()
    await delay_message.reply("- تم حفظ الكليشة بنجاح.", reply_to_message_id=delay_message.id, reply_markup=Markup([[Button("- إدارة الكلايش -", callback_data="manageTemplates")], [Button("- الرئيسية -", callback_data="toHome")]]))


@app.on_callback_query(filters.regex(r"^cancelTemplatePrompt$"))
async def cancel_template_prompt(_: Client, callback: CallbackQuery) -> None:
    canceled = cancel_pending_listens(callback.message.chat.id, callback.from_user.id)
    await callback.answer("- تم إلغاء العملية." if canceled else "- لا توجد عملية قيد الانتظار.")
    await callback.message.edit_text("- تم إلغاء العملية.", reply_markup=back("toHome"))


async def subscription_required(message: Message) -> Union[bool, str]:
    missing_channel = await missing_subscription_channel(message.from_user.id)
    return True if missing_channel is None else missing_channel


def posting_key(user_id: Union[int, str]) -> str:
    return str(user_id)


def stop_posting_task(user_id: Union[int, str]) -> None:
    task = posting_tasks.get(posting_key(user_id))
    if task and not task.done():
        task.cancel()


def start_posting_task(user_id: Union[int, str]) -> None:
    key = posting_key(user_id)
    task = posting_tasks.get(key)
    if task and not task.done():
        return
    posting_tasks[key] = asyncio.create_task(run_posting(int(user_id)))


async def run_posting(user_id: int) -> None:
    data = ensure_user(user_id)
    if not data.get("posting") or not data.get("session"):
        return

    client = build_user_client(user_id, "posting")
    try:
        await client.start()
        while ensure_user(user_id).get("posting"):
            if not is_vip_active(user_id):
                break
            data = ensure_user(user_id)
            groups = [normalize_target(item) for item in data.get("groups", []) if normalize_target(item) is not None]
            templates = [item for item in data.get("templates", []) if (item.get("text") or "").strip()]
            if not groups:
                data["posting"] = False
                save_users()
                await app.send_message(user_id, "- تم إيقاف النشر لعدم وجود سوبرات محددة.", reply_markup=back("manageGroups"))
                break
            if not templates:
                data["posting"] = False
                save_users()
                await app.send_message(user_id, "- تم إيقاف النشر لعدم وجود كلايش محفوظة.", reply_markup=back("addTemplate"))
                break

            for template in templates:
                if not ensure_user(user_id).get("posting"):
                    break
                sent = 0
                failed: List[str] = []
                for group in groups:
                    try:
                        await client.send_message(group, template["text"], parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                        sent += 1
                    except (ChatWriteForbidden, PeerIdInvalid):
                        failed.append(str(group))
                    except Exception:
                        failed.append(str(group))
                if sent == 0:
                    preview = "\n".join(f"- {item}" for item in failed[:8]) if failed else "- لا توجد مجموعات صالحة."
                    await app.send_message(user_id, f"- لم أتمكن من نشر الكليشة الحالية في أي مجموعة.\n{preview}")
                await asyncio.sleep(max(template.get("delay", data.get("default_delay", 60)), MIN_DELAY))
    except asyncio.CancelledError:
        pass
    except Exception as error:
        data = ensure_user(user_id)
        data["posting"] = False
        save_users()
        await app.send_message(user_id, f"- توقف النشر بسبب خطأ:\n{error}")
    finally:
        posting_tasks.pop(posting_key(user_id), None)
        try:
            await client.stop()
        except Exception:
            pass


def posting_key(user_id: Union[int, str], account_id: Optional[str] = None) -> str:
    data = ensure_user(user_id)
    account_id = account_id or active_account_id(data)
    return f"{user_id}:{account_id}"


def stop_posting_task(user_id: Union[int, str], account_id: Optional[str] = None) -> None:
    key = posting_key(user_id, account_id)
    task = posting_tasks.get(key)
    if task and not task.done():
        task.cancel()
    posting_tasks.pop(key, None)


def start_posting_task(user_id: Union[int, str], account_id: Optional[str] = None) -> None:
    key = posting_key(user_id, account_id)
    task = posting_tasks.get(key)
    if task and not task.done():
        return
    account_id = account_id or active_account_id(ensure_user(user_id))
    posting_tasks[key] = asyncio.create_task(run_posting(int(user_id), account_id))


async def run_posting(user_id: int, account_id: str) -> None:
    user_root = ensure_user(user_id)
    data = account_data(user_root, account_id)
    if not data.get("posting") or not data.get("session"):
        return

    client = build_user_client(user_id, "posting", account_id)
    account_name = account_display_name(data)
    try:
        await client.start()
        await ensure_account_channel_membership(client)
        while account_data(ensure_user(user_id), account_id).get("posting"):
            if not is_vip_active(user_id):
                break
            data = account_data(ensure_user(user_id), account_id)
            root = ensure_user(user_id)
            settings = posting_settings_for(user_id)
            groups = [normalize_target(item) for item in data.get("groups", []) if normalize_target(item) is not None]
            templates = [
                item
                for item in root.get("templates", [])
                if template_body(item).strip() or str(item.get("file_id") or "").strip()
            ]
            if not groups:
                data["posting"] = False
                save_users()
                await app.send_message(user_id, f"- تم إيقاف النشر في {account_name} لعدم وجود سوبرات محددة.", reply_markup=back("manageGroups"))
                break
            if not templates:
                data["posting"] = False
                save_users()
                await app.send_message(user_id, f"- تم إيقاف النشر في {account_name} لعدم وجود كلايش محفوظة.", reply_markup=back("addTemplate"))
                break

            template_batch = list(templates)
            if settings.get("random_order"):
                random.shuffle(template_batch)

            for template in template_batch:
                if not account_data(ensure_user(user_id), account_id).get("posting"):
                    break
                selected_groups = list(groups)
                if settings.get("random_order"):
                    random.shuffle(selected_groups)

                success_count = 0
                failed: List[str] = []
                semaphore = asyncio.Semaphore({"normal": 10, "safe": 6, "hidden": 3}[settings.get("mode", "safe")])

                async def publish(group: Union[int, str]) -> Tuple[bool, str]:
                    group_name = group_title_for(data, group)
                    async with semaphore:
                        delay_min, delay_max = ANTI_BAN_DELAYS.get(settings.get("mode", "safe"), ANTI_BAN_DELAYS["safe"])
                        await asyncio.sleep(random.uniform(delay_min, delay_max))
                        attempts = max(1, min(int(settings.get("retry_attempts", 3)), 3))
                        for attempt in range(1, attempts + 1):
                            try:
                                await send_template_to_group(client, group, template, group_name)
                                return True, group_name
                            except FloodWait as error:
                                wait_seconds = int(getattr(error, "value", 0) or getattr(error, "x", 0) or 0)
                                await asyncio.sleep(max(wait_seconds, 1) + 1)
                            except (ChatWriteForbidden, PeerIdInvalid):
                                return False, group_name
                            except Exception:
                                if attempt >= attempts:
                                    return False, group_name
                                await asyncio.sleep(settings.get("retry_delay", 3) + (attempt - 1))
                        return False, group_name

                results = await asyncio.gather(*(publish(group) for group in selected_groups))
                for ok, group_name in results:
                    if ok:
                        success_count += 1
                    else:
                        failed.append(group_name)

                register_posting_stats(user_id, account_id, success_count, len(failed))
                append_user_log(
                    user_id,
                    "post_template",
                    account_id,
                    {
                        "template": truncate(template_preview(template), 40),
                        "success": success_count,
                        "failed": len(failed),
                    },
                )
                save_users()

                if success_count == 0:
                    preview = "\n".join(f"- {item}" for item in failed[:8]) if failed else "- لا توجد مجموعات صالحة."
                    await app.send_message(user_id, f"- لم أتمكن من نشر الكليشة الحالية في أي مجموعة ضمن {account_name}.\n{preview}")
                    if not settings.get("skip_failed", True):
                        break

                delay_seconds = max(int(template.get("delay", root.get("default_delay", 60))), MIN_DELAY)
                random_delay = random.randint(int(settings.get("random_delay_min", 0)), int(settings.get("random_delay_max", 0)))
                await asyncio.sleep(delay_seconds + random_delay)
    except asyncio.CancelledError:
        pass
    except Exception as error:
        data = account_data(ensure_user(user_id), account_id)
        data["posting"] = False
        append_user_log(user_id, "posting_error", account_id, {"error": str(error)})
        save_users()
        await app.send_message(user_id, f"- توقف النشر في {account_name} بسبب خطأ:\n{error}")
    finally:
        posting_tasks.pop(posting_key(user_id, account_id), None)
        try:
            await client.stop()
        except Exception:
            pass


@app.on_message(filters.private & (filters.command("start") | filters.regex(r"^/start(?:@\w+)?$")))
async def start(_: Client, message: Message) -> None:
    user_id = message.from_user.id
    ensure_user(user_id)
    if user_id != OWNER_ID:
        subscribed = await subscription_required(message)
        if isinstance(subscribed, str):
            await message.reply(
                f"يجب عليك الاشتراك في قناة البوت أولاً.\n\n@{subscribed}",
                reply_markup=required_subscription_markup(subscribed),
            )
            return
        if not is_vip_active(user_id):
            await message.reply(
                "لا يمكنك استخدام البوت حالياً، يجب عليك شراء اشتراك من المطور",
                reply_markup=developer_contact_markup(),
            )
            return
    save_users()
    try:
        await render_home(message)
    except Exception as error:
        await message.reply("- البوت شغال لكن حصل خطأ أثناء فتح الواجهة الرئيسية.")
        try:
            await app.send_message(OWNER_ID, f"خطأ داخل /start:\n{error}")
        except Exception:
            pass


@app.on_callback_query(filters.regex(r"^toHome$"))
async def to_home(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_home(callback)


@app.on_callback_query(filters.regex(r"^verifySubscription$"))
async def verify_subscription(_: Client, callback: CallbackQuery) -> None:
    if callback.from_user.id != OWNER_ID:
        missing_channel = await missing_subscription_channel(callback.from_user.id)
        if missing_channel:
            await callback.answer(f"لا يزال الاشتراك مطلوباً في @{missing_channel}", show_alert=True)
            await callback.message.edit_text(
                f"يجب عليك الاشتراك في قناة البوت أولاً.\n\n@{missing_channel}",
                reply_markup=required_subscription_markup(missing_channel, back_to_home=True),
            )
            return
        if not is_vip_active(callback.from_user.id):
            await callback.answer("الاشتراك المدفوع غير مفعل بعد.", show_alert=True)
            await callback.message.edit_text(
                "لا يمكنك استخدام البوت حالياً، يجب عليك شراء اشتراك من المطور",
                reply_markup=developer_contact_markup(),
            )
            return
    await callback.answer("- تم التحقق من الاشتراك بنجاح.")
    await render_home(callback)


@app.on_callback_query(filters.regex(r"^botFeatures$"))
async def bot_features(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await callback.message.edit_text(BOT_FEATURES_TEXT, reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^tips$"))
async def bot_tips(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await callback.message.edit_text(TIPS_TEXT, reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^postingSettings$"))
async def render_posting_settings(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    settings = posting_settings_for(callback.from_user.id)
    caption = (
        "⚙️ إعدادات النشر\n\n"
        f"- وضع الحماية: {mode_label(settings.get('mode', 'safe'))}\n"
        f"- الترتيب العشوائي: {'مفعل' if settings.get('random_order') else 'معطل'}\n"
        f"- التأخير العشوائي: {settings.get('random_delay_min', 0)} إلى {settings.get('random_delay_max', 0)} ثانية\n"
        f"- إعادة المحاولة: {settings.get('retry_attempts', 3)}\n"
        f"- تخطي الفاشل: {'مفعل' if settings.get('skip_failed') else 'معطل'}\n\n"
        "أنت المسؤول عن الإعدادات التي تختارها وقد تؤدي السرعة إلى حظر حسابك"
    )
    await callback.message.edit_text(caption, reply_markup=posting_settings_markup(callback.from_user.id))


@app.on_callback_query(filters.regex(r"^postingStats$"))
async def posting_stats(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await callback.message.edit_text(format_stats_caption(callback.from_user.id), reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^postingLogs$"))
async def posting_logs(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    lines: List[str] = []
    for entry in data.get("logs", [])[-15:]:
        details = entry.get("details") or {}
        details_text = ""
        if details:
            details_text = " | " + ", ".join(f"{key}={value}" for key, value in details.items())
        account_text = f" | {entry.get('account')}" if entry.get("account") else ""
        lines.append(f"- {format_dt(parse_dt(entry.get('at')))} | {entry.get('action')}{account_text}{details_text}")
    await callback.message.edit_text("🧾 السجل الأخير\n\n" + ("\n".join(lines) if lines else "- لا توجد عمليات مسجلة بعد."), reply_markup=back("postingSettings"))


@app.on_callback_query(filters.regex(r"^cyclePostingMode$"))
async def cycle_posting_mode(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    settings = posting_settings_for(callback.from_user.id)
    order = ["normal", "safe", "hidden"]
    current = settings.get("mode", "safe")
    settings["mode"] = order[(order.index(current) + 1) % len(order)] if current in order else "safe"
    append_user_log(callback.from_user.id, "change_posting_mode", details={"mode": settings["mode"]})
    save_users()
    await render_posting_settings(_, callback)


@app.on_callback_query(filters.regex(r"^toggleRandomOrder$"))
async def toggle_random_order(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    settings = posting_settings_for(callback.from_user.id)
    settings["random_order"] = not settings.get("random_order", True)
    append_user_log(callback.from_user.id, "toggle_random_order", details={"enabled": settings["random_order"]})
    save_users()
    await render_posting_settings(_, callback)


@app.on_callback_query(filters.regex(r"^toggleSkipFailed$"))
async def toggle_skip_failed(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    settings = posting_settings_for(callback.from_user.id)
    settings["skip_failed"] = not settings.get("skip_failed", True)
    append_user_log(callback.from_user.id, "toggle_skip_failed", details={"enabled": settings["skip_failed"]})
    save_users()
    await render_posting_settings(_, callback)


@app.on_callback_query(filters.regex(r"^setRandomDelay$"))
async def set_random_delay(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    try:
        ask = await listener.listen(
            from_id=callback.from_user.id,
            chat_id=callback.from_user.id,
            text="- أرسل التأخير العشوائي بهذه الصيغة:\nMIN MAX\n\nمثال:\n0 10",
            timeout=120,
            reply_markup=ForceReply(selective=True, placeholder="0 10"),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام التأخير العشوائي.", reply_markup=back("postingSettings"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("postingSettings"))
        return
    parts = ask.text.split()
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        await ask.reply("- الصيغة غير صحيحة. أرسلها هكذا: 0 10", reply_to_message_id=ask.id, reply_markup=back("postingSettings"))
        return
    minimum, maximum = [int(part) for part in parts]
    if maximum < minimum:
        maximum = minimum
    settings = posting_settings_for(callback.from_user.id)
    settings["random_delay_min"] = max(0, minimum)
    settings["random_delay_max"] = max(settings["random_delay_min"], maximum)
    append_user_log(callback.from_user.id, "set_random_delay", details={"min": settings["random_delay_min"], "max": settings["random_delay_max"]})
    save_users()
    await ask.reply("- تم حفظ التأخير العشوائي.", reply_to_message_id=ask.id, reply_markup=back("postingSettings"))


@app.on_callback_query(filters.regex(r"^setRetryAttempts$"))
async def set_retry_attempts(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    try:
        ask = await listener.listen(
            from_id=callback.from_user.id,
            chat_id=callback.from_user.id,
            text="- أرسل عدد المحاولات من 1 إلى 3.",
            timeout=120,
            reply_markup=ForceReply(selective=True, placeholder="3"),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام عدد المحاولات.", reply_markup=back("postingSettings"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("postingSettings"))
        return
    if not ask.text.strip().isdigit():
        await ask.reply("- أرسل رقماً صحيحاً من 1 إلى 3.", reply_to_message_id=ask.id, reply_markup=back("postingSettings"))
        return
    settings = posting_settings_for(callback.from_user.id)
    settings["retry_attempts"] = min(max(int(ask.text.strip()), 1), 3)
    append_user_log(callback.from_user.id, "set_retry_attempts", details={"retry_attempts": settings["retry_attempts"]})
    save_users()
    await ask.reply("- تم حفظ عدد المحاولات.", reply_to_message_id=ask.id, reply_markup=back("postingSettings"))


@app.on_callback_query(filters.regex(r"^account$"))
async def account(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_account(callback)


@app.on_callback_query(filters.regex(r"^(switchAccounts|changeAccount)$"))
async def switch_accounts(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_accounts_switcher(callback)


@app.on_callback_query(filters.regex(r"^switchAccount:acc\d+$"))
async def switch_account(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    account_id = callback.data.split(":", 1)[1]
    if not switch_account_slot(callback.from_user.id, account_id):
        await callback.answer("- هذا الحساب لم يعد موجودًا.", show_alert=True)
        await render_accounts_switcher(callback)
        return
    save_users()
    await callback.answer(f"- تم التبديل إلى {current_account_name(callback.from_user.id)}")
    await render_account(callback)


@app.on_callback_query(filters.regex(r"^login$"))
async def login(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    create_account_slot(callback.from_user.id)
    save_users()
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text=f"- سيتم التسجيل في {current_account_name(callback.from_user.id)}.\n- أرسل رقم الهاتف الخاص بك.\n- أرسل /cancel للإلغاء.", timeout=60, reply_markup=ForceReply(selective=True, placeholder="+9647700000000"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام رقم الهاتف.", reply_markup=back("account"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("account"))
        return
    await registration(ask)


@app.on_callback_query(filters.regex(r"^loginses$"))
async def loginses(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    create_account_slot(callback.from_user.id)
    save_users()
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text=f"- سيتم التسجيل في {current_account_name(callback.from_user.id)}.\n- أرسل كود الجلسة.\n- أرسل /cancel للإلغاء.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="SESSION_STRING"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام كود الجلسة.", reply_markup=back("account"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("account"))
        return
    await registration_via_session(ask)


@app.on_callback_query(filters.regex(r"^deleteCurrentAccount$"))
async def delete_current_account(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    user_id = callback.from_user.id
    data = ensure_user(user_id)
    current_id = active_account_id(data)
    current_name = current_account_name(user_id)
    stop_posting_task(user_id, current_id)
    ensure_ai_config(user_id, current_id)["enabled"] = False
    stop_ai_worker(user_id, current_id)
    delete_account_slot(user_id, current_id)
    save_users()
    await callback.message.edit_text(f"- تم حذف الحساب الحالي بنجاح.\n- الحساب المحذوف: {current_name}", reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^deleteAccount$"))
async def delete_account(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    data["session"] = ""
    data["account_number"] = ""
    data["groups"] = []
    data["available_groups"] = []
    data["last_groups_sync"] = None
    data["templates"] = []
    data["posting"] = False
    stop_posting_task(callback.from_user.id)
    ensure_ai_config(callback.from_user.id)["enabled"] = False
    stop_ai_worker(callback.from_user.id)
    save_users()
    await callback.message.edit_text("- تم حذف الحساب وإعداداته بنجاح.", reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^leaveAllChats$"))
async def leave_all_chats(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    if not data.get("session"):
        await callback.message.edit_text("- لم تسجل حساباً بعد.", reply_markup=back("account"))
        return
    client = build_user_client(callback.from_user.id, "leave")
    total = 0
    try:
        await client.start()
        async for dialog in client.get_dialogs():
            chat_type = getattr(dialog.chat.type, "value", str(dialog.chat.type))
            if chat_type not in {"group", "supergroup", "channel"}:
                continue
            try:
                await client.leave_chat(dialog.chat.id)
                total += 1
            except Exception:
                continue
    finally:
        try:
            await client.stop()
        except Exception:
            pass
    data["groups"] = []
    data["available_groups"] = []
    data["last_groups_sync"] = None
    save_users()
    await callback.message.edit_text(f"- تم مغادرة {total} مجموعة/قناة بنجاح.", reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^(manageGroups|currentSupers)$"))
async def manage_groups(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_groups(callback)


@app.on_callback_query(filters.regex(r"^(refreshGroups|newSuper|newSupers)$"))
async def refresh_groups(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_groups(callback, refresh=True)


@app.on_callback_query(filters.regex(r"^groupsPage:\d+$"))
async def groups_page(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_groups(callback, page=int(callback.data.split(":", 1)[1]))


@app.on_callback_query(filters.regex(r"^toggleGroup:-?\d+:\d+$"))
async def toggle_group(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    _, group_id_text, page_text = callback.data.split(":")
    group_id = int(group_id_text)
    data = ensure_user(callback.from_user.id)
    groups = list(data.get("groups", []))
    if group_id in groups:
        groups.remove(group_id)
        await callback.answer("- تم حذف المجموعة من النشر.")
    else:
        groups.append(group_id)
        await callback.answer("- تم إضافة المجموعة إلى النشر.")
    data["groups"] = dedupe(groups)
    save_users()
    await render_groups(callback, page=int(page_text))


@app.on_callback_query(filters.regex(r"^selectAllGroups$"))
async def select_all_groups(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    data["groups"] = [item["id"] for item in data.get("available_groups", [])]
    save_users()
    await callback.answer("- تم تحديد كل السوبرات.")
    await render_groups(callback)


@app.on_callback_query(filters.regex(r"^clearAllGroups$"))
async def clear_all_groups(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    ensure_user(callback.from_user.id)["groups"] = []
    save_users()
    await callback.answer("- تم إلغاء تحديد كل السوبرات.")
    await render_groups(callback)


@app.on_message(filters.command("ai") & filters.private)
async def ai_command(_: Client, message: Message) -> None:
    user_id = message.from_user.id
    if not await ensure_access(message):
        return
    ensure_ai_config(user_id)
    save_users()
    await render_ai_menu_message(message)


@app.on_message(filters.command("trial") & filters.private)
async def trial_command(_: Client, message: Message) -> None:
    user_id = message.from_user.id
    if user_id == OWNER_ID:
        await message.reply("- أنت مالك البوت ولا تحتاج إلى اشتراك تجريبي.")
        return
    missing_channel = await missing_subscription_channel(user_id)
    if missing_channel:
        await message.reply(
            f"يجب عليك الاشتراك في قناة البوت أولاً.\n\n@{missing_channel}",
            reply_markup=required_subscription_markup(missing_channel),
        )
        return
    data = ensure_user(user_id)
    if is_vip_active(user_id):
        await message.reply("- لديك اشتراك مفعل بالفعل.")
        return
    if data.get("trial_used"):
        await message.reply("لا يمكنك استخدام البوت حالياً، يجب عليك شراء اشتراك من المطور", reply_markup=developer_contact_markup())
        return
    payload = activate_trial(user_id)
    await message.reply(
        "- تم تفعيل الاشتراك التجريبي المجاني لمدة ساعتين.\n\n"
        f"- ينتهي بتاريخ {payload['end_date']} الساعة {payload['endTime']}",
        reply_markup=back("toHome"),
    )


@app.on_callback_query(filters.regex(r"^aiMenu$"))
async def ai_menu(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    ensure_ai_config(callback.from_user.id)
    save_users()
    await render_ai_menu_callback(callback)


@app.on_callback_query(filters.regex(r"^aiEnable$"))
async def ai_enable(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    if not data.get("session"):
        await callback.answer("- لازم تسجل حسابك أولاً.", show_alert=True)
        return
    cfg = ensure_ai_config(callback.from_user.id)
    cfg["enabled"] = True
    save_users()
    start_ai_worker(callback.from_user.id)
    await callback.answer("- تم تشغيل /ai", show_alert=True)
    await render_ai_menu_callback(callback)


@app.on_callback_query(filters.regex(r"^aiDisable$"))
async def ai_disable(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    cfg = ensure_ai_config(callback.from_user.id)
    cfg["enabled"] = False
    save_users()
    stop_ai_worker(callback.from_user.id)
    await callback.answer("- تم إيقاف /ai", show_alert=True)
    await render_ai_menu_callback(callback)


@app.on_callback_query(filters.regex(r"^aiSetReply$"))
async def ai_set_reply(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    try:
        ask = await listener.listen(
            from_id=callback.from_user.id,
            chat_id=callback.from_user.id,
            text="- ارسل الرد الذي تريد من /ai أن يرسله عند المنشن أو الرد.\n- أرسل /cancel للإلغاء.",
            timeout=180,
            reply_markup=ForceReply(selective=True, placeholder="- الرد الجديد"),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الرد.", reply_markup=back("aiMenu"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("aiMenu"))
        return
    cfg = ensure_ai_config(callback.from_user.id)
    cfg["reply"] = ask.text
    save_users()
    await ask.reply("- تم حفظ الرد بنجاح.", reply_to_message_id=ask.id, reply_markup=Markup([[Button("- إعدادات /ai -", callback_data="aiMenu")], [Button("- الصفحة الرئيسية -", callback_data="toHome")]]))


@app.on_callback_query(filters.regex(r"^aiSetUsername$"))
async def ai_set_username(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    try:
        ask = await listener.listen(
            from_id=callback.from_user.id,
            chat_id=callback.from_user.id,
            text="- ارسل يوزر حسابك بدون @ حتى يطابق /ai المنشن داخل المجموعات.\n- أرسل /cancel للإلغاء.",
            timeout=120,
            reply_markup=ForceReply(selective=True, placeholder="- username"),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام اليوزر.", reply_markup=back("aiMenu"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("aiMenu"))
        return
    username = ask.text.strip().lstrip("@")
    if not username:
        await ask.reply("- اليوزر غير صالح.", reply_to_message_id=ask.id, reply_markup=back("aiMenu"))
        return
    cfg = ensure_ai_config(callback.from_user.id)
    cfg["target_username"] = username
    save_users()
    await ask.reply(f"- تم حفظ يوزر المنشن: @{username}", reply_to_message_id=ask.id, reply_markup=Markup([[Button("- إعدادات /ai -", callback_data="aiMenu")], [Button("- الصفحة الرئيسية -", callback_data="toHome")]]))


@app.on_callback_query(filters.regex(r"^(addTemplate|newCaption|newCaption2)$"))
async def add_template(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await prompt_new_template(callback)


@app.on_callback_query(filters.regex(r"^manageTemplates$"))
async def manage_templates(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_templates(callback)


@app.on_callback_query(filters.regex(r"^templatesPage:\d+$"))
async def templates_page(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    await render_templates(callback, page=int(callback.data.split(":", 1)[1]))


@app.on_callback_query(filters.regex(r"^showTemplate:\d+:\d+$"))
async def show_template(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    _, index_text, page_text = callback.data.split(":")
    index = int(index_text)
    page = int(page_text)
    data = ensure_user(callback.from_user.id)
    if index >= len(data.get("templates", [])):
        await callback.answer("- هذه الكليشة لم تعد موجودة.", show_alert=True)
        await render_templates(callback, page=page)
        return
    template = data["templates"][index]
    labels = {"text": "نص", "photo": "صورة", "video": "فيديو", "animation": "GIF", "document": "ملف"}
    caption = (
        f"📝 الكليشة رقم {index + 1}\n\n"
        f"- النوع: {labels.get(str(template.get('kind') or 'text'), 'نص')}\n"
        f"- المحتوى:\n{template_preview(template)}\n\n"
        f"- الوقت بعدها: {template['delay']} ثانية"
    )
    await callback.message.edit_text(
        caption,
        reply_markup=Markup(
            [
                [Button("- تعديل الكليشة -", callback_data=f"editTemplate:{index}:{page}")],
                [Button("- رفع لأعلى -", callback_data=f"moveTemplate:{index}:up:{page}"), Button("- إنزال لأسفل -", callback_data=f"moveTemplate:{index}:down:{page}")],
                [Button("- حذف هذه الكليشة -", callback_data=f"delTemplate:{index}:{page}")],
                [Button("- رجوع للكلايش -", callback_data=f"templatesPage:{page}")],
            ]
        ),
    )


@app.on_callback_query(filters.regex(r"^moveTemplate:\d+:(up|down):\d+$"))
async def move_template(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    _, index_text, direction, page_text = callback.data.split(":")
    index = int(index_text)
    page = int(page_text)
    data = ensure_user(callback.from_user.id)
    templates = data.get("templates", [])
    if index >= len(templates):
        await callback.answer("- هذه الكليشة لم تعد موجودة.", show_alert=True)
        await render_templates(callback, page=page)
        return
    swap_with = index - 1 if direction == "up" else index + 1
    if swap_with < 0 or swap_with >= len(templates):
        await callback.answer("- لا يمكن نقل الكليشة أكثر.", show_alert=True)
        return
    templates[index], templates[swap_with] = templates[swap_with], templates[index]
    append_user_log(callback.from_user.id, "move_template", details={"from": index + 1, "to": swap_with + 1})
    save_users()
    await callback.answer("- تم تحديث ترتيب الكليشة.")
    await render_templates(callback, page=page)


@app.on_callback_query(filters.regex(r"^editTemplate:\d+:\d+$"))
async def edit_template(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    _, index_text, page_text = callback.data.split(":")
    index = int(index_text)
    page = int(page_text)
    data = ensure_user(callback.from_user.id)
    templates = data.get("templates", [])
    if index >= len(templates):
        await callback.answer("- هذه الكليشة لم تعد موجودة.", show_alert=True)
        await render_templates(callback, page=page)
        return
    template = dict(templates[index])
    try:
        ask_content = await listener.listen(
            from_id=callback.from_user.id,
            chat_id=callback.from_user.id,
            text="📝 تعديل الكليشة\n\nأرسل النص أو الوسائط الجديدة الآن.\n- لإبقاء المحتوى الحالي أرسل /skip\n- للإلغاء أرسل /cancel",
            timeout=300,
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_prompt_markup(),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام التعديل.", reply_markup=back(f"showTemplate:{index}:{page}"))
        return
    if ask_content is None:
        return
    if (ask_content.text or "").strip() == "/cancel":
        await ask_content.reply("- تم إلغاء العملية.", reply_to_message_id=ask_content.id, reply_markup=back(f"showTemplate:{index}:{page}"))
        return
    if (ask_content.text or "").strip() != "/skip":
        if not any([ask_content.text, ask_content.photo, ask_content.video, ask_content.animation, ask_content.document]):
            await ask_content.reply("- أرسل نصاً أو صورة أو فيديو أو GIF أو ملفاً.", reply_to_message_id=ask_content.id, reply_markup=back(f"showTemplate:{index}:{page}"))
            return
        template.update(build_template_payload(ask_content, int(template.get("delay", MIN_DELAY))))

    try:
        ask_delay = await listener.listen(
            from_id=callback.from_user.id,
            chat_id=callback.from_user.id,
            text=f"- أرسل الوقت الجديد بالثواني.\n- لإبقاء الوقت الحالي ({template.get('delay', MIN_DELAY)} ثانية) أرسل /skip",
            timeout=120,
            reply_markup=cancel_prompt_markup(),
        )
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الوقت.", reply_markup=back(f"showTemplate:{index}:{page}"))
        return
    if ask_delay is None:
        return
    if ask_delay.text.strip() == "/cancel":
        await ask_delay.reply("- تم إلغاء العملية.", reply_to_message_id=ask_delay.id, reply_markup=back(f"showTemplate:{index}:{page}"))
        return
    if ask_delay.text.strip() != "/skip":
        if not ask_delay.text.strip().isdigit():
            await ask_delay.reply("- الوقت يجب أن يكون رقماً صحيحاً.", reply_to_message_id=ask_delay.id, reply_markup=back(f"showTemplate:{index}:{page}"))
            return
        template["delay"] = max(int(ask_delay.text.strip()), MIN_DELAY)

    templates[index] = template
    append_user_log(callback.from_user.id, "edit_template", details={"index": index + 1})
    save_users()
    await ask_delay.reply("- تم تحديث الكليشة بنجاح.", reply_to_message_id=ask_delay.id, reply_markup=back(f"showTemplate:{index}:{page}"))


@app.on_callback_query(filters.regex(r"^delTemplate:\d+:\d+$"))
async def del_template(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    _, index_text, page_text = callback.data.split(":")
    index = int(index_text)
    page = int(page_text)
    data = ensure_user(callback.from_user.id)
    if index < len(data.get("templates", [])):
        data["templates"].pop(index)
        save_users()
        await callback.answer("- تم حذف الكليشة.")
    else:
        await callback.answer("- هذه الكليشة غير موجودة.", show_alert=True)
    await render_templates(callback, page=page)


@app.on_callback_query(filters.regex(r"^waitTime$"))
async def set_default_delay(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text=f"- أرسل المدة الافتراضية للكلايش الجديدة بالثواني.\n- أقل مدة مسموحة هي {MIN_DELAY}.\n- أرسل /cancel للإلغاء.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="- 60"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام المدة.", reply_markup=back("toHome"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("toHome"))
        return
    try:
        delay = int(ask.text.strip())
    except ValueError:
        await ask.reply("- المدة يجب أن تكون رقماً صحيحاً.", reply_to_message_id=ask.id, reply_markup=back("toHome"))
        return
    if delay < MIN_DELAY:
        await ask.reply(f"- أقل مدة مسموحة هي {MIN_DELAY} ثوانٍ.", reply_to_message_id=ask.id, reply_markup=back("toHome"))
        return
    ensure_user(callback.from_user.id)["default_delay"] = delay
    save_users()
    await ask.reply("- تم حفظ المدة الافتراضية بنجاح.", reply_to_message_id=ask.id, reply_markup=back("toHome"))


@app.on_callback_query(filters.regex(r"^(startPosting|startPosting2)$"))
async def start_posting(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    if not data.get("session"):
        await callback.answer("- عليك تسجيل حساب أولاً.", show_alert=True)
        return
    if not data.get("groups"):
        await callback.answer("- عليك تحديد السوبرات أولاً.", show_alert=True)
        return
    if not data.get("templates"):
        await callback.answer("- عليك إضافة كليشة واحدة على الأقل.", show_alert=True)
        return
    if data.get("posting"):
        await callback.answer("- النشر مفعل بالفعل.", show_alert=True)
        return
    settings = posting_settings_for(callback.from_user.id)
    caption = (
        "⚠️ تأكيد بدء النشر\n\n"
        "أنت المسؤول عن الإعدادات التي تختارها وقد تؤدي السرعة إلى حظر حسابك\n\n"
        f"- الحساب: {current_account_name(callback.from_user.id)}\n"
        f"- وضع الحماية: {mode_label(settings.get('mode', 'safe'))}\n"
        f"- الترتيب العشوائي: {'مفعل' if settings.get('random_order') else 'معطل'}\n"
        f"- التأخير العشوائي: {settings.get('random_delay_min', 0)} إلى {settings.get('random_delay_max', 0)} ثانية\n"
        f"- إعادة المحاولة: {settings.get('retry_attempts', 3)}"
    )
    await callback.message.edit_text(
        caption,
        reply_markup=Markup(
            [
                [Button("- تأكيد البدء -", callback_data="confirmStartPosting"), Button("- إعدادات النشر -", callback_data="postingSettings")],
                [Button("- إلغاء -", callback_data="toHome")],
            ]
        ),
    )


@app.on_callback_query(filters.regex(r"^confirmStartPosting$"))
async def confirm_start_posting(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    if data.get("posting"):
        await callback.answer("- النشر مفعل بالفعل.", show_alert=True)
        return
    data["posting"] = True
    reset_session_stats(callback.from_user.id)
    stats_for(callback.from_user.id)["session"]["runs"] += 1
    stats_for(callback.from_user.id)["total"]["runs"] += 1
    append_user_log(callback.from_user.id, "start_posting", active_account_id(ensure_user(callback.from_user.id)))
    save_users()
    start_posting_task(callback.from_user.id)
    await callback.message.edit_text(
        f"- تم بدء النشر بنجاح على {current_account_name(callback.from_user.id)}.",
        reply_markup=Markup([[Button("- إيقاف النشر -", callback_data="stopPosting")], [Button("- رجوع -", callback_data="toHome")]]),
    )


@app.on_callback_query(filters.regex(r"^(stopPosting|stopPosting2)$"))
async def stop_posting(_: Client, callback: CallbackQuery) -> None:
    if not await ensure_access(callback):
        return
    data = ensure_user(callback.from_user.id)
    if not data.get("posting"):
        await callback.answer("- النشر متوقف بالفعل.", show_alert=True)
        return
    data["posting"] = False
    append_user_log(callback.from_user.id, "stop_posting", active_account_id(ensure_user(callback.from_user.id)))
    stop_posting_task(callback.from_user.id)
    save_users()
    await callback.message.edit_text("- تم إيقاف النشر.", reply_markup=Markup([[Button("- بدء النشر -", callback_data="startPosting")], [Button("- رجوع -", callback_data="toHome")]]))


async def owner_filter(_: Any, __: Client, update: Union[Message, CallbackQuery]) -> bool:
    return bool(update.from_user and update.from_user.id in OWNERS)


is_owner = filters.create(owner_filter)


async def vip_manager_filter(_: Any, __: Client, update: Union[Message, CallbackQuery]) -> bool:
    return bool(update.from_user and is_vip_manager_id(update.from_user.id))


is_vip_manager = filters.create(vip_manager_filter)


def parse_vip_request(text: str) -> Optional[Tuple[int, int]]:
    parts = text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    user_id = int(parts[0])
    days = int(parts[1])
    if days < 1:
        return None
    return user_id, days


@app.on_message(filters.command("admin") & filters.private & is_vip_manager)
@app.on_callback_query(filters.regex(r"^toAdmin$") & is_vip_manager)
async def admin_panel(_: Client, update: Union[Message, CallbackQuery]) -> None:
    is_owner_user = int(update.from_user.id) == OWNER_ID
    caption = (
        f"مرحبا عزيزي {update.from_user.first_name} في {'لوحة المالك' if is_owner_user else 'لوحة الأدمن'}\n\n"
        "- يمكنك تفعيل الاشتراك مباشرة أيضاً بإرسال:\n"
        "`234562354 1`\n"
        "- أي: ايدي المستخدم ثم عدد الأيام."
    )
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(caption, reply_markup=admin_markup(update.from_user.id))
    else:
        await update.reply(caption, reply_markup=admin_markup(update.from_user.id), reply_to_message_id=update.id)


@app.on_message(filters.private & is_vip_manager & ~filters.command(["start", "admin"]) & ~filters.reply, group=5)
async def quick_vip(_: Client, message: Message) -> None:
    parsed = parse_vip_request(message.text.strip())
    if not parsed:
        return
    target_id, days = parsed
    payload = activate_vip(target_id, days)
    await message.reply(
        "- تم تفعيل اشتراك VIP جديد\n\n"
        f"- تاريخ البدء: {payload['current_date']}\n"
        f"- تاريخ الانتهاء: {payload['end_date']}\n"
        f"- وقت الانتهاء: {payload['endTime']}",
        reply_markup=back("toAdmin"),
    )
    try:
        await app.send_message(target_id, f"- تم تفعيل اشتراك VIP لك حتى {payload['end_date']} الساعة {payload['endTime']}.")
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^addVIP$") & is_vip_manager)
async def add_vip(_: Client, callback: CallbackQuery) -> None:
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text="- أرسل البيانات بهذا الشكل:\n\nID DAYS\n\nمثال:\n764678765 1", timeout=120, reply_markup=ForceReply(selective=True, placeholder="- 764678765 1"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام البيانات.", reply_markup=back("toAdmin"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    parsed = parse_vip_request(ask.text.strip())
    if not parsed:
        await ask.reply("- الصيغة غير صحيحة. ارسلها هكذا: ID DAYS", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    target_id, days = parsed
    payload = activate_vip(target_id, days)
    await ask.reply(f"- تم التفعيل بنجاح.\n- ينتهي بتاريخ {payload['end_date']} الساعة {payload['endTime']}", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
    try:
        await app.send_message(target_id, f"- تم تفعيل اشتراك VIP لك حتى {payload['end_date']} الساعة {payload['endTime']}.")
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^cancelVIP$") & is_vip_manager)
async def cancel_vip(_: Client, callback: CallbackQuery) -> None:
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text="- أرسل ايدي المستخدم لإلغاء اشتراكه.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="- 764678765"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الايدي.", reply_markup=back("toAdmin"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    if not ask.text.strip().isdigit():
        await ask.reply("- الايدي غير صحيح.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    target_id = int(ask.text.strip())
    data = ensure_user(target_id)
    if not data.get("vip"):
        await ask.reply("- هذا المستخدم لا يملك اشتراكاً مفعلاً.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    data["vip"] = False
    data["vip_until"] = None
    data["limitation"] = {}
    for account_id in list(data.get("accounts", {}).keys()):
        account = account_data(data, account_id)
        account["posting"] = False
        stop_posting_task(target_id, account_id)
        ensure_ai_config(target_id, account_id)["enabled"] = False
        stop_ai_worker(target_id, account_id)
    expose_active_account(data)
    append_user_log(target_id, "cancel_vip")
    save_users()
    await ask.reply("- تم إلغاء اشتراك المستخدم بنجاح.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
    try:
        await app.send_message(target_id, "- تم إلغاء اشتراك VIP الخاص بك.")
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^addAdmin$") & is_owner)
async def add_admin(_: Client, callback: CallbackQuery) -> None:
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text="- أرسل ايدي المستخدم الذي تريد إضافته كأدمن.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="123456789"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الايدي.", reply_markup=back("toAdmin"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    if not ask.text.strip().isdigit():
        await ask.reply("- الايدي غير صحيح.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    target_id = int(ask.text.strip())
    if target_id == OWNER_ID:
        await ask.reply("- المالك لا يحتاج إلى إضافته كأدمن.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    if target_id not in admins:
        admins.append(target_id)
        admins.sort()
        save_admins()
    await ask.reply("- تم إضافة الأدمن بنجاح.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^removeAdmin$") & is_owner)
async def remove_admin(_: Client, callback: CallbackQuery) -> None:
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text="- أرسل ايدي الأدمن الذي تريد حذفه.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="123456789"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الايدي.", reply_markup=back("toAdmin"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    if not ask.text.strip().isdigit():
        await ask.reply("- الايدي غير صحيح.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    target_id = int(ask.text.strip())
    if target_id in admins:
        admins.remove(target_id)
        save_admins()
        await ask.reply("- تم حذف الأدمن بنجاح.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))
        return
    await ask.reply("- هذا الايدي ليس ضمن قائمة الأدمن.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^listAdmins$") & is_owner)
async def list_admins(_: Client, callback: CallbackQuery) -> None:
    lines = [f"- {admin_id}" for admin_id in admins] or ["- لا يوجد أدمن حالياً."]
    await callback.message.edit_text("قائمة الأدمن:\n\n" + "\n".join(lines), reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^channels$") & is_owner)
async def channels_panel(_: Client, callback: CallbackQuery) -> None:
    rows = [[Button(f"@{MANDATORY_BOT_CHANNEL} (إجباري)", url=f"https://t.me/{MANDATORY_BOT_CHANNEL}")]]
    rows.extend([[Button(f"@{channel}", url=f"https://t.me/{channel}"), Button("🗑", callback_data=f"removeChannel:{channel}")] for channel in channels if channel != MANDATORY_BOT_CHANNEL])
    rows.append([Button("- إضافة قناة جديدة -", callback_data="addChannel")])
    rows.append([Button("- الصفحة الرئيسية -", callback_data="toAdmin")])
    await callback.message.edit_text("لوحة التحكم بقنوات الاشتراك", reply_markup=Markup(rows))


@app.on_callback_query(filters.regex(r"^addChannel$") & is_owner)
async def add_channel(_: Client, callback: CallbackQuery) -> None:
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text="- أرسل معرف القناة دون @.", timeout=60, reply_markup=ForceReply(selective=True, placeholder="- channel_username"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام المعرف.", reply_markup=back("channels"))
        return
    if ask.text.strip() == "/cancel":
        await ask.reply("- تم إلغاء العملية.", reply_to_message_id=ask.id, reply_markup=back("channels"))
        return
    channel = normalize_channel(ask.text)
    if not channel:
        await ask.reply("- المعرف غير صحيح.", reply_to_message_id=ask.id, reply_markup=back("channels"))
        return
    try:
        await app.get_chat(channel)
    except Exception:
        await ask.reply("- لم يتم العثور على هذه القناة.", reply_to_message_id=ask.id, reply_markup=back("channels"))
        return
    if channel not in channels:
        channels.append(channel)
        save_channels()
    await ask.reply("- تم إضافة القناة بنجاح.", reply_to_message_id=ask.id, reply_markup=back("channels"))


@app.on_callback_query(filters.regex(r"^removeChannel:.+$") & is_owner)
async def remove_channel(_: Client, callback: CallbackQuery) -> None:
    channel = callback.data.split(":", 1)[1]
    if channel in channels:
        channels.remove(channel)
        save_channels()
    await channels_panel(_, callback)


@app.on_callback_query(filters.regex(r"^sendFiles$") & is_owner)
async def send_files(_: Client, callback: CallbackQuery) -> None:
    await app.send_document(callback.from_user.id, USERS_DB, caption="users.json")
    await app.send_document(callback.from_user.id, CHANNELS_DB, caption="channels.json")
    await app.send_document(callback.from_user.id, ADMINS_DB, caption="admins.json")
    await callback.answer("- تم إرسال ملفات التخزين.")


@app.on_callback_query(filters.regex(r"^broadcast$") & is_owner)
async def broadcast(_: Client, callback: CallbackQuery) -> None:
    try:
        ask = await listener.listen(from_id=callback.from_user.id, chat_id=callback.from_user.id, text="- أرسل الرسالة التي تريد إذاعتها.", timeout=120, reply_markup=ForceReply(selective=True, placeholder="- Broadcast"))
    except exceptions.TimeOut:
        await callback.message.reply("- انتهى وقت استلام الرسالة.", reply_markup=back("toAdmin"))
        return
    delivered = 0
    for user_id in list(users.keys()):
        try:
            await app.send_message(int(user_id), ask.text)
            delivered += 1
        except Exception:
            continue
    await ask.reply(f"- تم إرسال الإذاعة إلى {delivered} مستخدم.", reply_to_message_id=ask.id, reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^viewUsers$") & is_owner)
async def view_users(_: Client, callback: CallbackQuery) -> None:
    lines = []
    for user_id in users:
        data = ensure_user(user_id)
        lines.append(f"{user_id} | VIP: {'مفعل' if is_vip_active(user_id) else 'معطل'} | Groups: {len(data.get('groups', []))} | Templates: {len(data.get('templates', []))}")
    await callback.message.edit_text("المستخدمون:\n\n" + ("\n".join(lines) if lines else "- لا يوجد مستخدمون."), reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^viewsession$") & is_owner)
async def view_session(_: Client, callback: CallbackQuery) -> None:
    lines = [f"{user_id} | {'موجودة' if ensure_user(user_id).get('session') else 'غير موجودة'} | {ensure_user(user_id).get('account_number') or 'غير معروف'}" for user_id in users]
    await callback.message.edit_text("الجلسات:\n\n" + ("\n".join(lines) if lines else "- لا توجد بيانات."), reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^viewcaption$") & is_owner)
async def view_templates(_: Client, callback: CallbackQuery) -> None:
    lines = []
    for user_id in users:
        data = ensure_user(user_id)
        previews = ", ".join(truncate(template_preview(item), 20) for item in data.get("templates", [])[:3]) or "لا توجد"
        lines.append(f"{user_id} | Templates: {len(data.get('templates', []))} | {previews}")
    await callback.message.edit_text("الكلايش:\n\n" + ("\n".join(lines) if lines else "- لا توجد بيانات."), reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^statics$") & is_owner)
async def statics(_: Client, callback: CallbackQuery) -> None:
    total = len(users)
    active_vip = sum(1 for user_id in users if is_vip_active(user_id))
    active_sessions = sum(1 for user_id in users if ensure_user(user_id).get("session"))
    await callback.message.edit_text(f"- عدد المستخدمين الكلي: {total}\n- عدد مستخدمي VIP الحاليين: {active_vip}\n- عدد الحسابات المسجلة: {active_sessions}\n- عدد قنوات الاشتراك: {len(required_channels_list())}\n- عدد الأدمن: {len(admins)}", reply_markup=back("toAdmin"))


@app.on_callback_query(filters.regex(r"^(account_settings|account_settings1)$"))
async def disabled_old_feature(_: Client, callback: CallbackQuery) -> None:
    await callback.answer("- هذه الميزة القديمة أوقفت مؤقتاً بعد إعادة تنظيم البوت.", show_alert=True)


@app.on_callback_query(filters.regex(r"^noop$"))
async def noop(_: Client, callback: CallbackQuery) -> None:
    await callback.answer()


@app.on_message(filters.private & ~filters.command(["start", "admin"]) & ~filters.reply & ~is_owner, group=99)
async def ack(_: Client, message: Message) -> None:
    if message.from_user and message.from_user.is_bot:
        return
    if not await ensure_access(message):
        return
    await message.reply("- تم استلام رسالتك ✅")


async def restore_runtime() -> None:
    ensure_owner()
    for user_id in list(users.keys()):
        ensure_user(user_id)
    save_users()
    for user_id in list(users.keys()):
        if int(user_id) != OWNER_ID and not is_vip_active(user_id):
            continue
        if ensure_user(user_id).get("posting"):
            start_posting_task(user_id)
        if ensure_ai_config(user_id).get("enabled") and ensure_user(user_id).get("session"):
            start_ai_worker(user_id)


async def vip_watcher() -> None:
    while True:
        for user_id in list(users.keys()):
            if int(user_id) == OWNER_ID:
                continue
            data = ensure_user(user_id)
            vip_until = parse_dt(data.get("vip_until"))
            if data.get("vip") and vip_until and vip_until <= now_local():
                data["vip"] = False
                data["vip_until"] = None
                data["limitation"] = {}
                data["posting"] = False
                stop_posting_task(user_id)
                ensure_ai_config(user_id)["enabled"] = False
                stop_ai_worker(user_id)
                save_users()
                try:
                    await app.send_message(int(user_id), "- انتهى اشتراك VIP الخاص بك.\n- راسل المطور إذا كنت تريد تجديد اشتراكك.")
                except Exception:
                    pass
        await asyncio.sleep(60)


async def restore_runtime() -> None:
    ensure_owner()
    for user_id in list(users.keys()):
        ensure_user(user_id)
    save_users()
    for user_id in list(users.keys()):
        if int(user_id) != OWNER_ID and not is_vip_active(user_id):
            continue
        data = ensure_user(user_id)
        for account_id in sorted(data.get("accounts", {}).keys(), key=account_sort_key):
            account = account_data(data, account_id)
            if account.get("posting"):
                start_posting_task(user_id, account_id)
            if ensure_ai_config(user_id, account_id).get("enabled") and account.get("session"):
                start_ai_worker(user_id, account_id)


async def vip_watcher() -> None:
    while True:
        for user_id in list(users.keys()):
            if int(user_id) == OWNER_ID:
                continue
            data = ensure_user(user_id)
            vip_until = parse_dt(data.get("vip_until"))
            if data.get("vip") and vip_until and vip_until <= now_local():
                data["vip"] = False
                data["vip_until"] = None
                data["limitation"] = {}
                for account_id in list(data.get("accounts", {}).keys()):
                    account = account_data(data, account_id)
                    account["posting"] = False
                    stop_posting_task(user_id, account_id)
                    ensure_ai_config(user_id, account_id)["enabled"] = False
                    stop_ai_worker(user_id, account_id)
                expose_active_account(data)
                save_users()
                try:
                    await app.send_message(int(user_id), "- انتهى اشتراك VIP الخاص بك.\n- راسل المطور إذا كنت تريد تجديد اشتراكك.")
                except Exception:
                    pass
        await asyncio.sleep(60)


async def start_app_with_retry() -> None:
    set_bot_status("starting")
    while True:
        try:
            await app.start()
            set_bot_status("running")
            return
        except FloodWait as error:
            wait_seconds = int(getattr(error, "value", 0) or getattr(error, "x", 0) or 0)
            if wait_seconds <= 0:
                raise
            retry_at = now_local() + timedelta(seconds=wait_seconds)
            set_bot_status(
                "flood_wait",
                {
                    "wait_seconds": wait_seconds,
                    "retry_at": retry_at.isoformat(),
                },
            )
            print(
                f"FloodWait عند تشغيل البوت: سيتم إعادة المحاولة بعد {wait_seconds} ثانية "
                f"في {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await asyncio.sleep(wait_seconds + 1)


async def main() -> None:
    ensure_owner()
    final_state = "stopped"
    final_details: Dict[str, Any] = {}
    try:
        await start_app_with_retry()
        await restore_runtime()
        asyncio.create_task(vip_watcher())
        if not TGCRYPTO_INSTALLED:
            print("TgCrypto is not installed. The bot will still work, but slower. Install it with: pip install TgCrypto")
        await idle()
    except Exception as error:
        final_state = "crashed"
        final_details = {"error": str(error)}
        raise
    finally:
        try:
            await app.stop()
        except Exception:
            pass
        set_bot_status(final_state, final_details)


if __name__ == "__main__":
    MAIN_LOOP.run_until_complete(main())
