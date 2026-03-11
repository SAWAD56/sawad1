import json
import logging
import math
import re
import time
import asyncio
from typing import Dict, List, Tuple

import requests
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
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

TOKEN = "8108589562:AAF4th-6Bhyu4zSAtDdQS59Y4X4zDecaN2o"
OWNER_ID = 1411672636
COLLECTION_ADDRESS = "EQAg556MaTsIRDH-NUHOyzQ5WsKBdD9OFXBp8cMsuUxlX5dV" # عنوان مجموعة Pepe-Sim NFT
USERS_FILE = "allowed_users.json"

# حالات المحادثة لإضافة المستخدمين
ADD_USER_ID = 1

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


def make_page(items: List[str], typ: str, page: int, per_page: int = 6) -> Tuple[str, InlineKeyboardMarkup]:
    """
    تُعيد نص الصفحة والكيبورد مع أزرار السابق/التالي.
    """
    start = page * per_page
    chunk = items[start : start + per_page]
    text = "\n".join(chunk) if chunk else "لا توجد بيانات."

    kb = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"show:{typ}:{page-1}"))
    if start + per_page < len(items):
        row.append(InlineKeyboardButton("التالي ▶️", callback_data=f"show:{typ}:{page+1}"))
    if row:
        kb.append(row)
    
    kb.append([InlineKeyboardButton("العودة للقائمة الرئيسية", callback_data="main_menu")])

    return text, InlineKeyboardMarkup(kb)


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
        await update.message.reply_text("عذراً، لا تملك صلاحية استخدام هذا البوت.")
        return

    keyboard = [
        [
            InlineKeyboardButton("متوفر 🟢", callback_data="show:available:0"),
            InlineKeyboardButton("مباع 🔴", callback_data="show:sold:0")
        ],
        [
            InlineKeyboardButton("فلتره ⚙️", callback_data="filter_menu"),
            InlineKeyboardButton("محجوز ⏱️", callback_data="show:reserved:0")
        ]
    ]

    message_text = (
        f'مرحباً، <a href="tg://user?id={user.id}">{user.first_name}</a>\n'
        f'يسعدنا وجودك معنا في فريقنا.\n\n'
        f'اختر تصنيفاً :'
    )

    await update.message.reply_text(
        text=message_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
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
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("العودة للقائمة الرئيسية", callback_data="main_menu")]])
                await query.edit_message_text(text=text, reply_markup=kb)
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
            await query.edit_message_text(text=text, reply_markup=kb)

        except Exception as e:
            logging.error(f"خطأ في معالج الاستدعاء: {e}")
            await query.edit_message_text(text="❌ فشل جلب البيانات أو معالجتها.")

    elif data == "filter_menu":
        kb = [
            [InlineKeyboardButton("رقم عادي الارخص", callback_data="show:f_normal:0")],
            [InlineKeyboardButton("مكرر A", callback_data="show:f_rep_a:0")],
            [InlineKeyboardButton("مكرر B", callback_data="show:f_rep_b:0")],
            [InlineKeyboardButton("تصاعدي", callback_data="show:f_asc:0")],
            [InlineKeyboardButton("تنازلي", callback_data="show:f_desc:0")],
            [InlineKeyboardButton("العودة للقائمة الرئيسية", callback_data="main_menu")]
        ]
        await query.edit_message_text(text="حدد ما تريد", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "main_menu":
        keyboard = [
            [
                InlineKeyboardButton("متوفر 🟢", callback_data="show:available:0"),
                InlineKeyboardButton("مباع 🔴", callback_data="show:sold:0")
            ],
            [
                InlineKeyboardButton("فلتره ⚙️", callback_data="filter_menu"),
                InlineKeyboardButton("محجوز ⏱️", callback_data="show:reserved:0")
            ]
        ]
        message_text = (
            f'مرحباً، <a href="tg://user?id={user.id}">{user.first_name}</a>\n'
            f'يسعدنا وجودك معنا في فريقنا.\n\n'
            f'اختر تصنيفاً :'
        )
        await query.edit_message_text(text=message_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "add_user":
        await query.edit_message_text("أرسل ID المستخدم الجديد:")
        return ADD_USER_ID


async def sa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    kb = [[InlineKeyboardButton("إضافة مستخدم", callback_data="add_user")]]
    await update.message.reply_text("لوحة التحكم:", reply_markup=InlineKeyboardMarkup(kb))

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
