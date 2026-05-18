import logging
import os
import json
import asyncio
import time
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# إعداد التسجيل بشكل احترافي
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# الإعدادات الأساسية
TOKEN = "8799827850:AAF_6bEXiJn7CQnUjrRQk6hELHOLy6ym-Kw"
MARKET_URL = "https://marketapp.ws/rent/?tab=market&subtab=gifts&view=grid&query=&sort_by=min_price&filter_by=&market_filter_by=&collections=3555&min_price=&max_price=&item_num_from=&item_num_to="
PROFIT_MARGIN = 0.6
CACHE_EXPIRY = 600  # التخزين المؤقت لمدة 10 دقائق

async def fetch_gifts_live():
    """
    جلب البيانات مباشرة من الموقع باستخدام متصفح حقيقي (Playwright).
    """
    logger.info("محاولة جلب البيانات الحية من الموقع...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # ضبط مهلة التحميل
            await page.goto(MARKET_URL, wait_until="networkidle", timeout=60000)
            
            # الانتظار حتى تظهر الهدايا (NFTs)
            try:
                await page.wait_for_selector("a[href*='/nft/']", timeout=20000)
            except:
                logger.warning("لم يتم العثور على عناصر NFT في الوقت المحدد.")
                await browser.close()
                return []

            content = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            gifts = []
            gift_links = soup.find_all('a', href=lambda x: x and x.startswith('/nft/'))
            
            for link in gift_links:
                img_tag = link.find('img')
                if not img_tag: continue
                
                image_url = img_tag.get('src')
                text_content = link.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text_content.split('|') if p.strip()]
                
                name = "Unknown"
                base_price = 0.0
                
                for part in parts:
                    if '#' in part:
                        name = part
                    try:
                        # استخراج السعر الرقمي
                        clean = part.replace('≤', '').replace('TON', '').strip()
                        val = float(clean)
                        if 0 < val < 100: base_price = val
                    except ValueError:
                        continue
                
                if name != "Unknown" and base_price > 0:
                    gifts.append({
                        'name': name,
                        'image_url': image_url,
                        'price': base_price,
                        'final_price': round(base_price + PROFIT_MARGIN, 2)
                    })
            
            # إزالة التكرار والترتيب من الأقل للأعلى
            unique = {g['name']: g for g in gifts}.values()
            return sorted(unique, key=lambda x: x['final_price'])
            
        except Exception as e:
            logger.error(f"خطأ أثناء جلب البيانات: {e}")
            return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 *أهلاً بك يا {user.first_name}!*\n\n"
        "هذا البوت مخصص لتأجير الهدايا من `MarketApp` مع إضافة نسبة ربح.\n\n"
        "✅ *مميزات البوت:*\n"
        "• جلب حي ومباشر للهدايا.\n"
        "• عرض الصور والأسعار بدقة.\n"
        "• خيارات تأجير (أسبوع، 15 يوم، شهر).\n\n"
        "اضغط على الزر أدناه لبدء التصفح 👇"
    )
    keyboard = [[InlineKeyboardButton("تصفح الهدايا المتاحة 🎁", callback_data='show_0')]]
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_display(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    index = int(query.data.split('_')[1])
    now = time.time()
    
    # إدارة التخزين المؤقت
    if ('gifts' not in context.bot_data or 
        now - context.bot_data.get('last_update', 0) > CACHE_EXPIRY or
        not context.bot_data['gifts']):
        
        status_msg = await query.message.reply_text("🔄 جاري تحديث البيانات من الموقع... قد يستغرق ذلك 10 ثوانٍ.")
        gifts = await fetch_gifts_live()
        context.bot_data['gifts'] = gifts
        context.bot_data['last_update'] = now
        await status_msg.delete()
    else:
        gifts = context.bot_data['gifts']

    if not gifts:
        await query.message.reply_text("❌ عذراً، تعذر العثور على هدايا حالياً. تأكد من اتصال الخادم بالإنترنت وحاول مجدداً.")
        return

    # ضبط الفهرس
    if index < 0: index = len(gifts) - 1
    if index >= len(gifts): index = 0
    
    gift = gifts[index]
    p = gift['final_price']
    
    caption = (
        f"🎁 *الهدية:* `{gift['name']}`\n"
        f"💰 *السعر اليومي:* `{p}` TON\n\n"
        f"🗓 *تكلفة التأجير:*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔹 7 أيام: `{round(p*7, 2)}` TON\n"
        f"🔹 15 يوم: `{round(p*15, 2)}` TON\n"
        f"🔹 30 يوم: `{round(p*30, 2)}` TON\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 _الهدية {index+1} من {len(gifts)}_"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🛒 تأجير 7 أيام", callback_data=f"rent_7_{index}"),
            InlineKeyboardButton("🛒 تأجير 15 يوم", callback_data=f"rent_15_{index}")
        ],
        [InlineKeyboardButton("🛒 تأجير 30 يوم", callback_data=f"rent_30_{index}")],
        [
            InlineKeyboardButton("⬅️ السابق", callback_data=f"show_{index-1}"),
            InlineKeyboardButton("التالي ➡️", callback_data=f"show_{index+1}")
        ],
        [InlineKeyboardButton("🔄 تحديث القائمة", callback_data="refresh")]
    ]

    try:
        if query.message.photo:
            await query.edit_message_media(
                media=InputMediaPhoto(media=gift['image_url'], caption=caption, parse_mode='Markdown'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=gift['image_url'],
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await query.delete_message()
    except Exception as e:
        logger.error(f"Error displaying gift: {e}")
        await query.message.reply_text("حدث خطأ أثناء عرض الصورة، يرجى المحاولة مجدداً.")

async def refresh_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.bot_data['gifts'] = None # إجبار البوت على التحديث
    query.data = "show_0"
    await handle_display(update, context)

async def rent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('_')
    days, idx = data[1], int(data[2])
    gift = context.bot_data['gifts'][idx]
    await query.answer(f"✅ تم اختيار {gift['name']} لمدة {days} يوم!", show_alert=True)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(refresh_data, pattern='^refresh$'))
    app.add_handler(CallbackQueryHandler(handle_display, pattern='^show_'))
    app.add_handler(CallbackQueryHandler(rent_callback, pattern='^rent_'))
    
    print("🚀 البوت يعمل الآن بنظام Playwright الحقيقي...")
    app.run_polling()
