# =================================================================
# صياد الدرر: النسخة النهائية الكاملة والمحصّنة (v2.0)
# تم تنفيذ ودمج جميع التحسينات المتقدمة بشكل كامل.
# =================================================================

import os
import json
import time
import asyncio
from typing import Dict, List, Any

from dotenv import load_dotenv
from web3 import Web3

# =================================================================
# 1. الإعدادات المركزية
# =================================================================
load_dotenv()

# --- إعدادات الاتصال بالشبكة (BSC) ---
NODE_URL_WS = os.getenv('NODE_URL')
if not NODE_URL_WS:
    raise ValueError("❌ يجب تعيين NODE_URL في ملف .env!")

# --- إعدادات المحفظة ---
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
PRIVATE_KEY = '0x' + os.getenv('PRIVATE_KEY', '')

# --- إعدادات الشراء والبيع ---
BUY_AMOUNT_BNB = float(os.getenv('BUY_AMOUNT_BNB', '0.01'))
SLIPPAGE_LIMIT = int(os.getenv('SLIPPAGE_LIMIT', '49'))
GAS_LIMIT = int(os.getenv('GAS_LIMIT', '600000'))
MINIMUM_LIQUIDITY_BNB = float(os.getenv('MINIMUM_LIQUIDITY_BNB', '5.0'))
GAS_PRICE_TIP_GWEI = int(os.getenv('GAS_PRICE_TIP_GWEI', '1')) 

# --- إعدادات الحارس (البيع الآلي) ---
TAKE_PROFIT_THRESHOLD_1 = int(os.getenv('TAKE_PROFIT_THRESHOLD_1', '100'))
SELL_PERCENTAGE_1 = int(os.getenv('SELL_PERCENTAGE_1', '50'))
TAKE_PROFIT_THRESHOLD_2 = int(os.getenv('TAKE_PROFIT_THRESHOLD_2', '300'))
SELL_PERCENTAGE_2 = int(os.getenv('SELL_PERCENTAGE_2', '100'))
STOP_LOSS_THRESHOLD = int(os.getenv('STOP_LOSS_THRESHOLD', '-50'))

# --- العناوين الثابتة ---
ROUTER_ADDRESS = os.getenv('ROUTER_ADDRESS', '0x10ED43C718714eb63d5aA57B78B54704E256024E')
FACTORY_ADDRESS = os.getenv('FACTORY_ADDRESS', '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73')
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# التحقق من المتغيرات الإلزامية
if not WALLET_ADDRESS or not os.getenv('PRIVATE_KEY'):
    raise ValueError("❌ يجب تعيين WALLET_ADDRESS و PRIVATE_KEY في .env!")

print("✅ تم تحميل الإعدادات المحصّنة بنجاح.")

# =================================================================
# 2. ABIs (واجهات العقود الذكية)
# =================================================================
FACTORY_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"token0","type":"address"},{"indexed":true,"internalType":"address","name":"token1","type":"address"},{"indexed":false,"internalType":"address","name":"pair","type":"address"},{"indexed":false,"internalType":"uint256","name":"","type":"uint256"}],"name":"PairCreated","type":"event"}]')
PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"}]')
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"}]')
ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]')

# =================================================================
# 3. مدير الـ Nonce (مع خاصية الاستمرارية)
# =================================================================
class مدير_الـNonce:
    def __init__(self, web3: Web3, address: str, filename="nonce.txt"):
        self.web3 = web3
        self.address = address
        self.filename = filename
        self.lock = asyncio.Lock()
        self.nonce = 0

    def _read_from_file(self) -> int:
        try:
            with open(self.filename, 'r') as f:
                return int(f.read())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_to_file(self, nonce_to_save: int):
        with open(self.filename, 'w') as f:
            f.write(str(nonce_to_save))

    async def initialize(self):
        async with self.lock:
            chain_nonce = await asyncio.to_thread(self.web3.eth.get_transaction_count, self.address)
            file_nonce = self._read_from_file()
            self.nonce = max(chain_nonce, file_nonce)
            self._save_to_file(self.nonce)
            print(f"🔑 مدير الـ Nonce جاهز. الـ Nonce الأولي: {self.nonce} (الأعلى من الشبكة والملف)")

    async def get_next(self) -> int:
        async with self.lock:
            current_nonce = self.nonce
            self.nonce += 1
            self._save_to_file(self.nonce)
            return current_nonce

# =================================================================
# 4. الوحدات الأساسية
# =================================================================

class الراصد:
    def __init__(self, web3: Web3):
        self.web3 = web3
        self.factory_contract = self.web3.eth.contract(address=FACTORY_ADDRESS, abi=FACTORY_ABI)
        print("✅ الراصد متصل وجاهز للاستماع.")

    async def استمع_للمجمعات_الجديدة(self, handler_func: callable):
        event_filter = await asyncio.to_thread(self.factory_contract.events.PairCreated.create_filter, fromBlock='latest')
        print("👂 بدء الاستماع لحدث PairCreated...")
        while True:
            try:
                new_entries = await asyncio.to_thread(event_filter.get_new_entries)
                for event in new_entries:
                    # --- التحصين: التحقق من سلامة الحدث قبل المعالجة ---
                    if 'args' not in event:
                        print("   [تجاهل] تم استلام حدث غير مكتمل، يتم تجاهله.")
                        continue
                    # ----------------------------------------------------
                    token0 = event['args']['token0']
                    token1 = event['args']['token1']
                    pair_address = event['args']['pair']
                    
                    new_token = token1 if token0.lower() == WBNB_ADDRESS.lower() else token0
                    print(f"\n🔔 تم اكتشاف مجمع جديد: {pair_address}")
                    print(f"   العملة الجديدة: {new_token}")
                    
                    asyncio.create_task(handler_func(pair_address, new_token))
            except Exception as e:
                print(f"⚠️ خطأ أثناء الاستماع في الراصد: {e}")
                await asyncio.sleep(5)
            await asyncio.sleep(1)

class المدقق:
    def __init__(self, web3: Web3):
        self.web3 = web3
        self.router_contract = self.web3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
        print("✅ المدقق جاهز (مع فلترة سيولة ومحاكاة بيع).")

    async def فحص_أولي_سريع(self, pair_address: str) -> bool:
        print(f"   [فحص سريع] التحقق من سيولة المجمع: {pair_address}")
        try:
            pair_contract = self.web3.eth.contract(address=pair_address, abi=PAIR_ABI)
            reserves = await asyncio.to_thread(pair_contract.functions.getReserves().call)
            token0_address = await asyncio.to_thread(pair_contract.functions.token0().call)

            wbnb_reserve_wei = reserves[0] if token0_address.lower() == WBNB_ADDRESS.lower() else reserves[1]
            wbnb_reserve = self.web3.from_wei(wbnb_reserve_wei, 'ether')

            print(f"   [فحص سريع] السيولة المكتشفة: {wbnb_reserve:.2f} BNB")
            if wbnb_reserve >= MINIMUM_LIQUIDITY_BNB:
                print(f"   [فحص سريع] ✅ نجح. السيولة كافية.")
                return True
            else:
                print(f"   [فحص سريع] 🔻 فشل. السيولة أقل من الحد المطلوب.")
                return False
        except Exception as e:
            print(f"   [فحص سريع] ⚠️ خطأ أثناء فحص السيولة: {e}")
            return False

    async def محاكاة_عملية_بيع(self, token_address: str) -> bool:
        print(f"   [محاكاة البيع] التحقق من إمكانية بيع {token_address}")
        try:
            token_contract = self.web3.eth.contract(address=token_address, abi=ERC20_ABI)
            token_balance = await asyncio.to_thread(token_contract.functions.balanceOf(WALLET_ADDRESS).call)
            
            # نستخدم رصيد وهمي صغير للمحاكاة إذا كان رصيدنا الحقيقي صفراً
            amount_to_simulate = 1000 if token_balance == 0 else int(token_balance * 0.1)

            await asyncio.to_thread(
                self.router_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                    amount_to_simulate, 0, [token_address, WBNB_ADDRESS], WALLET_ADDRESS, int(time.time()) + 120
                ).call, {'from': WALLET_ADDRESS}
            )
            print("   [محاكاة البيع] ✅ نجحت المحاكاة. العملة قابلة للبيع.")
            return True
        except Exception:
            print(f"   [محاكاة البيع] 🚨🚨🚨 فشلت المحاكاة! على الأغلب Honeypot.")
            return False

    async def فحص_شامل(self, pair_address: str, token_address: str) -> bool:
        if not await self.فحص_أولي_سريع(pair_address):
            return False
        
        if not await self.محاكاة_عملية_بيع(token_address):
            return False
        
        return True

class القناص:
    def __init__(self, web3: Web3, nonce_manager: مدير_الـNonce):
        self.web3 = web3
        self.nonce_manager = nonce_manager
        self.router_contract = self.web3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
        print("✅ القناص جاهز (مع غاز ديناميكي).")

    async def _get_dynamic_gas(self) -> int:
        base_price = await asyncio.to_thread(self.web3.eth.gas_price)
        tip = self.web3.to_wei(GAS_PRICE_TIP_GWEI, 'gwei')
        return base_price + tip

    async def تنفيذ_الشراء(self, token_address: str) -> Dict[str, Any]:
        try:
            print(f"🚀🚀🚀 بدء عملية قنص وشراء العملة: {token_address} 🚀🚀🚀")
            bnb_amount_wei = self.web3.to_wei(BUY_AMOUNT_BNB, 'ether')
            path = [WBNB_ADDRESS, token_address]
            
            amounts_out = await asyncio.to_thread(self.router_contract.functions.getAmountsOut(bnb_amount_wei, path).call)
            min_tokens = int(amounts_out[1] * (1 - (SLIPPAGE_LIMIT / 100)))

            tx = self.router_contract.functions.swapExactETHForTokens(
                min_tokens, path, WALLET_ADDRESS, int(time.time()) + 120
            ).build_transaction({
                'from': WALLET_ADDRESS, 'value': bnb_amount_wei,
                'gas': GAS_LIMIT, 'gasPrice': await self._get_dynamic_gas(),
                'nonce': await self.nonce_manager.get_next(),
            })

            signed_tx = self.web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            tx_hash = await asyncio.to_thread(self.web3.eth.send_raw_transaction, signed_tx.rawTransaction)
            print(f"   هاش معاملة الشراء: {tx_hash.hex()}")
            
            receipt = await asyncio.to_thread(self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=180)

            if receipt.status == 1:
                print(f"💰 نجحت عملية الشراء! تم قنص {token_address}.")
                token_contract = self.web3.eth.contract(address=token_address, abi=ERC20_ABI)
                decimals = await asyncio.to_thread(token_contract.functions.decimals().call)
                
                amount_bought = amounts_out[1]
                buy_price = BUY_AMOUNT_BNB / (amount_bought / (10**decimals))

                return {
                    "success": True, "token_address": token_address,
                    "buy_price": buy_price, "amount_bought_wei": amount_bought,
                    "decimals": decimals,
                }
            else:
                print(f"🚨 فشلت معاملة الشراء.")
                return {"success": False}
        except Exception as e:
            print(f"❌ خطأ في تنفيذ الشراء: {e}")
            return {"success": False}

class الحارس:
    def __init__(self, web3: Web3, nonce_manager: مدير_الـNonce):
        self.web3 = web3
        self.nonce_manager = nonce_manager
        self.router_contract = self.web3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
        self.active_trades: List[Dict] = []
        print("✅ الحارس المحصّن مستيقظ ويراقب...")

    def add_trade(self, trade_details: Dict):
        trade = {
            "token_address": trade_details["token_address"],
            "buy_price": trade_details["buy_price"],
            "initial_amount_wei": trade_details["amount_bought_wei"],
            "remaining_amount_wei": trade_details["amount_bought_wei"],
            "decimals": trade_details["decimals"],
            "tp1_triggered": False, "tp2_triggered": False
        }
        self.active_trades.append(trade)
        print(f"🛡️ [الحارس] بدأ مراقبة العملة: {trade['token_address']}")

    async def _get_dynamic_gas(self) -> int:
        base_price = await asyncio.to_thread(self.web3.eth.gas_price)
        tip = self.web3.to_wei(GAS_PRICE_TIP_GWEI, 'gwei')
        return base_price + tip

    async def _get_current_price(self, trade: Dict) -> float:
        try:
            one_token = 1 * (10**trade["decimals"])
            amounts_out = await asyncio.to_thread(
                self.router_contract.functions.getAmountsOut(one_token, [trade["token_address"], WBNB_ADDRESS]).call
            )
            return self.web3.from_wei(amounts_out[1], 'ether')
        except Exception:
            return 0.0

    async def _execute_sell(self, trade: Dict, amount_to_sell_wei: int) -> bool:
        token_address = trade['token_address']
        print(f"\n💸 [الحارس] بدء عملية البيع لـ {token_address}...")
        try:
            token_contract = self.web3.eth.contract(address=token_address, abi=ERC20_ABI)
            gas_price = await self._get_dynamic_gas()
            
            approve_tx = token_contract.functions.approve(ROUTER_ADDRESS, amount_to_sell_wei).build_transaction({
                'from': WALLET_ADDRESS, 'gasPrice': gas_price, 'gas': 100000,
                'nonce': await self.nonce_manager.get_next()
            })
            signed_approve = self.web3.eth.account.sign_transaction(approve_tx, PRIVATE_KEY)
            approve_hash = await asyncio.to_thread(self.web3.eth.send_raw_transaction, signed_approve.rawTransaction)
            print(f"   - هاش الموافقة: {approve_hash.hex()}")
            await asyncio.to_thread(self.web3.eth.wait_for_transaction_receipt, approve_hash, timeout=180)
            print("   - ✅ نجحت الموافقة.")

            swap_tx = self.router_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                amount_to_sell_wei, 0, [token_address, WBNB_ADDRESS],
                WALLET_ADDRESS, int(time.time()) + 300
            ).build_transaction({
                'from': WALLET_ADDRESS, 'gas': GAS_LIMIT, 'gasPrice': gas_price,
                'nonce': await self.nonce_manager.get_next()
            })
            signed_swap = self.web3.eth.account.sign_transaction(swap_tx, PRIVATE_KEY)
            swap_hash = await asyncio.to_thread(self.web3.eth.send_raw_transaction, signed_swap.rawTransaction)
            print(f"   - هاش البيع: {swap_hash.hex()}")
            await asyncio.to_thread(self.web3.eth.wait_for_transaction_receipt, swap_hash, timeout=180)
            
            print(f"   - 💰💰💰 نجحت عملية البيع لـ {token_address}!")
            return True
        except Exception as e:
            print(f"   - ❌ خطأ فادح في عملية البيع: {e}")
            return False

    async def monitor_trades(self):
        while True:
            if not self.active_trades:
                await asyncio.sleep(2); continue

            price_tasks = [self._get_current_price(trade) for trade in self.active_trades]
            current_prices = await asyncio.gather(*price_tasks, return_exceptions=True)

            for i, trade in enumerate(list(self.active_trades)):
                price = current_prices[i]
                if isinstance(price, Exception) or price == 0: continue

                profit = ((price - trade["buy_price"]) / trade["buy_price"]) * 100
                print(f"   [مراقبة] {trade['token_address'][:10]}.. | الربح: {profit:.2f}%")

                if not trade["tp1_triggered"] and profit >= TAKE_PROFIT_THRESHOLD_1:
                    trade["tp1_triggered"] = True
                    amount = int(trade['initial_amount_wei'] * (SELL_PERCENTAGE_1 / 100))
                    if await self._execute_sell(trade, amount):
                        trade['remaining_amount_wei'] -= amount

                if not trade["tp2_triggered"] and profit >= TAKE_PROFIT_THRESHOLD_2:
                    trade["tp2_triggered"] = True
                    if await self._execute_sell(trade, trade['remaining_amount_wei']):
                        self.active_trades.remove(trade)

                if profit <= STOP_LOSS_THRESHOLD:
                    print(f"🚨 [الحارس] تفعيل وقف الخسارة لـ {trade['token_address']}")
                    if await self._execute_sell(trade, trade['remaining_amount_wei']):
                        self.active_trades.remove(trade)
            
            await asyncio.sleep(5)

# =================================================================
# 5. البرنامج الرئيسي ونقطة الانطلاق
# =================================================================

async def process_new_token(pair_address, token_address, verifier, sniper, guardian):
    print(f"\n[مهمة جديدة] بدأت معالجة العملة: {token_address}")
    if await verifier.فحص_شامل(pair_address, token_address):
        trade_result = await sniper.تنفيذ_الشراء(token_address)
        if trade_result.get("success"):
            guardian.add_trade(trade_result)
    else:
        print(f"🔻 [مهمة منتهية] تم تجاهل العملة {token_address} (لم تجتز الفحص).")

async def main():
    print("--- بدأ تشغيل بوت صياد الدرر (النسخة النهائية المحصّنة v2.0) ---")
    
    web3 = Web3(Web3.WebsocketProvider(NODE_URL_WS, websocket_timeout=60))
    if not await web3.is_connected():
        print("❌ لا يمكن الاتصال بالشبكة. يتم الخروج."); return

    nonce_manager = مدير_الـNonce(web3, WALLET_ADDRESS)
    await nonce_manager.initialize()

    watcher = الراصد(web3)
    verifier = المدقق(web3)
    sniper = القناص(web3, nonce_manager)
    guardian = الحارس(web3, nonce_manager)

    async def new_pool_handler(pair, token):
        asyncio.create_task(process_new_token(pair, token, verifier, sniper, guardian))

    print("🛡️  البوت المحصّن جاهز على خط الانطلاق...")
    guardian_task = asyncio.create_task(guardian.monitor_trades())
    watcher_task = asyncio.create_task(watcher.استمع_للمجمعات_الجديدة(new_pool_handler))
    
    await asyncio.gather(guardian_task, watcher_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n--- تم إيقاف البوت يدويًا ---")
    except Exception as main_exc:
        print(f"❌ خطأ فادح في البرنامج الرئيسي: {main_exc}")