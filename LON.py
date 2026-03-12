import json
import logging
import math
import re
import time
import asyncio
import html
from typing import Dict, List, Tuple

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------- إعداد اللوق ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

import os
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 1411672636
COLLECTION_ADDRESS = "EQAg556MaTsIRDH-NUHOyzQ5WsKBdD9OFXBp8cMsuUxlX5dV" # عنوان مجموعة Pepe-Sim NFT
USERS_FILE = "allowed_users.json"
DEBUG_TG_API = True


def tg_api(method: str, payload: Dict) -> Dict:
    """
    نستخدم Bot API مباشرة حتى لا تقوم المكتبات بتجاهل الحقول الجديدة
    مثل: style / icon_custom_emoji_id.
    """
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    if DEBUG_TG_API and method in {"sendMessage", "editMessageText"}:
        result = data.get("result") or {}
        markup = result.get("reply_markup") or {}
        inline_kb = markup.get("inline_keyboard") or []
        any_icon = any(
            isinstance(btn, dict) and ("icon_custom_emoji_id" in btn)
            for row in inline_kb
            if isinstance(row, list)
            for btn in row
        )
        any_style = any(
            isinstance(btn, dict) and ("style" in btn)
            for row in inline_kb
            if isinstance(row, list)
            for btn in row
        )
        logging.info(
            "TG_API %s ok; reply_markup: buttons=%s icon=%s style=%s",
            method,
            sum(len(row) for row in inline_kb if isinstance(row, list)),
            any_icon,
            any_style,
        )
    return data

# حالات المحادثة لإضافة المستخدمين
ADD_USER_ID = 1

# ---------- إيموجي مميز (Premium/Custom Emoji) ----------
# ضع الـ IDs هنا. إذا تركته فارغ "" سيتم تجاهل الإيموجي ويعمل البوت طبيعي.
CUSTOM_EMOJI: Dict[str, str] = {
    "WELCOME": "",
    "AVAILABLE": "6296367896398399651",
    "SOLD": "6298671811345254603",
    "RESERVED": "5791724597921453986",
    "FILTER": "5803348359972393936",
    "NEXT": "6001504647632654909",
    "PREV": "6001215342930565066",
    "BACK": "5938487727824574689",
    "ASC": "6001316880252410036",
    "DESC": "6001311563082897619",
    "NORMAL": "5951811553895388029",
    "REP_A": "5951779294396028785",
    "REP_B": "5951940647727403709",
    "ADD_USER": "5258362837411045098",
}


def tg_emoji(emoji_id: str, fallback: str) -> str:
    if not emoji_id:
        return fallback
    return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"


# ---------- أزرار ملوّنة (Bot API 9.4+) ----------
def _button_style(text: str, callback_data: str | None) -> str:
    t = (text or "").lower()
    cd = (callback_data or "").lower()

    # زر "محجوز" بدون لون (بدون style)
    if "محجوز" in (text or ""):
        return ""

    # رجوع/إلغاء
    if any(k in t for k in ("العودة", "رجوع", "back", "cancel", "إلغاء")) or cd in {"main_menu", "cancel"}:
        return "danger"   # أحمر

    # إيجابي/متوفر
    if any(k in t for k in ("متوفر", "نعم", "yes", "ok", "تأكيد")):
        return "success"  # أخضر

    # تحذير/رفض
    if any(k in t for k in ("مباع", "لا", "no", "حذف", "delete")):
        return "danger"   # أحمر

    return "primary"      # أزرق


def btn(
    text: str,
    callback_data: str,
    style: str | None = None,
    icon_custom_emoji_id: str | None = None,
) -> Dict[str, str]:
    resolved_style = style if style is not None else _button_style(text, callback_data)
    payload: Dict[str, str] = {
        "text": text,
        "callback_data": callback_data,
    }
    if icon_custom_emoji_id:
        payload["icon_custom_emoji_id"] = icon_custom_emoji_id
    if resolved_style:
        payload["style"] = resolved_style
    return payload


def inline_markup(rows: List[List[Dict[str, str]]]) -> Dict[str, List[List[Dict[str, str]]]]:
    return {"inline_keyboard": rows}

# متغيرات لتخزين البيانات مؤقتاً (Caching)
cached_available_numbers: List[Tuple[str, float]] = []
cached_sold_numbers: List[str] = []
last_fetch_time: float = 0
FETCH_INTERVAL = 3600  # جلب البيانات كل ساعة (3600 ثانية)

# ---------- تخزين/قراءة المستخدمين المصرح لهم ----------
def load_allowed() -> List[int]:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_allowed(ids: List[int]) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f)

allowed_ids = set(load_allowed())


# ---------- مساعدة لجلب الأرقام من TonAPI ----------
async def fetch_numbers_from_tonapi() -> None:
    """
    تجلب الأرقام المتاحة والمباعة من TonAPI وتخزنها مؤقتاً.
    """
    global cached_available_numbers, cached_sold_numbers, last_fetch_time

    current_available = []
    current_sold = []
    limit = 1000  # الحد الأقصى للعناصر في كل طلب
    offset = 0

    logging.info("بدء جلب البيانات من TonAPI...")

    while True:
        url = f"https://tonapi.io/v2/nfts/collections/{COLLECTION_ADDRESS}/items?limit={limit}&offset={offset}"
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            items = data.get("nft_items", [])

            if not items:
                break
            
            for item in items:
                name = item.get("metadata", {}).get("name", "Unknown")
                sale = item.get("sale")
                if sale and sale.get("price"):
                    price_raw = sale["price"].get("value")
                    if price_raw:
                        price = float(price_raw) / 10**9
                        # تجاهل الأرقام التي بدون سعر 0.0
                        if price > 0:
                            current_available.append((name, price))
                else:
                    current_sold.append(name)
            
            logging.info(f"تم جلب {len(items)} عنصر، الإجمالي المتاح: {len(current_available)}، الإجمالي المباع: {len(current_sold)}")
            offset += limit
            await asyncio.sleep(0.5)

        except Exception as e:
            logging.error(f"خطأ في جلب البيانات: {e}")
            return
    
    cached_available_numbers = current_available
    cached_sold_numbers = current_sold
    last_fetch_time = time.time()


async def ensure_data_is_fresh() -> None:
    """
    يتأكد من أن البيانات حديثة، ويقوم بجلبها إذا لزم الأمر.
    """
    global last_fetch_time
    if time.time() - last_fetch_time > FETCH_INTERVAL or not cached_available_numbers:
        await fetch_numbers_from_tonapi()


# ---------- تنسيق العرض مع الربح 88٪ ----------
def sale_price(orig: float) -> float:
    return round(orig * 1.88, 2)


def make_page(items: List[str], typ: str, page: int, per_page: int = 6) -> Tuple[str, Dict]:
    """
    تُعيد نص الصفحة والكيبورد مع أزرار السابق/التالي.
    """
    start = page * per_page
    chunk = items[start : start + per_page]
    if chunk:
        # تنسيق مثل الصورة: السطر 1 داخل blockquote، 2 عادي، 3 blockquote، 4 عادي، ...
        parts: List[str] = []
        for idx, line in enumerate(chunk):
            safe = html.escape(line)
            if idx % 2 == 0:
                parts.append(f"<blockquote>{safe}</blockquote>")
            else:
                parts.append(safe)
        text = "\n".join(parts)
    else:
        text = "لا توجد بيانات."

    kb = []
    row = []
    if page > 0:
        row.append(
            btn(
                "◀️ السابق",
                callback_data=f"show:{typ}:{page-1}",
                style="danger",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("PREV") or None,
            )
        )
    if start + per_page < len(items):
        row.append(
            btn(
                "التالي ▶️",
                callback_data=f"show:{typ}:{page+1}",
                style="success",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("NEXT") or None,
            )
        )
    if row:
        kb.append(row)
    
    kb.append(
        [
            btn(
                "العودة للقائمة الرئيسية",
                callback_data="main_menu",
                style="primary",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("BACK") or None,
            )
        ]
    )

    return text, inline_markup(kb)


# ---------- وظائف الفلترة المحدثة ----------

def filter_normal_cheapest(numbers: List[Tuple[str, float]]) -> List[str]:
    # الأرقام التي تنتهي بـ 5 من الأرخص للأغلى
    filtered = [(n, p) for n, p in numbers if n.endswith('5')]
    filtered.sort(key=lambda x: x[1])
    return [f"{n} < {sale_price(p)} >" for n, p in filtered]

def filter_repeated_a(numbers: List[Tuple[str, float]]) -> List[str]:
    # مكرر A (حسب المثال: +999 1547 7101): رقمين مختلفين كل منهما مكرر مرتين على الأقل
    res = []
    for n, p in numbers:
        digits = re.sub(r'\D', '', n[4:]) # استخراج الأرقام بعد +999
        counts = {}
        for d in digits:
            counts[d] = counts.get(d, 0) + 1
        repeated_twice = [d for d, c in counts.items() if c >= 2]
        if len(repeated_twice) >= 2:
            res.append(f"{n} < {sale_price(p)} >")
    return res

def filter_repeated_b(numbers: List[Tuple[str, float]]) -> List[str]:
    # مكرر B (حسب المثال: +999 1547 7308): رقم واحد مكرر مرتين متتاليتين
    res = []
    for n, p in numbers:
        digits = re.sub(r'\D', '', n[4:])
        if any(digits[i] == digits[i+1] for i in range(len(digits)-1)):
            res.append(f"{n} < {sale_price(p)} >")
    return res

def filter_ascending(numbers: List[Tuple[str, float]]) -> List[str]:
    # تصاعدي من الادنى الى الاعلا
    sorted_nums = sorted(numbers, key=lambda x: x[1])
    return [f"{n} < {sale_price(p)} >" for n, p in sorted_nums]

def filter_descending(numbers: List[Tuple[str, float]]) -> List[str]:
    # تنازلي من الاعلا الى الادنى
    sorted_nums = sorted(numbers, key=lambda x: x[1], reverse=True)
    return [f"{n} < {sale_price(p)} >" for n, p in sorted_nums]


# ---------- الـ Handlers ----------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in allowed_ids and user.id != OWNER_ID:
        tg_api("sendMessage", {"chat_id": update.effective_chat.id, "text": "عذراً، لا تملك صلاحية استخدام هذا البوت."})
        return

    keyboard = [
        [
            btn(
                "متوفر 🟢",
                callback_data="show:available:0",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("AVAILABLE") or None,
            ),
            btn(
                "مباع 🔴",
                callback_data="show:sold:0",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("SOLD") or None,
            ),
        ],
        [
            btn(
                "فلتره ⚙️",
                callback_data="filter_menu",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("FILTER") or None,
            ),
            btn(
                "محجوز ⏱️",
                callback_data="show:reserved:0",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("RESERVED") or None,
            ),
        ]
    ]

    message_text = (
        f'مرحباً، <a href="tg://user?id={user.id}">{user.first_name}</a>\n'
        f'يسعدنا وجودك معنا في فريقنا.\n\n'
        f'اختر تصنيفاً :'
    )

    tg_api(
        "sendMessage",
        {
            "chat_id": update.effective_chat.id,
            "text": message_text,
            "parse_mode": "HTML",
            "reply_markup": inline_markup(keyboard),
        },
    )


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    data = query.data

    if data.startswith("show:"):
        try:
            _, typ, page_str = data.split(":")
            page = int(page_str)
            await ensure_data_is_fresh()

            entries = []
            if typ == "available":
                entries = [f"{n} < {sale_price(p)} >" for n, p in cached_available_numbers]
            elif typ == "sold":
                entries = cached_sold_numbers
            elif typ == "reserved":
                text = "هذه الأرقام محجوزة حالياً ولا يمكن عرضها."
                kb = inline_markup(
                    [
                        [
                            btn(
                                "العودة للقائمة الرئيسية",
                                callback_data="main_menu",
                                style="primary",
                                icon_custom_emoji_id=CUSTOM_EMOJI.get("BACK") or None,
                            )
                        ]
                    ]
                )
                tg_api(
                    "editMessageText",
                    {
                        "chat_id": query.message.chat.id,
                        "message_id": query.message.message_id,
                        "text": text,
                        "reply_markup": kb,
                    },
                )
                return
            
            # الفلاتر
            elif typ == "f_normal":
                entries = filter_normal_cheapest(cached_available_numbers)
            elif typ == "f_rep_a":
                entries = filter_repeated_a(cached_available_numbers)
            elif typ == "f_rep_b":
                entries = filter_repeated_b(cached_available_numbers)
            elif typ == "f_asc":
                entries = filter_ascending(cached_available_numbers)
            elif typ == "f_desc":
                entries = filter_descending(cached_available_numbers)

            text, kb = make_page(entries, typ, page)
            tg_api(
                "editMessageText",
                {
                    "chat_id": query.message.chat.id,
                    "message_id": query.message.message_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": kb,
                },
            )

        except Exception as e:
            logging.error(f"خطأ في معالج الاستدعاء: {e}")
            tg_api(
                "editMessageText",
                {
                    "chat_id": query.message.chat.id,
                    "message_id": query.message.message_id,
                    "text": "طاحضك لا تدوس بسرعه انطي مجال ❌",
                },
            )

    elif data == "filter_menu":
        # ألوان أزرار الفلاتر بالتسلسل: أحمر، أخضر، أزرق، ثم تكرار
        styles_cycle = ["danger", "success", "primary"]
        kb = [
            [
                btn(
                    "رقم عادي الارخص",
                    callback_data="show:f_normal:0",
                    style=styles_cycle[0 % len(styles_cycle)],
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("NORMAL") or None,
                )
            ],
            [
                btn(
                    "مكرر A",
                    callback_data="show:f_rep_a:0",
                    style=styles_cycle[1 % len(styles_cycle)],
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("REP_A") or None,
                )
            ],
            [
                btn(
                    "مكرر B",
                    callback_data="show:f_rep_b:0",
                    style=styles_cycle[2 % len(styles_cycle)],
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("REP_B") or None,
                )
            ],
            [
                btn(
                    "تصاعدي",
                    callback_data="show:f_asc:0",
                    style="success",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("ASC") or None,
                )
            ],
            [
                btn(
                    "تنازلي",
                    callback_data="show:f_desc:0",
                    style="danger",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("DESC") or None,
                )
            ],
            # زر الرجوع أزرق
            [
                btn(
                    "العودة للقائمة الرئيسية",
                    callback_data="main_menu",
                    style="primary",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("BACK") or None,
                )
            ],
        ]
        tg_api(
            "editMessageText",
            {
                "chat_id": query.message.chat.id,
                "message_id": query.message.message_id,
                "text": "حدد ما تريد",
                "reply_markup": inline_markup(kb),
            },
        )

    elif data == "main_menu":
        keyboard = [
            [
                btn(
                    "متوفر 🟢",
                    callback_data="show:available:0",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("AVAILABLE") or None,
                ),
                btn(
                    "مباع 🔴",
                    callback_data="show:sold:0",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("SOLD") or None,
                ),
            ],
            [
                btn(
                    "فلتره ⚙️",
                    callback_data="filter_menu",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("FILTER") or None,
                ),
                btn(
                    "محجوز ⏱️",
                    callback_data="show:reserved:0",
                    icon_custom_emoji_id=CUSTOM_EMOJI.get("RESERVED") or None,
                ),
            ]
        ]
        message_text = (
            f'مرحباً، <a href="tg://user?id={user.id}">{user.first_name}</a>\n'
            f'يسعدنا وجودك معنا في فريقنا.\n\n'
            f'اختر تصنيفاً :'
        )
        tg_api(
            "editMessageText",
            {
                "chat_id": query.message.chat.id,
                "message_id": query.message.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "reply_markup": inline_markup(keyboard),
            },
        )

    elif data == "add_user":
        await query.edit_message_text("أرسل ID المستخدم الجديد:")
        return ADD_USER_ID


async def sa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    kb = [
        [
            btn(
                "إضافة مستخدم",
                callback_data="add_user",
                icon_custom_emoji_id=CUSTOM_EMOJI.get("ADD_USER") or None,
            )
        ]
    ]
    tg_api(
        "sendMessage",
        {
            "chat_id": update.effective_chat.id,
            "text": "لوحة التحكم:",
            "reply_markup": inline_markup(kb),
        },
    )

async def receive_new_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("الرجاء إدخال رقم معرف صالح.")
        return ADD_USER_ID
    new_id = int(text)
    allowed_ids.add(new_id)
    save_allowed(list(allowed_ids))
    await update.message.reply_text(f"تم إضافة {new_id} بنجاح.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END

async def post_init(application: ApplicationBuilder) -> None:
    await fetch_numbers_from_tonapi()

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("sa", sa_command))
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_query_handler, pattern="^add_user$")],
        states={ADD_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_id)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
