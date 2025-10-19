# =================================================================
# صياد الدرر: v5.3 (مع نبضات قلب مرئية في السجل)
# =================================================================

import os
import json
import time
import asyncio
import logging
from typing import Dict, List, Any, Tuple

from dotenv import load_dotenv
from web3 import Web3, AsyncWeb3, AsyncHTTPProvider
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, 
                          ContextTypes, ConversationHandler, MessageHandler, filters)
from telegram.constants import ParseMode

# =================================================================
# 1. نظام التسجيل (Logging)
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sniper_bot.log"),
        logging.StreamHandler()
    ]
)

# =================================================================
# 2. واجهات العقود الذكية (ABIs)
# =================================================================
FACTORY_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"token0","type":"address"},{"indexed":true,"internalType":"address","name":"token1","type":"address"},{"indexed":false,"internalType":"address","name":"pair","type":"address"},{"indexed":false,"internalType":"uint256","name":"","type":"uint256"}],"name":"PairCreated","type":"event"}]')
PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"}]')
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"}]')
ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]')

# =================================================================
# 3. الإعدادات المركزية
# =================================================================
load_dotenv()
NODE_URL = os.getenv('NODE_URL')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID')
ROUTER_ADDRESS = os.getenv('ROUTER_ADDRESS', '0x10ED43C718714eb63d5aA57B78B54704E256024E')
FACTORY_ADDRESS = os.getenv('FACTORY_ADDRESS', '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73')
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

if not all([NODE_URL, WALLET_ADDRESS, PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID]):
    raise ValueError("❌ تأكد من تعيين كل المتغيرات المطلوبة في ملف .env!")
logging.info("✅ تم تحميل الإعدادات المحصّنة بنجاح.")

# =================================================================
# 4. فئة واجهة التليجرام (كاملة ومحدثة)
# =================================================================
(SELECTING_SETTING, TYPING_VALUE) = range(2)

class واجهة_التليجرام:
    def __init__(self, token, admin_id, bot_state, guardian_ref):
        self.application = Application.builder().token(token).build()
        self.admin_id = admin_id
        self.bot_state = bot_state
        self.guardian = guardian_ref
        
        settings_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^⚙️ الإعدادات$'), self.settings_menu)],
            states={
                SELECTING_SETTING: [CallbackQueryHandler(self.ask_for_new_value, pattern='^change_')],
                TYPING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.set_new_value)],
            },
            fallbacks=[CallbackQueryHandler(self.start_callback, pattern='^main_menu$')],
        )

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.Regex('^📊 الحالة$'), self.show_status))
        self.application.add_handler(MessageHandler(filters.Regex('^(⏸️ إيقاف القنص|▶️ استئناف القنص)$'), self.toggle_pause))
        self.application.add_handler(MessageHandler(filters.Regex('^(🟢 تفعيل التصحيح|⚪️ إيقاف التصحيح)$'), self.toggle_debug_mode))
        self.application.add_handler(MessageHandler(filters.Regex('^💰 بيع يدوي$'), self.show_sell_options))
        self.application.add_handler(MessageHandler(filters.Regex('^🔬 التشخيص$'), self.show_diagnostics))
        self.application.add_handler(settings_conv_handler)
        self.application.add_handler(CallbackQueryHandler(self.sell_button_handler, pattern='^sell_'))

    def _get_main_keyboard(self):
        pause_button_text = "▶️ استئناف القنص" if self.bot_state['is_paused'] else "⏸️ إيقاف القنص"
        debug_button_text = "⚪️ إيقاف التصحيح" if self.bot_state.get('DEBUG_MODE', False) else "🟢 تفعيل التصحيح"
        keyboard = [
            [KeyboardButton("📊 الحالة"), KeyboardButton(pause_button_text)],
            [KeyboardButton("💰 بيع يدوي"), KeyboardButton("⚙️ الإعدادات")],
            [KeyboardButton("🔬 التشخيص"), KeyboardButton(debug_button_text)]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def send_message(self, text, parse_mode=ParseMode.HTML):
        try:
            await self.application.bot.send_message(chat_id=self.admin_id, text=text, parse_mode=parse_mode)
        except Exception as e:
            logging.error(f"❌ خطأ في إرسال رسالة تليجرام: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message_to_reply = update.message if hasattr(update, 'message') and update.message else update
        chat_id = update.effective_chat.id if hasattr(update, 'effective_chat') else message_to_reply.chat.id
        if str(chat_id) != self.admin_id: return
        await message_to_reply.reply_text(
            '<b>أهلاً بك في مركز قيادة صياد الدرر!</b>',
            reply_markup=self._get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )

    async def start_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("تم العودة للقائمة الرئيسية.")
        await self.start(query.message, context)
        return ConversationHandler.END

    async def sell_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        token_address = query.data.split('_')[1]
        await query.edit_message_text(text=f"⏳ جاري بيع {token_address}...")
        success = await self.guardian.manual_sell_token(token_address)
        if success:
            await query.edit_message_text(text=f"✅ تم بيع {token_address} بنجاح!")
        else:
            await query.edit_message_text(text=f"❌ فشلت عملية بيع {token_address}.")
        await asyncio.sleep(2)
        await query.delete_message()

    async def show_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status_text = "<b>📊 الحالة الحالية للبوت:</b>\n\n"
        status_text += f"<b>الحالة:</b> {'موقوف مؤقتاً ⏸️' if self.bot_state['is_paused'] else 'نشط ▶️'}\n"
        status_text += f"<b>وضع التصحيح:</b> {'فعّال 🟢' if self.bot_state.get('DEBUG_MODE', False) else 'غير فعّال ⚪️'}\n"
        status_text += "-----------------------------------\n"
        if not self.guardian.active_trades:
            status_text += "ℹ️ لا توجد صفقات نشطة حالياً.\n"
        else:
            status_text += "<b>📈 الصفقات النشطة:</b>\n"
            for trade in self.guardian.active_trades:
                profit = trade.get('current_profit', 0)
                status_text += f"<b>- <code>{trade['token_address']}</code>:</b> {profit:.2f}%\n"
        
        status_text += "-----------------------------------\n"
        status_text += "<b>⚙️ إعدادات التداول:</b>\n"
        s = self.bot_state
        status_text += f"- مبلغ الشراء: {s['BUY_AMOUNT_BNB']} BNB\n"
        status_text += f"- إكرامية الغاز: {s['GAS_PRICE_TIP_GWEI']} Gwei\n"
        status_text += f"- الانزلاق السعري: {s['SLIPPAGE_LIMIT']}%\n"
        status_text += f"- حد السيولة: {s['MINIMUM_LIQUIDITY_BNB']} BNB\n"
        status_text += f"- الهدف 1: بيع {s['SELL_PERCENTAGE_1']}% عند ربح {s['TAKE_PROFIT_THRESHOLD_1']}%\n"
        status_text += f"- الهدف 2: بيع {s['SELL_PERCENTAGE_2']}% عند ربح {s['TAKE_PROFIT_THRESHOLD_2']}%\n"
        status_text += f"- وقف الخسارة: {s['STOP_LOSS_THRESHOLD']}%\n"
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)

    async def toggle_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.bot_state['is_paused'] = not self.bot_state['is_paused']
        status = "موقوف مؤقتاً ⏸️" if self.bot_state['is_paused'] else "نشط ▶️"
        await self.send_message(f"ℹ️ حالة قنص العملات الجديدة الآن: <b>{status}</b>")
        await self.start(update.message, context)

    async def toggle_debug_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.bot_state['DEBUG_MODE'] = not self.bot_state.get('DEBUG_MODE', False)
        status = "فعّال 🟢" if self.bot_state['DEBUG_MODE'] else "غير فعّال ⚪️"
        logging.info(f"⚙️ تم تغيير وضع التصحيح إلى: {status}")
        await self.send_message(f"ℹ️ وضع التصحيح الآن: <b>{status}</b>")
        await self.start(update.message, context)

    async def show_sell_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.guardian.active_trades:
            await update.message.reply_text("ℹ️ لا توجد صفقات نشطة لبيعها.")
            return
        keyboard = [[InlineKeyboardButton(f"بيع {t['token_address'][:6]}...{t['token_address'][-4:]}", callback_data=f"sell_{t['token_address']}")] for t in self.guardian.active_trades]
        await update.message.reply_text("<b>اختر العملة التي تريد بيعها:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def show_diagnostics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            with open("sniper_bot.log", "r", encoding='utf-8') as f:
                lines = f.readlines()[-20:]
                log_data = "".join(lines)
                if not log_data: log_data = "ملف السجل فارغ."
        except FileNotFoundError:
            log_data = "ملف السجل لم يتم إنشاؤه بعد."
        await update.message.reply_text(f"<b>🔬 آخر 20 سطراً من سجل التشخيص:</b>\n\n<pre>{log_data}</pre>", parse_mode=ParseMode.HTML)

    async def settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        s = self.bot_state
        keyboard = [
            [InlineKeyboardButton(f"💵 مبلغ الشراء ({s['BUY_AMOUNT_BNB']} BNB)", callback_data='change_BUY_AMOUNT_BNB')],
            [InlineKeyboardButton(f"🚀 إكرامية الغاز ({s['GAS_PRICE_TIP_GWEI']} Gwei)", callback_data='change_GAS_PRICE_TIP_GWEI')],
            [InlineKeyboardButton(f"📊 الانزلاق ({s['SLIPPAGE_LIMIT']}%)", callback_data='change_SLIPPAGE_LIMIT')],
            [InlineKeyboardButton(f"💧 حد السيولة ({s['MINIMUM_LIQUIDITY_BNB']} BNB)", callback_data='change_MINIMUM_LIQUIDITY_BNB')],
            [InlineKeyboardButton(f"🎯 هدف الربح 1 ({s['TAKE_PROFIT_THRESHOLD_1']}%)", callback_data='change_TAKE_PROFIT_THRESHOLD_1'),
             InlineKeyboardButton(f"📦 الكمية ({s['SELL_PERCENTAGE_1']}%)", callback_data='change_SELL_PERCENTAGE_1')],
            [InlineKeyboardButton(f"🎯 هدف الربح 2 ({s['TAKE_PROFIT_THRESHOLD_2']}%)", callback_data='change_TAKE_PROFIT_THRESHOLD_2'),
             InlineKeyboardButton(f"📦 الكمية ({s['SELL_PERCENTAGE_2']}%)", callback_data='change_SELL_PERCENTAGE_2')],
            [InlineKeyboardButton(f"🛑 وقف الخسارة ({s['STOP_LOSS_THRESHOLD']}%)", callback_data='change_STOP_LOSS_THRESHOLD')],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='main_menu')]
        ]
        await update.message.reply_text("<b>⚙️ اختر الإعداد الذي تريد تغييره:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return SELECTING_SETTING

    async def ask_for_new_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        setting_key = query.data.replace('change_', '')
        context.user_data['setting_to_change'] = setting_key
        
        prompts = {
            "BUY_AMOUNT_BNB": "يرجى إرسال مبلغ الشراء الجديد بالـ BNB (مثال: 0.01):",
            "GAS_PRICE_TIP_GWEI": "يرجى إرسال إكرامية الغاز الجديدة بالـ Gwei (مثال: 1):",
            "SLIPPAGE_LIMIT": "يرجى إرسال نسبة الانزلاق السعري الجديدة (مثال: 49):",
            "MINIMUM_LIQUIDITY_BNB": "يرجى إرسال الحد الأدنى للسيولة بالـ BNB (مثال: 5.0):",
            "TAKE_PROFIT_THRESHOLD_1": "يرجى إرسال نسبة الهدف الأول للربح (مثال: 100):",
            "SELL_PERCENTAGE_1": "يرجى إرسال نسبة البيع للهدف الأول (مثال: 50):",
            "TAKE_PROFIT_THRESHOLD_2": "يرجى إرسال نسبة الهدف الثاني للربح (مثال: 300):",
            "SELL_PERCENTAGE_2": "يرجى إرسال نسبة البيع للهدف الثاني (مثال: 100):",
            "STOP_LOSS_THRESHOLD": "يرجى إرسال نسبة وقف الخسارة (مثال: -50):"
        }
        await query.edit_message_text(prompts.get(setting_key, "قيمة غير معروفة."))
        return TYPING_VALUE

    async def set_new_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        setting_key = context.user_data.pop('setting_to_change', None)
        if not setting_key:
            await self.start(update.message, context)
            return ConversationHandler.END

        new_value_str = update.message.text
        try:
            current_value = self.bot_state[setting_key]
            if isinstance(current_value, float): new_value = float(new_value_str)
            else: new_value = int(new_value_str)
            self.bot_state[setting_key] = new_value
            await update.message.reply_text(f"✅ تم تحديث {setting_key} إلى: {new_value}")
            logging.info(f"⚙️ تم تغيير {setting_key} ديناميكياً إلى {new_value}.")
        except (ValueError, KeyError):
            await update.message.reply_text("❌ قيمة غير صالحة. يرجى إدخال رقم صحيح.")
        await self.start(update.message, context)
        return ConversationHandler.END

    async def run(self):
        await self.send_message("✅ <b>تم تشغيل بوت صياد الدرر (v5.3) بنجاح!</b>")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

# =================================================================
# 5. الوحدات الأساسية (كاملة ومحدثة)
# =================================================================
class مدير_الـNonce:
    def __init__(self, w3: AsyncWeb3, address: str, filename="nonce.txt"):
        self.w3 = w3
        self.address = Web3.to_checksum_address(address)
        self.filename = filename
        self.lock = asyncio.Lock()
        self.nonce = 0
    def _read_from_file(self) -> int:
        try:
            with open(self.filename, 'r') as f: return int(f.read())
        except (FileNotFoundError, ValueError): return 0
    def _save_to_file(self, nonce_to_save: int):
        with open(self.filename, 'w') as f: f.write(str(nonce_to_save))
    async def initialize(self):
        async with self.lock:
            chain_nonce = await self.w3.eth.get_transaction_count(self.address)
            file_nonce = self._read_from_file()
            self.nonce = max(chain_nonce, file_nonce)
            self._save_to_file(self.nonce)
            logging.info(f"🔑 مدير الـ Nonce جاهز. الـ Nonce الأولي: {self.nonce}")
    async def get_next(self) -> int:
        async with self.lock:
            current_nonce = self.nonce
            self.nonce += 1
            self._save_to_file(self.nonce)
            return current_nonce

class الراصد:
    def __init__(self, w3: AsyncWeb3, telegram_interface: "واجهة_التليجرام"):
        self.w3 = w3
        self.telegram = telegram_interface
        self.factory_contract = self.w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        logging.info("✅ الراصد متصل وجاهز للاستماع والفحص الصحي.")
    
    async def check_connection_periodically(self):
        """[ترقية] يتحقق بشكل دوري من الاتصال ويرسل إنذاراً عند الفشل."""
        while True:
            await asyncio.sleep(60) # انتظر 60 ثانية قبل الفحص
            try:
                await asyncio.wait_for(self.w3.eth.block_number, timeout=15.0)
                # --- التعديل هنا ---
                logging.info("❤️ [نبض القلب] الاتصال بالشبكة سليم.")
            except asyncio.TimeoutError:
                logging.critical("🚨 [فحص صحي] فشل الاتصال بالشبكة (انتهت المهلة).")
                await self.telegram.send_message("🚨 <b>انقطاع الاتصال!</b> 🚨\n\nفشل الاتصال بعقدة البلوك تشين (انتهت المهلة). سيستمر البوت في محاولة إعادة الاتصال تلقائياً.")
            except Exception as e:
                logging.critical(f"🚨 [فحص صحي] خطأ فادح في الاتصال بالشبكة: {e}")
                await self.telegram.send_message(f"🚨 <b>انقطاع الاتصال!</b> 🚨\n\nحدث خطأ فادح في الاتصال: {e}\n\nسيستمر البوت في محاولة إعادة الاتصال تلقائياً.")

    async def استمع_للمجمعات_الجديدة(self, handler_func: callable):
        event_filter = await self.factory_contract.events.PairCreated.create_filter(from_block='latest')
        logging.info("👂 بدء الاستماع لحدث PairCreated...")
        while True:
            try:
                new_entries = await self.w3.eth.get_filter_changes(event_filter.filter_id)
                for event in new_entries:
                    if 'args' in event:
                        pair_address = event['args']['pair']
                        token0 = event['args']['token0']
                        token1 = event['args']['token1']
                        new_token = token1 if token0.lower() == WBNB_ADDRESS.lower() else token0
                        logging.info(f"🔔 تم اكتشاف مجمع جديد: {pair_address} | العملة: {new_token}")
                        asyncio.create_task(handler_func(pair_address, new_token))
            except Exception as e:
                logging.warning(f"⚠️ خطأ أثناء الاستماع في الراصد: {e}")
                if 'filter not found' in str(e).lower():
                    logging.info("   [الراصد] الفلتر غير موجود، سيتم إعادة إنشائه...")
                    event_filter = await self.factory_contract.events.PairCreated.create_filter(from_block='latest')
                else:
                    await asyncio.sleep(5)
            await asyncio.sleep(2)

class المدقق:
    def __init__(self, w3: AsyncWeb3, telegram_interface: "واجهة_التليجرام", bot_state: Dict):
        self.w3 = w3
        self.router_contract = self.w3.eth.contract(address=Web3.to_checksum_address(ROUTER_ADDRESS), abi=ROUTER_ABI)
        self.telegram = telegram_interface
        self.bot_state = bot_state
        logging.info("✅ المدقق جاهز (مع فلترة سيولة ومحاكاة بيع).")
    
    async def فحص_أولي_سريع(self, pair_address: str) -> Tuple[bool, float]:
        logging.info(f"   [فحص سريع] التحقق من سيولة المجمع: {pair_address}")
        try:
            pair_contract = self.w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
            reserves = await pair_contract.functions.getReserves().call()
            token0_address = await pair_contract.functions.token0().call()
            wbnb_reserve_wei = reserves[0] if token0_address.lower() == WBNB_ADDRESS.lower() else reserves[1]
            wbnb_reserve = Web3.from_wei(wbnb_reserve_wei, 'ether')
            logging.info(f"   [فحص سريع] السيولة المكتشفة: {wbnb_reserve:.2f} BNB")
            if wbnb_reserve >= self.bot_state['MINIMUM_LIQUIDITY_BNB']:
                logging.info(f"   [فحص سريع] ✅ نجح. السيولة كافية.")
                return True, wbnb_reserve
            else:
                logging.warning(f"   [فحص سريع] 🔻 فشل. السيولة أقل من الحد المطلوب.")
                return False, wbnb_reserve
        except Exception as e:
            logging.error(f"   [فحص سريع] ⚠️ خطأ أثناء فحص السيولة: {e}")
            return False, 0

    async def محاكاة_عملية_بيع(self, token_address: str) -> Tuple[bool, str]:
        logging.info(f"   [محاكاة البيع] التحقق من إمكانية بيع {token_address}")
        try:
            checksum_token = Web3.to_checksum_address(token_address)
            checksum_wallet = Web3.to_checksum_address(WALLET_ADDRESS)
            await self.router_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                1, 0, [checksum_token, Web3.to_checksum_address(WBNB_ADDRESS)], checksum_wallet, int(time.time()) + 120
            ).call({'from': checksum_wallet})
            logging.info("   [محاكاة البيع] ✅ نجحت المحاكاة. العملة قابلة للبيع.")
            return True, "العملة قابلة للبيع"
        except Exception as e:
            error_message = str(e)
            logging.warning(f"   [محاكاة البيع] 🚨🚨🚨 فشلت المحاكاة! على الأغلب Honeypot. الخطأ: {error_message}")
            return False, error_message
    
    async def فحص_شامل(self, pair_address: str, token_address: str) -> Tuple[bool, str]:
        liquidity_passed, wbnb_reserve = await self.فحص_أولي_سريع(pair_address)
        if not liquidity_passed:
            return False, f"سيولة غير كافية ({wbnb_reserve:.2f} BNB)"
        
        sell_sim_passed, error_msg = await self.محاكاة_عملية_بيع(token_address)
        if not sell_sim_passed:
            return False, f"فخ عسل (Honeypot) - {error_msg}"
            
        return True, "اجتاز كل الفحوصات"

class القناص:
    def __init__(self, w3: AsyncWeb3, nonce_manager: "مدير_الـNonce", telegram_interface: "واجهة_التليجرام", bot_state: Dict):
        self.w3 = w3
        self.nonce_manager = nonce_manager
        self.telegram = telegram_interface
        self.bot_state = bot_state
        self.router_contract = self.w3.eth.contract(address=Web3.to_checksum_address(ROUTER_ADDRESS), abi=ROUTER_ABI)
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        logging.info("✅ القناص جاهز (مع غاز ديناميكي).")

    async def _get_dynamic_gas(self) -> int:
        base_price = await self.w3.eth.gas_price
        tip = Web3.to_wei(self.bot_state['GAS_PRICE_TIP_GWEI'], 'gwei')
        return base_price + tip
    
    async def _approve_max(self, token_address: str):
        logging.info(f"   [موافقة] جاري عمل Approve لكمية لا نهائية لـ {token_address}...")
        try:
            checksum_token = Web3.to_checksum_address(token_address)
            token_contract = self.w3.eth.contract(address=checksum_token, abi=ERC20_ABI)
            max_amount = 2**256 - 1
            approve_tx = await token_contract.functions.approve(Web3.to_checksum_address(ROUTER_ADDRESS), max_amount).build_transaction({
                'from': self.account.address,
                'gasPrice': await self._get_dynamic_gas(), 
                'gas': 100000, 
                'nonce': await self.nonce_manager.get_next()
            })
            signed_tx = self.account.sign_transaction(approve_tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            logging.info(f"   [موافقة] ✅ تمت الموافقة بنجاح لـ {token_address}")
        except Exception as e:
            logging.error(f"   [موافقة] ❌ فشلت عملية الموافقة: {e}")

    async def تنفيذ_الشراء(self, token_address: str) -> Dict[str, Any]:
        try:
            logging.info(f"🚀🚀🚀 بدء عملية قنص وشراء العملة: {token_address} 🚀🚀🚀")
            bnb_amount_wei = Web3.to_wei(self.bot_state['BUY_AMOUNT_BNB'], 'ether')
            path = [Web3.to_checksum_address(WBNB_ADDRESS), Web3.to_checksum_address(token_address)]
            
            amounts_out = await self.router_contract.functions.getAmountsOut(bnb_amount_wei, path).call()
            min_tokens = int(amounts_out[1] * (1 - (self.bot_state['SLIPPAGE_LIMIT'] / 100)))

            tx_params = {
                'from': self.account.address, 'value': bnb_amount_wei,
                'gas': self.bot_state['GAS_LIMIT'], 'gasPrice': await self._get_dynamic_gas(),
                'nonce': await self.nonce_manager.get_next(),
            }
            
            tx = await self.router_contract.functions.swapExactETHForTokens(
                min_tokens, path, self.account.address, int(time.time()) + 120
            ).build_transaction(tx_params)

            signed_tx = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            logging.info(f"   هاش معاملة الشراء: {tx_hash.hex()}")
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            if receipt['status'] == 1:
                logging.info(f"💰 نجحت عملية الشراء! تم قنص {token_address}.")
                asyncio.create_task(self._approve_max(token_address))
                token_contract = self.w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
                decimals = await token_contract.functions.decimals().call()
                amount_bought_wei = amounts_out[1]
                buy_price = self.bot_state['BUY_AMOUNT_BNB'] / (amount_bought_wei / (10**decimals)) if amount_bought_wei > 0 else 0

                msg = f"💰 <b>نجحت عملية الشراء!</b> 💰\n\n<b>العملة:</b> <code>{token_address}</code>\n<b>المبلغ:</b> {self.bot_state['BUY_AMOUNT_BNB']} BNB\n<b>سعر الشراء:</b> ${buy_price:.10f}\n<b>رابط المعاملة:</b> <a href='https://bscscan.com/tx/{tx_hash.hex()}'>BscScan</a>"
                await self.telegram.send_message(msg)

                return {"success": True, "token_address": token_address, "buy_price": buy_price, "amount_bought_wei": amount_bought_wei, "decimals": decimals}
            else:
                logging.error(f"🚨 فشلت معاملة الشراء (الحالة 0).")
                return {"success": False}
        except Exception:
            logging.exception(f"❌ خطأ في تنفيذ الشراء:")
            return {"success": False}

class الحارس:
    def __init__(self, w3: AsyncWeb3, nonce_manager: "مدير_الـNonce", telegram_interface: "واجهة_التليجرام", bot_state: Dict):
        self.w3 = w3
        self.nonce_manager = nonce_manager
        self.telegram = telegram_interface
        self.bot_state = bot_state
        self.router_contract = self.w3.eth.contract(address=Web3.to_checksum_address(ROUTER_ADDRESS), abi=ROUTER_ABI)
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        self.active_trades: List[Dict] = []
        logging.info("✅ الحارس المحصّن مستيقظ ويراقب...")

    def add_trade(self, trade_details: Dict):
        trade = {
            "token_address": trade_details["token_address"], "buy_price": trade_details["buy_price"],
            "initial_amount_wei": trade_details["amount_bought_wei"], "remaining_amount_wei": trade_details["amount_bought_wei"],
            "decimals": trade_details["decimals"], "tp1_triggered": False, "tp2_triggered": False, "current_profit": 0
        }
        self.active_trades.append(trade)
        logging.info(f"🛡️ [الحارس] بدأ مراقبة العملة: {trade['token_address']}")

    async def _get_dynamic_gas(self) -> int:
        base_price = await self.w3.eth.gas_price
        tip = Web3.to_wei(self.bot_state['GAS_PRICE_TIP_GWEI'], 'gwei')
        return base_price + tip

    async def _get_current_price(self, trade: Dict) -> float:
        try:
            one_token = 1 * (10**trade["decimals"])
            path = [Web3.to_checksum_address(trade["token_address"]), Web3.to_checksum_address(WBNB_ADDRESS)]
            amounts_out = await self.router_contract.functions.getAmountsOut(one_token, path).call()
            return Web3.from_wei(amounts_out[1], 'ether')
        except Exception: return 0.0

    async def _execute_sell(self, trade: Dict, amount_to_sell_wei: int, manual=False) -> bool:
        token_address = trade['token_address']
        logging.info(f"💸 [الحارس] بدء عملية البيع لـ {token_address}...")
        try:
            path = [Web3.to_checksum_address(token_address), Web3.to_checksum_address(WBNB_ADDRESS)]
            tx_params = {
                'from': self.account.address, 'gas': self.bot_state['GAS_LIMIT'], 
                'gasPrice': await self._get_dynamic_gas(),
                'nonce': await self.nonce_manager.get_next()
            }
            swap_tx = await self.router_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                amount_to_sell_wei, 0, path, self.account.address, int(time.time()) + 300
            ).build_transaction(tx_params)
            signed_swap = self.account.sign_transaction(swap_tx)
            swap_hash = await self.w3.eth.send_raw_transaction(signed_swap.rawTransaction)
            logging.info(f"   - هاش البيع: {swap_hash.hex()}")
            receipt = await self.w3.eth.wait_for_transaction_receipt(swap_hash, timeout=180)
            
            if receipt['status'] == 1:
                sell_type = "يدوية" if manual else "تلقائية"
                msg = f"💸 <b>نجحت عملية البيع ({sell_type})!</b> 💸\n\n<b>العملة:</b> <code>{token_address}</code>\n<b>رابط المعاملة:</b> <a href='https://bscscan.com/tx/{swap_hash.hex()}'>BscScan</a>"
                await self.telegram.send_message(msg)
                logging.info(f"   - 💰💰💰 نجحت عملية البيع لـ {token_address}!")
                return True
            else:
                logging.error(f"   - 🚨 فشلت معاملة البيع لـ {token_address} (الحالة 0).")
                return False
        except Exception:
            logging.exception(f"   - ❌ خطأ فادح في عملية البيع:")
            return False
            
    async def manual_sell_token(self, token_address: str) -> bool:
        trade_to_sell = next((t for t in self.active_trades if t['token_address'] == token_address), None)
        if trade_to_sell:
            success = await self._execute_sell(trade_to_sell, trade_to_sell['remaining_amount_wei'], manual=True)
            if success: self.active_trades.remove(trade_to_sell)
            return success
        return False

    async def monitor_trades(self):
        while True:
            if not self.active_trades:
                await asyncio.sleep(2); continue
            price_tasks = [self._get_current_price(trade) for trade in self.active_trades]
            current_prices = await asyncio.gather(*price_tasks, return_exceptions=True)
            for i, trade in enumerate(list(self.active_trades)):
                price = current_prices[i]
                if isinstance(price, Exception) or price == 0:
                    trade['current_profit'] = -100; continue
                profit = ((price - trade["buy_price"]) / trade["buy_price"]) * 100 if trade["buy_price"] > 0 else 0
                trade['current_profit'] = profit
                if not trade["tp1_triggered"] and profit >= self.bot_state['TAKE_PROFIT_THRESHOLD_1']:
                    trade["tp1_triggered"] = True
                    logging.info(f"🎯 [الحارس] تفعيل الهدف الأول للربح لـ {trade['token_address']}")
                    amount = int(trade['initial_amount_wei'] * (self.bot_state['SELL_PERCENTAGE_1'] / 100))
                    if await self._execute_sell(trade, amount): trade['remaining_amount_wei'] -= amount
                if not trade["tp2_triggered"] and profit >= self.bot_state['TAKE_PROFIT_THRESHOLD_2']:
                    trade["tp2_triggered"] = True
                    logging.info(f"🎯 [الحارس] تفعيل الهدف الثاني للربح لـ {trade['token_address']}")
                    if await self._execute_sell(trade, trade['remaining_amount_wei']): self.active_trades.remove(trade)
                if profit <= self.bot_state['STOP_LOSS_THRESHOLD']:
                    logging.warning(f"🚨 [الحارس] تفعيل وقف الخسارة لـ {trade['token_address']}")
                    if await self._execute_sell(trade, trade['remaining_amount_wei']): self.active_trades.remove(trade)
            await asyncio.sleep(5)

# =================================================================
# 6. البرنامج الرئيسي ونقطة الانطلاق
# =================================================================

async def process_new_token(pair_address, token_address, verifier, sniper, guardian, bot_state, telegram_if):
    if bot_state['is_paused']:
        logging.info(f"   [تجاهل] تم تجاهل {token_address} لأن القنص موقوف مؤقتاً.")
        return
    logging.info(f"\n[مهمة جديدة] بدأت معالجة العملة: {token_address}")
    
    passed, reason = await verifier.فحص_شامل(pair_address, token_address)

    if passed:
        await telegram_if.send_message(f"✅ <b>عملة اجتازت الفحص!</b>\n\n<code>{token_address}</code>\n\n🚀 جاري محاولة القنص...")
        trade_result = await sniper.تنفيذ_الشراء(token_address)
        if trade_result.get("success"):
            guardian.add_trade(trade_result)
    else:
        logging.warning(f"🔻 [مهمة منتهية] تم تجاهل {token_address} (السبب: {reason}).")
        if bot_state.get('DEBUG_MODE', False):
             await telegram_if.send_message(f"⚪️ <b>تم تجاهل عملة</b>\n\n<code>{token_address}</code>\n\n<b>السبب:</b> {reason}")

async def main():
    logging.info("--- بدأ تشغيل بوت صياد الدرر (v5.3 نسخة النبضات المرئية) ---")
    
    bot_state = {
        'is_paused': False,
        'DEBUG_MODE': os.getenv('DEBUG_MODE', 'False').lower() in ('true', '1', 't'),
        'BUY_AMOUNT_BNB': float(os.getenv('BUY_AMOUNT_BNB', '0.01')),
        'GAS_PRICE_TIP_GWEI': int(os.getenv('GAS_PRICE_TIP_GWEI', '1')),
        'SLIPPAGE_LIMIT': int(os.getenv('SLIPPAGE_LIMIT', '49')),
        'GAS_LIMIT': int(os.getenv('GAS_LIMIT', '600000')),
        'MINIMUM_LIQUIDITY_BNB': float(os.getenv('MINIMUM_LIQUIDITY_BNB', '5.0')),
        'TAKE_PROFIT_THRESHOLD_1': int(os.getenv('TAKE_PROFIT_THRESHOLD_1', '100')),
        'SELL_PERCENTAGE_1': int(os.getenv('SELL_PERCENTAGE_1', '50')),
        'TAKE_PROFIT_THRESHOLD_2': int(os.getenv('TAKE_PROFIT_THRESHOLD_2', '300')),
        'SELL_PERCENTAGE_2': int(os.getenv('SELL_PERCENTAGE_2', '100')),
        'STOP_LOSS_THRESHOLD': int(os.getenv('STOP_LOSS_THRESHOLD', '-50')),
    }
    
    w3 = AsyncWeb3(AsyncHTTPProvider(NODE_URL))
    if not await w3.is_connected():
        logging.critical("❌ لا يمكن الاتصال بالشبكة عند البدء. يتم الخروج."); return

    nonce_manager = مدير_الـNonce(w3, WALLET_ADDRESS)
    await nonce_manager.initialize()
    
    guardian = الحارس(w3, nonce_manager, None, bot_state) # سيتم ربط التليجرام لاحقاً
    telegram_interface = واجهة_التليجرام(TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, bot_state, guardian)
    guardian.telegram = telegram_interface

    watcher = الراصد(w3, telegram_interface)
    verifier = المدقق(w3, telegram_interface, bot_state)
    sniper = القناص(w3, nonce_manager, telegram_interface, bot_state)
    
    async def new_pool_handler(pair, token):
        asyncio.create_task(process_new_token(pair, token, verifier, sniper, guardian, bot_state, telegram_interface))

    logging.info("🚀 البوت جاهز على خط الانطلاق...")
    
    telegram_task = asyncio.create_task(telegram_interface.run())
    guardian_task = asyncio.create_task(guardian.monitor_trades())
    watcher_task = asyncio.create_task(watcher.استمع_للمجمعات_الجديدة(new_pool_handler))
    health_check_task = asyncio.create_task(watcher.check_connection_periodically())
    
    await asyncio.gather(telegram_task, guardian_task, watcher_task, health_check_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\n--- تم إيقاف البوت يدويًا ---")
    except Exception:
        logging.critical(f"❌ خطأ فادح في البرنامج الرئيسي:", exc_info=True)


