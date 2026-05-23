import time
import json
import re
import logging
from datetime import datetime

import requests

# ─── Configuration ───────────────────────────────────────────────
API_KEY = "8799827850:AAF_6bEXiJn7CQnUjrRQk6hELHOLy6ym-Kw"
BASE_URL = f"https://api.telegram.org/bot{API_KEY}"

# Exchange rates (IQD)
ASIA_RATE = 1620
MASTER_RATE = 1529
ITUNES_RATE = 1460
STARS_RATE = 67

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─── UTF-16 Helpers (Telegram API uses UTF-16 code units) ────────

def utf16_len(s):
    """Return the number of UTF-16 code units in a string."""
    return len(s.encode('utf-16-le')) // 2

def utf16_offset(text, substring):
    """Return the UTF-16 code unit offset of substring in text."""
    idx = text.index(substring)
    return utf16_len(text[:idx])

# ─── Telegram helpers ────────────────────────────────────────────

def bot(method, datas=None):
    url = f"{BASE_URL}/{method}"
    try:
        # Use json= for proper nested JSON serialization (supports Bot API 9.4 features)
        resp = requests.post(url, json=datas or {}, timeout=(5, 10))
        return resp.json()
    except Exception as exc:
        logging.error("Telegram API error: %s", exc)
        return None

def get_updates(offset=None):
    params = {"limit": 100, "timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=40)
        return resp.json()
    except Exception as exc:
        logging.error("Get updates error: %s", exc)
        return {"result": []}

# ─── Custom Emoji Helper ─────────────────────────────────────────

def build_entities_param(entities_list):
    """Convert custom emoji entities to Telegram API format"""
    if not entities_list:
        return None
    api_entities = []
    for ent in entities_list:
        api_ent = {
            "type": ent["type"],
            "offset": ent["offset"],
            "length": ent["length"]
        }
        if "document_id" in ent:
            api_ent["custom_emoji_id"] = str(ent["document_id"])
        if "custom_emoji_id" in ent:
            api_ent["custom_emoji_id"] = str(ent["custom_emoji_id"])
        if "url" in ent:
            api_ent["url"] = ent["url"]
        api_entities.append(api_ent)
    return json.dumps(api_entities)

# ─── Message Templates with Custom Emoji ─────────────────────────

MESSAGES = {
    "start": {
        "text": "🟩  حاب تحسب قيمة عملتك؟  😏\n\n💱  اكتب الكمية ونوع العملة\n\n🟩  مثال: 1 TON\n\n- يتم عرض السعر بالدولار وجميع العملات 💰",
        "entities": [
            {"type": "custom_emoji", "offset": 0, "length": 2, "document_id": 5314457068801908963},
            {"type": "custom_emoji", "offset": 26, "length": 2, "document_id": 5877670209229167742},
            {"type": "custom_emoji", "offset": 30, "length": 2, "document_id": 5377336227533969892},
            {"type": "custom_emoji", "offset": 59, "length": 2, "document_id": 5314457068801908963},
            {"type": "custom_emoji", "offset": 115, "length": 2, "document_id": 5278467510604160626}
        ]
    },
    "explain": {
        "text": "🟩 تصريف العملات\n\n⚙️ طريقة الاستخدام 👆 :\n• اكتب الكمية مع نوع العملة\n• أمثلة ✏️ :\n  - 10 تون\n  - 1000 نجوم\n  - 100 آسيا\n\n✨ سيعرض البوت الأسعار التالية ↘️ :\n\n• السعر بالدولار  💵 .\n• السعر بعملة تون  🪙 .\n• السعر بعملة آسيا 🤎 .\n• السعر بعملة ماستر 💳 .\n• عدد النجوم ⭐️ .\n\n⚠️ ملاحظة:\n\nالأسعار تتغير باستمرار حسب حركة السوق 🔼🔽",
        "entities": [
            {"type": "custom_emoji", "offset": 0, "length": 2, "document_id": 5314457068801908963},
            {"type": "custom_emoji", "offset": 18, "length": 2, "document_id": 5316977664848837418},
            {"type": "custom_emoji", "offset": 37, "length": 2, "document_id": 5343886833254159565},
            {"type": "custom_emoji", "offset": 78, "length": 2, "document_id": 6039779802741739617},
            {"type": "custom_emoji", "offset": 122, "length": 1, "document_id": 5319201848022808495},
            {"type": "custom_emoji", "offset": 152, "length": 2, "document_id": 5222456142017348216},
            {"type": "custom_emoji", "offset": 176, "length": 2, "document_id": 5409048419211682843},
            {"type": "custom_emoji", "offset": 200, "length": 2, "document_id": 5377620962390857342},
            {"type": "custom_emoji", "offset": 224, "length": 2, "document_id": 5224213947577572327},
            {"type": "custom_emoji", "offset": 249, "length": 2, "document_id": 5341390250369370761},
            {"type": "custom_emoji", "offset": 267, "length": 2, "document_id": 5956571391271637639},
            {"type": "custom_emoji", "offset": 273, "length": 2, "document_id": 5447603722152591223},
            {"type": "custom_emoji", "offset": 323, "length": 2, "document_id": 5449683594425410231},
            {"type": "custom_emoji", "offset": 325, "length": 2, "document_id": 5447183459602669338}
        ]
    },
    "commands": {
        "text": "📋 قائمة الأوامر والعملات:\n\n💱 التحويلات:\n• تون - مثال: 1 تون / 10 ton\n• آسيا - مثال: 1000 آسيا / 500 اسيا\n• ماستر - مثال: 1 ماستر / 5 master\n• نجوم - مثال: 100 نجوم / 50 stars\n• دولار - مثال: 10 دولار / 20 usdt\n\n📊 الأسعار:\n• سعر الذهب / الذهب\n• سعر النفط / النفط\n• سعر البيتكوين / btc\n• سعر الإيثيريوم / eth\n• سعر السولانا / sol\n• سعر السوق / p2p\n\n🎫 الخدمات:\n• ايتونز - مثال: 10 ايتونز\n• فحص - مثال: فحص @username\n\nℹ️ المساعدة:\n• /start - البداية\n• /commands - هذه القائمة\n• اشرحلي - شرح الاستخدام 🤔",
        "entities": [
            {"type": "custom_emoji", "offset": 0, "length": 2, "document_id": 5408946052961170713},
            {"type": "custom_emoji", "offset": 28, "length": 2, "document_id": 5314457068801908963},
            {"type": "custom_emoji", "offset": 213, "length": 2, "document_id": 5247046225651326543},
            {"type": "custom_emoji", "offset": 350, "length": 2, "document_id": 5418296969858680858},
            {"type": "custom_emoji", "offset": 418, "length": 2, "document_id": 5197288647275071607},
            {"type": "custom_emoji", "offset": 501, "length": 2, "document_id": 5298913899985264121}
        ]
    },
    "help": {
        "text": "💱  اكتب الكمية ونوع العملة\n😐  مثال: 1 TON او 1تون 💱",
        "entities": [
            {"type": "custom_emoji", "offset": 0, "length": 2, "document_id": 5377336227533969892},
            {"type": "custom_emoji", "offset": 28, "length": 2, "document_id": 5942629270298832732},
            {"type": "custom_emoji", "offset": 52, "length": 2, "document_id": 5312441427764989435}
        ]
    },
    "fragment_view": {
        "text": "شعليك ، جاي تبحوش وره العالم ㅤ🔫💵\n\nUser: @y_u_g",
        "entities": [
            {"type": "custom_emoji", "offset": 30, "length": 2, "document_id": 5942723231298362869},
            {"type": "custom_emoji", "offset": 32, "length": 2, "document_id": 5456343997779831665}
        ]
    },
    "itunes": {
        "text": "**🍎**** أسعار كروت وبطاقات آيتونز (1.0 $)\n\n**🤑** القيمة الإجمالية بالدولار: 1.0 $\n**🇮🇶** التكلفة الكلية بالعراقي: 1,460 د.ع\n\n**🏷** سعر الصرف المعتمد للآيتنز: 1,460 د.ع\n**🔄** الوقت: 10:10:22**",
        "entities": [
            {"type": "custom_emoji", "offset": 0, "length": 2, "document_id": 5300789799966242827},
            {"type": "custom_emoji", "offset": 38, "length": 2, "document_id": 5461139036708033234},
            {"type": "custom_emoji", "offset": 74, "length": 4, "document_id": 5228888890630224685},
            {"type": "custom_emoji", "offset": 115, "length": 2, "document_id": 5296385246579670377},
            {"type": "custom_emoji", "offset": 155, "length": 2, "document_id": 5778202206922608769}
        ]
    },
    "unknown": {
        "text": "❔❓ أمر غير معروف. اكتب /start لعرض الأوامر المتاحة.",
        "entities": [
            {"type": "custom_emoji", "offset": 0, "length": 1, "document_id": 5377537549831005036},
            {"type": "custom_emoji", "offset": 1, "length": 1, "document_id": 5326027753647002844}
        ]
    }
}

# ─── Price fetchers ──────────────────────────────────────────────

def get_crypto_prices():
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=the-open-network,bitcoin,ethereum,solana,tether,tron,binancecoin"
        "&vs_currencies=usd"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.json()
    except Exception as exc:
        logging.error("Crypto fetch error: %s", exc)
        return {}

def get_binance_p2p_superqi():
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
    }
    payload = {
        "asset": "USDT",
        "fiat": "IQD",
        "merchantCheck": False,
        "page": 1,
        "payTypes": ["SuperQi"],
        "rows": 7,
        "tradeType": "SELL"
    }
    try:
        r = requests.post(
            "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
            json=payload,
            headers=headers,
            timeout=10
        )
        data = r.json()
        prices = []
        for ad in data.get("data", []):
            if ad["adv"].get("isPromoted"):
                continue
            price = float(ad["adv"]["price"])
            name = ad["advertiser"]["nickName"]
            prices.append({"price": price, "seller": name})
        return prices
    except Exception as exc:
        logging.error("Binance P2P fetch error: %s", exc)
        return []

def get_global_commodity_prices():
    headers = {"User-Agent": "Mozilla/5.0"}
    brent = wti = 0.0

    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1m&range=1d",
            headers=headers, timeout=5,
        )
        brent = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as exc:
        logging.warning("Brent fetch failed: %s", exc)

    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1m&range=1d",
            headers=headers, timeout=5,
        )
        wti = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as exc:
        logging.warning("WTI fetch failed: %s", exc)

    if brent == 0:
        try:
            r = requests.get(
                "https://financialmodelingprep.com/api/v3/quote/CL00?apikey=demo",
                headers=headers, timeout=5,
            )
            data = r.json()
            if data:
                brent = float(data[0]["price"]) + 4.5
                wti = float(data[0]["price"])
        except Exception as exc:
            logging.warning("Oil fallback failed: %s", exc)
            brent = 78.50
            wti = 74.00

    if wti == 0 and brent > 0:
        wti = brent - 4.20

    gold_ounce = silver_ounce = 0.0
    try:
        r = requests.get(
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            headers=headers, timeout=5,
        )
        data = r.json()
        gold_ounce = 1 / data["usd"].get("xau", 1 / 2350.00)
        silver_ounce = 1 / data["usd"].get("xag", 1 / 28.50)
    except Exception as exc:
        logging.warning("Gold fetch failed: %s", exc)
        gold_ounce = 2350.00
        silver_ounce = 28.50

    return {
        "gold": gold_ounce,
        "silver": silver_ounce,
        "brent": brent,
        "wti": wti,
    }

# ─── Fragment checker ───────────────────────────────────────────

def check_fragment(username):
    try:
        url = f"https://fragment.com/username/{username}"
        html = requests.get(url, timeout=15).text
        if 'tm-status-unavail">Sold' in html:
            return "sold"
        if 'tm-status-taken">Taken' in html:
            return "taken"
        if 'tm-status-unavail">Unavailable' in html:
            return "available"
        return "unknown"
    except:
        return "error"

def extract_usernames(text):
    """Extract all usernames from text."""
    matches = re.findall(r'@([a-zA-Z0-9_]{4,32})', text)
    return matches

# ─── Keyboard helpers with COLORS and CUSTOM EMOJI ───────────────
# FIX: Swapped button positions - View Details first, then Open user

def get_main_keyboard():
    return json.dumps({
        "inline_keyboard": [
            [{"text": "اشرحلي", "callback_data": "explain", "style": "success", "icon_custom_emoji_id": "6012468526613272811"}],
            [{"text": "المالك", "url": "https://t.me/rrry_r", "style": "primary", "icon_custom_emoji_id": "5438548621127615575"}]
        ]
    })

def get_back_keyboard():
    return json.dumps({
        "inline_keyboard": [
            [{"text": "رجوع", "callback_data": "back_main", "style": "danger", "icon_custom_emoji_id": "6010608968982863617"}]
        ]
    })

def get_fragment_keyboard(username, status):
    """Fragment result keyboard based on status."""
    if status == "sold":
        # FIX: Swapped positions - View Details first, then Open user
        return json.dumps({
            "inline_keyboard": [
                [{"text": "View Details", "callback_data": f"frag_view_{username}", "style": "primary", "icon_custom_emoji_id": "5362061893605279054"}],
                [{"text": "Open user", "url": f"https://t.me/{username}", "style": "success", "icon_custom_emoji_id": "5359582963036069675"}]
            ]
        })
    else:
        return json.dumps({
            "inline_keyboard": [
                [{"text": "Open user", "url": f"https://t.me/{username}", "style": "danger", "icon_custom_emoji_id": "5359582963036069675"}]
            ]
        })

# ─── Send Message with Custom Emoji ─────────────────────────────

def send_message_with_emoji(chat_id, message_key, reply_markup=None, reply_to_message_id=None, edit=False, message_id=None):
    """Send a message with custom emoji support"""
    msg_data = MESSAGES.get(message_key, MESSAGES["unknown"])
    text = msg_data["text"]
    entities = build_entities_param(msg_data.get("entities"))

    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    if entities:
        payload["entities"] = entities

    if reply_markup:
        payload["reply_markup"] = reply_markup

    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    if edit and message_id:
        payload["message_id"] = message_id
        return bot("editMessageText", payload)
    else:
        return bot("sendMessage", payload)

# ─── Command handlers ──────────────────────────────────────────

def handle_start(chat_id, reply_to_message_id=None, message_id=None, edit=False):
    return send_message_with_emoji(
        chat_id, "start",
        reply_markup=get_main_keyboard(),
        reply_to_message_id=reply_to_message_id,
        edit=edit, message_id=message_id
    )

def handle_explain(chat_id, reply_to_message_id=None, message_id=None, edit=False):
    return send_message_with_emoji(
        chat_id, "explain",
        reply_markup=get_back_keyboard(),
        reply_to_message_id=reply_to_message_id,
        edit=edit, message_id=message_id
    )

def handle_commands(chat_id, reply_to_message_id=None):
    """Show all commands and currencies with examples"""
    return send_message_with_emoji(
        chat_id, "commands",
        reply_markup=get_main_keyboard(),
        reply_to_message_id=reply_to_message_id
    )

def handle_callback(update):
    callback = update["callback_query"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    data = callback.get("data", "")

    # Answer callback to remove loading state
    bot("answerCallbackQuery", {"callback_query_id": callback["id"]})

    if data == "explain":
        handle_explain(chat_id, message_id=message_id, edit=True)
    elif data == "back_main":
        handle_start(chat_id, message_id=message_id, edit=True)
    elif data.startswith("frag_view_"):
        username = data.replace("frag_view_", "")
        # Build text with blockquote entity for the custom text
        line1 = "شعليك ، جاي تبحوش وره العالم ㅤ🔫💵"
        line2 = f"User: @{username}"
        text = f"{line1}\n\n{line2}"

        # Calculate UTF-16 offsets dynamically
        frag_offset = utf16_offset(text, "🔫")
        dollar_offset = utf16_offset(text, "💵")

        entities = [
            {"type": "blockquote", "offset": 0, "length": utf16_len(line1)},
            {"type": "custom_emoji", "offset": frag_offset, "length": utf16_len("🔫"), "custom_emoji_id": "5942723231298362869"},
            {"type": "custom_emoji", "offset": dollar_offset, "length": utf16_len("💵"), "custom_emoji_id": "5456343997779831665"}
        ]
        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "entities": json.dumps(entities),
            "reply_markup": get_fragment_keyboard(username, "sold")
        }
        bot("editMessageText", payload)

def do_conversion(chat_id, amount, currency, ton_p, reply_to_message_id=None):
    """Core conversion logic - converts any amount+currency to all others."""

    if currency in ["تون", "ton"]:
        clean_ton = amount - (amount * 1.5 / 100)
        usdt = clean_ton * ton_p
        title = f"{amount} TON"
    elif currency in ["آسيا", "اسيا", "asia"]:
        real_amount = amount * 1000
        usdt = real_amount / ASIA_RATE
        title = f"{amount:.3f} آسيا"
    elif currency in ["ماستر", "master"]:
        real_amount = amount * 1000
        usdt = real_amount / MASTER_RATE
        title = f"{amount:.3f} ماستر"
    elif currency in ["دولار", "دولا", "usdt", "$"]:
        usdt = amount
        title = f"{amount} USDT"
    elif currency in ["نجوم", "نجمة", "stars"]:
        usdt = amount / STARS_RATE
        title = f"{amount} نجوم"
    else:
        return False

    ton = usdt / ton_p if ton_p > 0 else 0
    asia = usdt * ASIA_RATE
    master = usdt * MASTER_RATE
    stars = usdt * STARS_RATE

    now = datetime.now().strftime("%H:%M:%S")

    # Build text - title OUTSIDE blockquote, all prices INSIDE one blockquote
    text = f"⌯ 🟩   نتائج التحويل لـ ({title})\n\n"

    # Price section - ALL inside ONE blockquote
    price_section = ""
    price_section += f"💰  دولار :   {usdt:.4f}  $\n"
    price_section += f"⭐️  نجوم :   {stars:,.0f}\n"
    price_section += f"💳  ماستر :   {master:,.0f} د.ع\n"

    # TON value line between Master and Asia
    if currency in ["تون", "ton"]:
        # Show as integer if whole number
        if amount == int(amount):
            ton_display = f"{int(amount)}"
        else:
            ton_display = f"{amount}"
        price_section += f"🪙  تون :   {ton_display} TON\n"
    else:
        price_section += f"🪙  تون :   {ton:.4f} TON\n"

    price_section += f"🤎   آسيا :  {asia:,.0f} رصيد\n\n"
    price_section += f"🪙  سعر TON الآن :  {ton_p:.3f} $\n"
    price_section += f"🔄  التحديث : {now}"

    full_text = text + price_section

    # Build entities: ONE blockquote for entire price_section + custom emojis
    entities = []

    # Single blockquote for ALL price lines
    title_len = utf16_len(f"⌯ 🟩   نتائج التحويل لـ ({title})\n\n")
    entities.append({"type": "blockquote", "offset": title_len, "length": utf16_len(price_section)})

    # Custom emoji entities
    emoji_map = {
        "🟩": 5314457068801908963,
        "💰": 5337064470977982460,
        "🪙": 5377620962390857342,
        "🤎": 5224213947577572327,
        "⭐️": 5956571391271637639,
        "💳": 5341390250369370761,
        "🔄": 5778202206922608769,
    }

    for emoji_char, doc_id in emoji_map.items():
        pos = full_text.find(emoji_char)
        while pos != -1:
            entities.append({
                "type": "custom_emoji",
                "offset": utf16_len(full_text[:pos]),
                "length": utf16_len(emoji_char),
                "custom_emoji_id": str(doc_id)
            })
            pos = full_text.find(emoji_char, pos + len(emoji_char))

    # Sort entities by offset
    entities.sort(key=lambda x: x["offset"])

    payload = {
        "chat_id": chat_id,
        "text": full_text,
        "entities": json.dumps(entities) if entities else None
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    bot("sendMessage", payload)
    return True


def handle_message(update):
    msg = update.get("message", {})
    text = msg.get("text", "")
    chat_id = msg["chat"]["id"]
    chat_type = msg.get("chat", {}).get("type", "private")
    reply_to_message_id = msg.get("message_id")

    if not text:
        return

    text_clean = text.replace(",", "").strip()

    # /start command - works in ALL chats
    if text_clean.lower() == "/start" or text_clean.lower().startswith("/start@"):
        handle_start(chat_id, reply_to_message_id=reply_to_message_id)
        return

    # /commands command - works in ALL chats  
    if text_clean.lower() in ["/commands", "/اوامر", "اوامر", "الاوامر"] or text_clean.lower().startswith("/commands@"):
        handle_commands(chat_id, reply_to_message_id=reply_to_message_id)
        return

    ton_p = get_crypto_prices().get("the-open-network", {}).get("usd", 2.05)

    # ─── Fragment checker ──────────────────────────────────────
    # Pattern 1: فحص test / فحص @test / فحص@test
    m = re.search(r'^فحص\s*@?(\w+)$', text_clean, re.IGNORECASE)
    if m:
        username = m.group(1)
        status = check_fragment(username)

        if status == "error":
            status_text = "⚠️ خطأ بالفحص حاول لاحقاً"
            payload = {
                "chat_id": chat_id,
                "text": status_text,
                "reply_to_message_id": reply_to_message_id
            }
            bot("sendMessage", payload)
            return

        # Build dynamic fragment text with correct UTF-16 offsets and custom emoji
        if status == "sold":
            text = f"User • @{username}\nStatus • NFT ✔️"
            check_offset = utf16_len(f"User • @{username}\nStatus • NFT ")
            entities = [
                {"type": "custom_emoji", "offset": check_offset, "length": utf16_len("✔️"), "custom_emoji_id": "5206607081334906820"}
            ]
        elif status == "taken":
            text = f"User • @{username}\nStatus • Taken ❌"
            cross_offset = utf16_len(f"User • @{username}\nStatus • Taken ")
            entities = [
                {"type": "custom_emoji", "offset": cross_offset, "length": utf16_len("❌"), "custom_emoji_id": "5210952531676504517"}
            ]
        elif status == "available":
            text = f"User • @{username}\nStatus • No NFT ❌"
            cross_offset = utf16_len(f"User • @{username}\nStatus • No NFT ")
            entities = [
                {"type": "custom_emoji", "offset": cross_offset, "length": utf16_len("❌"), "custom_emoji_id": "5210952531676504517"}
            ]
        else:
            text = f"User • @{username}\nStatus • Unknown ❓"
            entities = []

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_markup": get_fragment_keyboard(username, status),
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Pattern 2: Reply to message with "فحص" - check ALL usernames in replied message
    reply_to = msg.get("reply_to_message")
    if reply_to and text_clean.strip().lower() == "فحص":
        reply_text = reply_to.get("text", "") or reply_to.get("caption", "")
        if reply_text:
            usernames = extract_usernames(reply_text)
            if usernames:
                if len(usernames) == 1:
                    # Single username - send with buttons (View Details + Open user)
                    username = usernames[0]
                    status = check_fragment(username)

                    if status == "error":
                        status_text = "⚠️ خطأ بالفحص حاول لاحقاً"
                        payload = {
                            "chat_id": chat_id,
                            "text": status_text,
                            "reply_to_message_id": reply_to_message_id
                        }
                        bot("sendMessage", payload)
                        return

                    if status == "sold":
                        text = f"User • @{username}\nStatus • NFT ✔️"
                        check_offset = utf16_len(f"User • @{username}\nStatus • NFT ")
                        entities = [
                            {"type": "custom_emoji", "offset": check_offset, "length": utf16_len("✔️"), "custom_emoji_id": "5206607081334906820"}
                        ]
                    elif status == "taken":
                        text = f"User • @{username}\nStatus • Taken ❌"
                        cross_offset = utf16_len(f"User • @{username}\nStatus • Taken ")
                        entities = [
                            {"type": "custom_emoji", "offset": cross_offset, "length": utf16_len("❌"), "custom_emoji_id": "5210952531676504517"}
                        ]
                    elif status == "available":
                        text = f"User • @{username}\nStatus • No NFT ❌"
                        cross_offset = utf16_len(f"User • @{username}\nStatus • No NFT ")
                        entities = [
                            {"type": "custom_emoji", "offset": cross_offset, "length": utf16_len("❌"), "custom_emoji_id": "5210952531676504517"}
                        ]
                    else:
                        text = f"User • @{username}\nStatus • Unknown ❓"
                        entities = []

                    payload = {
                        "chat_id": chat_id,
                        "text": text,
                        "entities": json.dumps(entities) if entities else None,
                        "reply_markup": get_fragment_keyboard(username, status),
                        "reply_to_message_id": reply_to_message_id
                    }
                    bot("sendMessage", payload)
                    return
                else:
                    # Multiple usernames - send ONE combined message, NO buttons, with custom emoji
                    lines = []
                    all_entities = []
                    base_offset = 0

                    for i, username in enumerate(usernames):
                        status = check_fragment(username)

                        if status == "sold":
                            line_text = f"User • @{username}\nStatus • NFT ✔️"
                            check_off = utf16_len(f"User • @{username}\nStatus • NFT ")
                            line_entities = [{"type": "custom_emoji", "offset": base_offset + check_off, "length": utf16_len("✔️"), "custom_emoji_id": "5206607081334906820"}]
                        elif status == "taken":
                            line_text = f"User • @{username}\nStatus • Taken ❌"
                            cross_off = utf16_len(f"User • @{username}\nStatus • Taken ")
                            line_entities = [{"type": "custom_emoji", "offset": base_offset + cross_off, "length": utf16_len("❌"), "custom_emoji_id": "5210952531676504517"}]
                        elif status == "available":
                            line_text = f"User • @{username}\nStatus • No NFT ❌"
                            cross_off = utf16_len(f"User • @{username}\nStatus • No NFT ")
                            line_entities = [{"type": "custom_emoji", "offset": base_offset + cross_off, "length": utf16_len("❌"), "custom_emoji_id": "5210952531676504517"}]
                        elif status == "error":
                            line_text = f"User • @{username}\nStatus • Error ⚠️"
                            line_entities = []
                        else:
                            line_text = f"User • @{username}\nStatus • Unknown ❓"
                            line_entities = []

                        lines.append(line_text)
                        all_entities.extend(line_entities)
                        base_offset += utf16_len(line_text) + 2

                    base_offset -= 2
                    full_text = "\n\n".join(lines)

                    payload = {
                        "chat_id": chat_id,
                        "text": full_text,
                        "entities": json.dumps(all_entities) if all_entities else None,
                        "reply_to_message_id": reply_to_message_id
                    }
                    bot("sendMessage", payload)
                    return

    # ─── "صرف" or "الصرف" → show help message ──────────────────
    if re.search(r'^(?:ال)?صرف$', text_clean, re.IGNORECASE):
        send_message_with_emoji(chat_id, "help", reply_to_message_id=reply_to_message_id)
        return

    # ─── Conversion patterns ────────────────────────────────────
    # Pattern 1: "[عدد] [عملة]" with space
    m = re.search(r'^(\d+(?:\.\d+)?)\s+(تون|ton|آسيا|اسيا|asia|ماستر|master|دولار|دولا|usdt|\$|نجوم|نجمة|stars)$', text_clean, re.IGNORECASE)
    if m:
        amount = float(m.group(1))
        currency = m.group(2).lower()
        do_conversion(chat_id, amount, currency, ton_p, reply_to_message_id)
        return

    # Pattern 2: "[عدد][عملة]" without space
    m = re.search(r'^(\d+(?:\.\d+)?)(تون|ton|آسيا|اسيا|asia|ماستر|master|دولار|دولا|usdt|\$|نجوم|نجمة|stars)$', text_clean, re.IGNORECASE)
    if m:
        amount = float(m.group(1))
        currency = m.group(2).lower()
        do_conversion(chat_id, amount, currency, ton_p, reply_to_message_id)
        return

    # Pattern 3: "سعر/صرف [عدد] [عملة]"
    m = re.search(r'^(?:سعر|صرف)\s+(\d+(?:\.\d+)?)\s*(تون|ton|آسيا|اسيا|asia|ماستر|master|دولار|دولا|usdt|\$|نجوم|نجمة|stars)$', text_clean, re.IGNORECASE)
    if m:
        amount = float(m.group(1))
        currency = m.group(2).lower()
        do_conversion(chat_id, amount, currency, ton_p, reply_to_message_id)
        return

    # Pattern 4: "سعر/صرف [عملة]" without number
    m = re.search(r'^(?:سعر|صرف)\s+(?:ال)?(تون|ton|آسيا|اسيا|asia|ماستر|master|دولار|دولا|usdt|\$|نجوم|نجمة|stars)$', text_clean, re.IGNORECASE)
    if m:
        currency = m.group(1).lower()
        do_conversion(chat_id, 1, currency, ton_p, reply_to_message_id)
        return

    # Pattern 5: Standalone currency names
    m = re.search(r'^(?:ال)?(تون|ton|آسيا|اسيا|asia|ماستر|master|دولار|دولا|usdt|\$|نجوم|نجمة|stars)$', text_clean, re.IGNORECASE)
    if m:
        currency = m.group(1).lower()
        do_conversion(chat_id, 1, currency, ton_p, reply_to_message_id)
        return

    # ─── Pattern 6: "سعر/صرف [عدد] ايتونز" ─────────────────────
    m = re.search(r'^(?:سعر|صرف)\s+(\d+(?:\.\d+)?)\s*ايتونز$', text_clean, re.IGNORECASE)
    if m:
        amount = float(m.group(1))
        cost_iqd = amount * ITUNES_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"🍎 أسعار كروت وبطاقات آيتونز ({amount} $)\n\n"
            f"💵  القيمة الإجمالية بالدولار : {amount} $\n"
            f"🇮🇶  التكلفة الكلية بالعراقي : {cost_iqd:,.0f} د.ع\n\n"
            f"📊  سعر الصرف المعتمد للآيتنز : {ITUNES_RATE:,.0f} د.ع\n"
            f"🔄  الوقت : {now}"
        )

        # Build blockquote entities for each line
        entities = []
        line1_start = utf16_len(f"🍎 أسعار كروت وبطاقات آيتونز ({amount} $)\n\n")
        line1_text = f"💵  القيمة الإجمالية بالدولار : {amount} $"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"🇮🇶  التكلفة الكلية بالعراقي : {cost_iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"📊  سعر الصرف المعتمد للآيتنز : {ITUNES_RATE:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        line4_start = line3_start + utf16_len(line3_text) + 1
        line4_text = f"🔄  الوقت : {now}"
        entities.append({"type": "blockquote", "offset": line4_start, "length": utf16_len(line4_text)})

        emoji_map = {
            "🍎": 5300789799966242827,
            "💵": 5461139036708033234,
            "🇮🇶": 5228888890630224685,
            "📊": 5296385246579670377,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # ─── Pattern 6b: Standalone "[عدد] ايتونز" without سعر/صرف prefix ──
    m = re.search(r'^(\d+(?:\.\d+)?)\s*ايتونز$', text_clean, re.IGNORECASE)
    if m:
        amount = float(m.group(1))
        cost_iqd = amount * ITUNES_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"🍎 أسعار كروت وبطاقات آيتونز ({amount} $)\n\n"
            f"💵  القيمة الإجمالية بالدولار : {amount} $\n"
            f"🇮🇶  التكلفة الكلية بالعراقي : {cost_iqd:,.0f} د.ع\n\n"
            f"📊  سعر الصرف المعتمد للآيتنز : {ITUNES_RATE:,.0f} د.ع\n"
            f"🔄  الوقت : {now}"
        )

        # Build blockquote entities for each line
        entities = []
        line1_start = utf16_len(f"🍎 أسعار كروت وبطاقات آيتونز ({amount} $)\n\n")
        line1_text = f"💵  القيمة الإجمالية بالدولار : {amount} $"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"🇮🇶  التكلفة الكلية بالعراقي : {cost_iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"📊  سعر الصرف المعتمد للآيتنز : {ITUNES_RATE:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        line4_start = line3_start + utf16_len(line3_text) + 1
        line4_text = f"🔄  الوقت : {now}"
        entities.append({"type": "blockquote", "offset": line4_start, "length": utf16_len(line4_text)})

        emoji_map = {
            "🍎": 5300789799966242827,
            "💵": 5461139036708033234,
            "🇮🇶": 5228888890630224685,
            "📊": 5296385246579670377,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # ─── Pattern 7: Other commands (gold, oil, crypto, market) ─────

    # Gold - with or without "سعر/صرف" prefix
    if re.search(r'^(?:سعر|صرف)\s+(?:ال)?(ذهب|الذهب)$', text_clean, re.IGNORECASE) or \
       re.search(r'^(?:ال)?(ذهب|الذهب)$', text_clean, re.IGNORECASE):
        commodities = get_global_commodity_prices()
        ounce_gold = commodities["gold"]
        gram_gold = ounce_gold / 31.1034768
        ounce_iqd = ounce_gold * MASTER_RATE
        gram_iqd = gram_gold * MASTER_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"❤️ أسعار الذهب العالمية والمحلية في البورصة\n\n"
            f"💲  الأونصة عالمياً : {ounce_gold:,.2f} $\n"
            f"💲  الغرام عالمياً : {gram_gold:,.2f} $\n\n"
            f"💳  بالعراقي (أونصة) : {ounce_iqd:,.0f} د.ع\n"
            f"💳  بالعراقي (غرام) : {gram_iqd:,.0f} د.ع\n\n"
            f"🔄   التحديث المباشر : {now}"
        )

        # Build blockquote entities
        entities = []
        line1_start = utf16_len(f"❤️ أسعار الذهب العالمية والمحلية في البورصة\n\n")
        line1_text = f"💲  الأونصة عالمياً : {ounce_gold:,.2f} $"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"💲  الغرام عالمياً : {gram_gold:,.2f} $"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"💳  بالعراقي (أونصة) : {ounce_iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        line4_start = line3_start + utf16_len(line3_text) + 1
        line4_text = f"💳  بالعراقي (غرام) : {gram_iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line4_start, "length": utf16_len(line4_text)})

        line5_start = line4_start + utf16_len(line4_text) + 2
        line5_text = f"🔄   التحديث المباشر : {now}"
        entities.append({"type": "blockquote", "offset": line5_start, "length": utf16_len(line5_text)})

        emoji_map = {
            "❤️": 5361972983487289815,
            "💲": 5454035074901106230,
            "💳": 5341390250369370761,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Oil - with or without "سعر/صرف" prefix
    if re.search(r'^(?:سعر|صرف)\s+(?:ال)?(نفط|النفط)$', text_clean, re.IGNORECASE) or \
       re.search(r'^(?:ال)?(نفط|النفط)$', text_clean, re.IGNORECASE):
        commodities = get_global_commodity_prices()
        brent = commodities["brent"]
        wti = commodities["wti"]
        brent_iqd = brent * MASTER_RATE
        wti_iqd = wti * MASTER_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"🛢 مؤشرات أسعار النفط العالمية الحية (Yahoo Finance)\n\n"
            f"🛢  برميل برنت العالمي (Brent) : {brent:,.2f} $\n"
            f"🤩  برنت بالدينار العراقي : {brent_iqd:,.0f} د.ع\n\n"
            f"🛢  برميل غرب تكساس (WTI) : {wti:,.2f} $\n"
            f"🤩  WTI بالدينار العراقي : {wti_iqd:,.0f} د.ع\n\n"
            f"🔄  التحديث الفوري : {now}"
        )

        # Build blockquote entities
        entities = []
        line1_start = utf16_len(f"🛢 مؤشرات أسعار النفط العالمية الحية (Yahoo Finance)\n\n")
        line1_text = f"🛢  برميل برنت العالمي (Brent) : {brent:,.2f} $"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"🤩  برنت بالدينار العراقي : {brent_iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"🛢  برميل غرب تكساس (WTI) : {wti:,.2f} $"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        line4_start = line3_start + utf16_len(line3_text) + 1
        line4_text = f"🤩  WTI بالدينار العراقي : {wti_iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line4_start, "length": utf16_len(line4_text)})

        line5_start = line4_start + utf16_len(line4_text) + 2
        line5_text = f"🔄  التحديث الفوري : {now}"
        entities.append({"type": "blockquote", "offset": line5_start, "length": utf16_len(line5_text)})

        emoji_map = {
            "🛢": 5231105652100714290,
            "🤩": 5294390547803294400,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Bitcoin - with or without "سعر/صرف" prefix
    if re.search(r'^(?:سعر|صرف)\s+(?:ال)?(btc|بيتكوين)$', text_clean, re.IGNORECASE) or \
       re.search(r'^(?:ال)?(btc|بيتكوين)$', text_clean, re.IGNORECASE):
        cryptos = get_crypto_prices()
        p = cryptos.get("bitcoin", {}).get("usd", 67000)
        if p == 0:
            p = 67000
        iqd = p * MASTER_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"🟩 سعر البيتكوين المتقدم (BTC)\n\n"
            f"💲  بالسعر العالمي : {p:,.0f} USDT\n"
            f"🤩  بالدينار العراقي : {iqd:,.0f} د.ع\n\n"
            f"🔄  التحديث : {now}"
        )

        # Build blockquote entities
        entities = []
        line1_start = utf16_len(f"🟩 سعر البيتكوين المتقدم (BTC)\n\n")
        line1_text = f"💲  بالسعر العالمي : {p:,.0f} USDT"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"🤩  بالدينار العراقي : {iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"🔄  التحديث : {now}"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        emoji_map = {
            "🟩": 5312073533751325146,
            "💲": 5390875094027344872,
            "🤩": 5294390547803294400,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Ethereum - with or without "سعر/صرف" prefix
    if re.search(r'^(?:سعر|صرف)\s+(?:ال)?(eth|ايثيريوم)$', text_clean, re.IGNORECASE) or \
       re.search(r'^(?:ال)?(eth|ايثيريوم)$', text_clean, re.IGNORECASE):
        cryptos = get_crypto_prices()
        p = cryptos.get("ethereum", {}).get("usd", 3500)
        if p == 0:
            p = 3500
        iqd = p * MASTER_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"🪙 سعر الإيثيريوم المتقدم (ETH)\n\n"
            f"💲  بالسعر العالمي : {p:,.0f} USDT\n"
            f"🤩  بالدينار العراقي : {iqd:,.0f} د.ع\n\n"
            f"🔄  التحديث : {now}"
        )

        # Build blockquote entities
        entities = []
        line1_start = utf16_len(f"🪙 سعر الإيثيريوم المتقدم (ETH)\n\n")
        line1_text = f"💲  بالسعر العالمي : {p:,.0f} USDT"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"🤩  بالدينار العراقي : {iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"🔄  التحديث : {now}"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        emoji_map = {
            "🪙": 5202064723922670546,
            "💲": 5390875094027344872,
            "🤩": 5294390547803294400,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Solana - with or without "سعر/صرف" prefix
    if re.search(r'^(?:سعر|صرف)\s+(?:ال)?(sol|سولانا)$', text_clean, re.IGNORECASE) or \
       re.search(r'^(?:ال)?(sol|سولانا)$', text_clean, re.IGNORECASE):
        cryptos = get_crypto_prices()
        p = cryptos.get("solana", {}).get("usd", 145)
        if p == 0:
            p = 145
        iqd = p * MASTER_RATE
        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"🪙 سعر السولانا المتقدم (SOL)\n\n"
            f"💲  بالسعر العالمي : {p:,.2f} USDT\n"
            f"🤩  بالدينار العراقي : {iqd:,.0f} د.ع\n\n"
            f"🔄  التحديث : {now}"
        )

        # Build blockquote entities
        entities = []
        line1_start = utf16_len(f"🪙 سعر السولانا المتقدم (SOL)\n\n")
        line1_text = f"💲  بالسعر العالمي : {p:,.2f} USDT"
        entities.append({"type": "blockquote", "offset": line1_start, "length": utf16_len(line1_text)})

        line2_start = line1_start + utf16_len(line1_text) + 1
        line2_text = f"🤩  بالدينار العراقي : {iqd:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": line2_start, "length": utf16_len(line2_text)})

        line3_start = line2_start + utf16_len(line2_text) + 2
        line3_text = f"🔄  التحديث : {now}"
        entities.append({"type": "blockquote", "offset": line3_start, "length": utf16_len(line3_text)})

        emoji_map = {
            "🪙": 5202113974312653146,
            "💲": 5390875094027344872,
            "🤩": 5294390547803294400,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Binance P2P Market - with or without "سعر/صرف" prefix
    if re.search(r'^(?:سعر|صرف)\s+(?:ال)?(سوق|binance|p2p|سوبركي|superqi)$', text_clean, re.IGNORECASE) or \
       re.search(r'^(?:ال)?(سوق|binance|p2p|سوبركي|superqi)$', text_clean, re.IGNORECASE):
        prices = get_binance_p2p_superqi()
        now = datetime.now().strftime("%H:%M:%S")

        # Fallback prices if API fails
        if not prices:
            prices = [
                {"price": 1521, "seller": "User-75463"},
                {"price": 1521, "seller": "Halo_crypto"},
                {"price": 1521, "seller": "PRIME-1"},
                {"price": 1521, "seller": "SliM_15"},
                {"price": 1521, "seller": "يحيى1102"},
            ]

        text = f"🕯 أسعار Binance P2P - بيع USDT مقابل IQD (SuperQi)\n\n"
        text += "🔥  أفضل الأسعار :\n\n"

        for i, ad in enumerate(prices[:5], 1):
            # FIX: Extra spaces before/after emoji to prevent number overlap
            text += f"{i}.  🤩  {ad['price']:,.0f} د.ع  —  👤  {ad['seller']}\n"

        avg = sum(p['price'] for p in prices[:5]) / len(prices[:5])
        text += f"\n📈  متوسط السعر :  {avg:,.0f} د.ع\n"
        text += f"🔄  التحديث : {now}"

        # Build blockquote entities for price lines
        entities = []
        title_len = utf16_len(f"🕯 أسعار Binance P2P - بيع USDT مقابل IQD (SuperQi)\n\n🔥  أفضل الأسعار :\n\n")

        current_offset = title_len
        for i, ad in enumerate(prices[:5], 1):
            line_text = f"{i}.  🤩  {ad['price']:,.0f} د.ع  —  👤  {ad['seller']}"
            entities.append({"type": "blockquote", "offset": current_offset, "length": utf16_len(line_text)})
            current_offset += utf16_len(line_text) + 1

        # Empty line
        current_offset += 1

        avg_line = f"📈  متوسط السعر :  {avg:,.0f} د.ع"
        entities.append({"type": "blockquote", "offset": current_offset, "length": utf16_len(avg_line)})
        current_offset += utf16_len(avg_line) + 1

        update_line = f"🔄  التحديث : {now}"
        entities.append({"type": "blockquote", "offset": current_offset, "length": utf16_len(update_line)})

        emoji_map = {
            "🕯": 4956492465465984073,
            "🔥": 5461159437802698702,
            "🤩": 5294390547803294400,
            "👤": 5469664817373529894,
            "📈": 5469664817373529894,
            "🔄": 5778202206922608769,
        }
        for emoji_char, doc_id in emoji_map.items():
            pos = text.find(emoji_char)
            while pos != -1:
                entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_len(text[:pos]),
                    "length": utf16_len(emoji_char),
                    "custom_emoji_id": str(doc_id)
                })
                pos = text.find(emoji_char, pos + len(emoji_char))

        entities.sort(key=lambda x: x["offset"])

        payload = {
            "chat_id": chat_id,
            "text": text,
            "entities": json.dumps(entities) if entities else None,
            "reply_to_message_id": reply_to_message_id
        }
        bot("sendMessage", payload)
        return

    # Unknown command - reply in ALL chats with reply_to_message_id
    send_message_with_emoji(chat_id, "unknown", reply_to_message_id=reply_to_message_id)

# ─── Main loop (Polling) ─────────────────────────────────────────

def main():
    print("🤖 البوت يعمل... (Polling mode)")
    print("⏳ جاري الاستماع للرسائل...")
    offset = None

    while True:
        try:
            updates = get_updates(offset)
            for update in updates.get("result", []):
                offset = update["update_id"] + 1

                # Handle callback queries (inline buttons)
                if "callback_query" in update:
                    handle_callback(update)
                # Handle regular messages
                elif "message" in update:
                    handle_message(update)
        except Exception as exc:
            logging.error("Main loop error: %s", exc)
        time.sleep(1)

if __name__ == "__main__":
    main()
