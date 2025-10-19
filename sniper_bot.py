# =================================================================
# صياد الدرر: v4.7 (النسخة النهائية المستقرة) - محدث لـ AsyncWeb3 v6+
# =================================================================

import os
import json
import time
import asyncio
import logging
from typing import Dict, List, Any

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

# --- إعدادات الاتصال بالشبكة (BSC) ---
NODE_URL = os.getenv('NODE_URL')
if not NODE_URL:
    raise ValueError("❌ يجب تعيين NODE_URL في ملف .env!")

# --- إعدادات المحفظة ---
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')

# --- إعدادات التليجرام ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID')

# --- العناوين الثابتة ---
ROUTER_ADDRESS = os.getenv('ROUTER_ADDRESS', '0x10ED43C718714eb63d5aA57B78B54704E256024E')
FACTORY_ADDRESS = os.getenv('FACTORY_ADDRESS', '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73')
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# التحقق من المتغيرات الإلزامية
if not WALLET_ADDRESS or not PRIVATE_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
    raise ValueError("❌ تأكد من تعيين كل من: WALLET_ADDRESS, PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID في .env!")

logging.info("✅ تم تحميل الإعدادات المحصّنة بنجاح.")

# ... (باقي الكود كما هو في النسخة النهائية) ...

async def main():
    logging.info("--- بدأ تشغيل بوت صياد الدرر (v4.7 النسخة النهائية) ---")
    
    bot_state = {
        'is_paused': False,
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
    is_connected = await w3.is_connected()
    if not is_connected:
        logging.critical("❌ لا يمكن الاتصال بالشبكة. يتم الخروج."); return

    nonce_manager = مدير_الـNonce(w3, WALLET_ADDRESS)
    await nonce_manager.initialize()
    
    guardian = الحارس(w3, nonce_manager, None, bot_state)
    telegram_interface = واجهة_التليجرام(TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, bot_state, guardian)
    guardian.telegram = telegram_interface

    watcher = الراصد(w3)
    verifier = المدقق(w3, telegram_interface, bot_state)
    sniper = القناص(w3, nonce_manager, telegram_interface, bot_state)
    
    async def new_pool_handler(pair, token):
        asyncio.create_task(process_new_token(pair, token, verifier, sniper, guardian, bot_state, telegram_interface))

    logging.info("🚀 البوت جاهز على خط الانطلاق...")
    
    telegram_task = asyncio.create_task(telegram_interface.run())
    guardian_task = asyncio.create_task(guardian.monitor_trades())
    watcher_task = asyncio.create_task(watcher.استمع_للمجمعات_الجديدة(new_pool_handler))
    
    await asyncio.gather(telegram_task, guardian_task, watcher_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\n--- تم إيقاف البوت يدويًا ---")
    except Exception:
        logging.critical(f"❌ خطأ فادح في البرنامج الرئيسي:", exc_info=True)