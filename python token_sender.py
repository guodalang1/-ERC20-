import os
import time
import json
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from web3 import Web3
from eth_account import Account
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import requests
# 停止标志
stop_flag = False  # 用于暂停任务
# ====================== 公共配置区 ======================
# 注意：以下变量会在 GUI 中动态设置，这里只定义默认值（启动 GUI 时会显示这些默认值）
TOKEN_ADDRESS = "0x1f16e03C1a5908818F47f6EE7bB16690b40D0671"   # 代币合约地址    rayls
CHAIN_ID = ""                                             # ==== 链ID ====
START_ID = ""                                               # 起始序号（包含）
END_ID = ""                                                 # 结束序号（包含）
SEND_PERCENT = 99.99                                         # 发送比例：50=一半，99=全部，10=10%

# ==== 代理配置（中国用户必开）====
USE_PROXY = True
PROXY = "http://127.0.0.1:7890"
proxies = {
    "http":  PROXY,
    "https": PROXY
} if USE_PROXY else None

# ==================== 自动从 chains.json 读取 RPC 节点 ====================
CHAINS_FILE = "chains.json"
if not os.path.exists(CHAINS_FILE):
    raise FileNotFoundError("未找到 chains.json 文件！请在脚本同目录创建它并配置节点")

with open(CHAINS_FILE, 'r', encoding='utf-8') as f:
    chains_config = json.load(f)

def load_rpc_urls(chain_id):
    chain_key = str(chain_id)
    if chain_key not in chains_config:
        raise ValueError(f"chains.json 中未找到 Chain ID: {chain_id} 的配置！请添加")
    return chains_config[chain_key]

# ====================== Web3 初始化函数 ======================
def init_web3(chain_id):
    global w3, RPC_URLS
    RPC_URLS = load_rpc_urls(chain_id)
    print(f"自动加载链配置 → Chain ID {chain_id} 使用 {len(RPC_URLS)} 个公共节点")
    print(f"节点列表: {RPC_URLS}")

    w3 = None
    for rpc_url in RPC_URLS:
        w3 = Web3(Web3.HTTPProvider(
            rpc_url,
            request_kwargs={'proxies': proxies if USE_PROXY else None, 'timeout': 90}
        ))
        if w3.is_connected():
            print(f"成功连接到 RPC 节点: {rpc_url}")
            break
    else:
        chain_names = {
            1: "Ethereum 主网", 8453: "Base", 42161: "Arbitrum", 10: "Optimism",
            137: "Polygon", 56: "BNB Chain", 43114: "Avalanche", 59144: "Linea",
            324: "zkSync Era", 81457: "Blast"
        }
        current_chain = chain_names.get(chain_id, f"链ID {chain_id}")
        raise ConnectionError(f"无法连接到任何 {current_chain} 节点，请检查代理或网络")

    session = requests.Session()
    session.trust_env = False
    if USE_PROXY:
        session.proxies.update(proxies)

    retry = Retry(total=10, backoff_factor=3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return w3

# ====================== 自动链浏览器配置 ======================
EXPLORER_MAP = {
    1:     "https://etherscan.io/tx/",
    8453:  "https://basescan.org/tx/",
    42161: "https://arbiscan.io/tx/",
    421614:"https://sepolia.arbiscan.io/tx/",
    10:    "https://optimistic.etherscan.io/tx/",
    11155420:"https://sepolia-optimism.etherscan.io/tx/",
    137:   "https://polygonscan.com/tx/",
    80002: "https://amoy.polygonscan.com/tx/",
    56:    "https://bscscan.com/tx/",
    97:    "https://testnet.bscscan.com/tx/",
    43114: "https://snowtrace.io/tx/",
    43113: "https://testnet.snowtrace.io/tx/",
    59144: "https://lineascan.build/tx/",
    59141: "https://sepolia.lineascan.build/tx/",
    324:   "https://explorer.zksync.io/tx/",
    300:   "https://sepolia.explorer.zksync.io/tx/",
    81457: "https://blastscan.io/tx/",
    168587773:"https://testnet.blastscan.io/tx/",
}

def get_explorer_url(tx_hash):
    base_url = EXPLORER_MAP.get(CHAIN_ID, "https://etherscan.io/tx/")
    return f"{base_url}{tx_hash}"

# ====================== ERC20 ABI ======================
ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
]

# ====================== 全局变量 ======================
w3 = None
token_contract = None
TOKEN_SYMBOL = "UNKNOWN"
TOKEN_DECIMALS = 18
wallets_data = []
nonce_cache = {}

# ====================== 加载 wallets.json ======================
WALLETS_FILE = "wallets.json"
if not os.path.exists(WALLETS_FILE):
    raise FileNotFoundError(f"未找到 {WALLETS_FILE} 文件！")

with open(WALLETS_FILE, 'r', encoding='utf-8') as f:
    wallets_data = json.load(f)

total_wallets = len(wallets_data)
print(f"wallets.json 加载 {total_wallets} 个配置")

# ====================== 辅助函数 ======================
def get_nonce(wallet):
    if wallet not in nonce_cache:
        nonce_cache[wallet] = w3.eth.get_transaction_count(wallet, 'pending')
    return nonce_cache[wallet]

def increment_nonce(wallet):
    nonce_cache[wallet] = nonce_cache.get(wallet, 0) + 1

def get_raw_tx(signed_tx):
    return signed_tx.raw_transaction.hex() if hasattr(signed_tx, "raw_transaction") else signed_tx.rawTransaction.hex()


# ====================== 加强版代理检测（只重试代理）======================
def check_proxy():
    if not USE_PROXY:
        return True

    print("检测代理...", end="")
    for i in range(5):  # 重试5次
        try:
            resp = requests.get("https://www.google.com", proxies=proxies, timeout=8)
            if resp.status_code == 200:
                print("代理正常")
                return True
        except:
            print(f" ☣ 失败({i + 1}/5)", end="")
            if i < 4:
                print("，8秒后重试...", end="")
                time.sleep(8)
            else:
                print()
    print(" ☣ 代理彻底不可用，跳过此钱包")
    return False

def get_balance(wallet):
    for attempt in range(1, 4):
        try:
            balance_wei = token_contract.functions.balanceOf(wallet).call()
            balance = balance_wei / (10 ** TOKEN_DECIMALS)
            print(f"获取余额成功: {balance:.6f} {TOKEN_SYMBOL}")
            return balance_wei
        except Exception as e:
            print(f"获取余额失败 (尝试 {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(5)
    raise Exception("无法获取余额")

def send_token(wallet, private_key, target_address, amount_wei, max_attempts=5):
    account = Account.from_key(private_key)
    for attempt in range(1, max_attempts + 1):
        try:
            transfer_fn = token_contract.functions.transfer(
                w3.to_checksum_address(target_address),
                amount_wei
            )

            for gas_attempt in range(1, 4):
                try:
                    est_gas = transfer_fn.estimate_gas({'from': wallet})
                    gas_limit = int(est_gas * 1.3)
                    print(f"Gas 估算成功: {gas_limit}")
                    break
                except Exception as e:
                    print(f"Gas 估算失败 (尝试 {gas_attempt}/3): {e}")
                    if gas_attempt < 3:
                        time.sleep(5)
                    else:
                        gas_limit = 100_000
            else:
                gas_limit = 100_000

            if CHAIN_ID == 1:
                max_fee = w3.to_wei(2, 'gwei')
                max_priority = w3.to_wei(0.2, 'gwei')
            else:
                max_fee = w3.to_wei(0.03, 'gwei')
                max_priority = w3.to_wei(0.02, 'gwei')

            nonce = get_nonce(wallet)
            print(f"使用 nonce: {nonce}")

            tx = transfer_fn.build_transaction({
                'chainId': CHAIN_ID,
                'nonce': nonce,
                'gas': gas_limit,
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': max_priority
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(get_raw_tx(signed)).hex()
            print(f"交易已提交: {get_explorer_url(tx_hash)}")
            increment_nonce(wallet)

            print("等待确认（最多 180 秒）...")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt.status == 1:
                print(f" ✅  发送 {TOKEN_SYMBOL} 成功！")
                return True
            else:
                print("交易失败 (status=0)")
                return False

        except Exception as e:
            error_str = str(e).lower()
            if 'nonce too low' in error_str or 'replacement transaction underpriced' in error_str:
                print("Nonce 冲突，等待并刷新...")
                time.sleep(10)
                nonce_cache[wallet] = w3.eth.get_transaction_count(wallet, 'pending')
                continue
            if 'nonce too high' in error_str:
                print("Nonce 过高，回退...")
                nonce_cache[wallet] -= 1
                continue

            print(f"发送失败 (尝试 {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                time.sleep(15)
    return False

def batch_send():
    global token_contract, TOKEN_SYMBOL, TOKEN_DECIMALS
    print(f"=== 开始批量发送 {TOKEN_SYMBOL}（发送 {SEND_PERCENT}%）===\n")
    success = fail = 0
    total_sent_wei = 0

    if START_ID < 1 or END_ID > total_wallets or START_ID > END_ID:
        raise ValueError(f"范围错误！必须 1 ≤ START_ID ≤ END_ID ≤ {total_wallets}")

    print(f"本次处理第 {START_ID} ~ {END_ID} 个钱包（共 {END_ID - START_ID + 1} 个）\n")

    # 初始化合约
    token_contract = w3.eth.contract(address=Web3.to_checksum_address(TOKEN_ADDRESS), abi=ERC20_ABI)
    try:
        TOKEN_SYMBOL = token_contract.functions.symbol().call()
    except:
        TOKEN_SYMBOL = "UNKNOWN"
    try:
        TOKEN_DECIMALS = token_contract.functions.decimals().call()
    except:
        TOKEN_DECIMALS = 18
    print(f"检测到代币: {TOKEN_SYMBOL} (地址: {TOKEN_ADDRESS})")
    print(f"小数位: {TOKEN_DECIMALS}")

    for idx in range(START_ID - 1, END_ID):

        if stop_flag:
            print("任务已暂停，退出...")
            break  # 中断任务执行  # 退出任务

        data = wallets_data[idx]
        seq = idx + 1
        private_key = data.get("private_key")
        target_address = data.get("target_address")
        custom_id = data.get("id")

        if not private_key or not target_address:
            print(f"第 {seq} 个配置缺失，跳过")
            fail += 1
            continue

        try:
            account = Account.from_key(private_key)
            wallet = account.address
            id_str = f"(ID: {custom_id}) " if custom_id else ""
           # print(f"\n--- 第 {seq} 个 {id_str}{wallet} → {target_address} ---")
            print(f"\n\n--- 第 {seq} 个 {id_str}{wallet} → {target_address} ---")
            if not check_proxy():
                print(" ☣　代理不可用")
                fail += 1
                time.sleep(10)  # 彻底不行就歇15秒再试下一个
                continue

            balance_wei = get_balance(wallet)
            balance = balance_wei / (10 ** TOKEN_DECIMALS)

            if balance < 0.1:
                print(f" ☣  余额不足 0.1 {TOKEN_SYMBOL}，跳过")
                fail += 1
                continue

            eth_balance = w3.eth.get_balance(wallet)
            if eth_balance < w3.to_wei(0.00002, 'ether'):
                raise Exception(" ☣　ETH 不足支付 Gas")
            send_ratio = SEND_PERCENT / 100.0
            amount_to_send_wei = int(balance_wei * send_ratio)
            if amount_to_send_wei == 0 and balance_wei > 0:
                amount_to_send_wei = 1

            send_amount = amount_to_send_wei / (10 ** TOKEN_DECIMALS)
            print(f"即将发送: {send_amount:.6f} {TOKEN_SYMBOL} ({SEND_PERCENT}%)")

            if send_token(wallet, private_key, target_address, amount_to_send_wei):
                success += 1
                total_sent_wei += amount_to_send_wei
            else:
                fail += 1

            time.sleep(2)
        except Exception as e:
            print(f"第 {seq} 个出错: {e}")
            fail += 1
        time.sleep(1)

    total_sent = total_sent_wei / (10 ** TOKEN_DECIMALS)
    print(f"\n\n=== 执行完成 ===")
    print(f"成功: {success} 个")
    print(f"失败: {fail} 个")
    print(f"共计发送: {total_sent:,.6f} {TOKEN_SYMBOL}")


import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import sys

class TokenSenderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Token 批量发送工具")
        self.root.geometry("860x720")
        self.root.configure(bg='#1e1e1e')  # 深黑背景

        # 变量
        self.token_addr_var = tk.StringVar(value=TOKEN_ADDRESS if 'TOKEN_ADDRESS' in globals() else "")
        self.chain_id_var = tk.IntVar(value=CHAIN_ID if 'CHAIN_ID' in globals() else 1)
        self.start_id_var = tk.IntVar(value=START_ID if 'START_ID' in globals() else 1)
        self.end_id_var = tk.IntVar(value=END_ID if 'END_ID' in globals() else 100)
        self.send_percent_var = tk.DoubleVar(value=SEND_PERCENT if 'SEND_PERCENT' in globals() else 50.0)

        self.setup_style()
        self.create_widgets()
        # 停止标志
        global stop_flag
        stop_flag = False

    def setup_style(self):
        style = ttk.Style()
        style.theme_use('clam')  # clam 主题更容易自定义

        # 整体暗黑绿风格
        style.configure('.', background='#1e1e1e', foreground='#00ff00', font=('Consolas', 10))
        style.configure('TLabel', background='#1e1e1e', foreground='#00ff00')
        style.configure('TButton', background='#003300', foreground='#00ff00', padding=6)
        style.map('TButton',
                  background=[('active', '#004400'), ('pressed', '#002200')])
        style.configure('TEntry', fieldbackground='#003300', foreground='#00ff00', insertcolor='#00ff00')
        style.configure('Treeview', background='#1e1e1e', fieldbackground='#1e1e1e', foreground='#00ff00')

    def create_widgets(self):
        # 主容器
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 参数输入区
        inputs = [
            ("代币合约地址 :", self.token_addr_var, 65),
            ("链ID :", self.chain_id_var, 20),
            ("起始钱包序号 :", self.start_id_var, 20),
            ("结束钱包序号 :", self.end_id_var, 20),
            ("发送比例 % :", self.send_percent_var, 20),
        ]

        for i, (label_text, var, width) in enumerate(inputs):
            ttk.Label(main_frame, text=label_text).grid(row=i, column=0, sticky=tk.W, pady=10)
            entry = ttk.Entry(main_frame, textvariable=var, width=width)
            entry.grid(row=i, column=1, sticky=(tk.W, tk.E), pady=10, padx=(10, 0))
            main_frame.columnconfigure(1, weight=1)

        # 链ID说明
        chain_id_info = "链ID对应的网络：\n"
        chain_id_info += "\n".join([
            "1: Ethereum 主网",
            "8453: Base",
            "42161: Arbitrum",
            "10: Optimism",
            "137: Polygon",
            "56: BNB Chain",
            "43114: Avalanche",
            "59144: Linea",
            "324: zkSync Era",
            "81457: Blast"
        ])

        # 显示链ID说明
        # ttk.Label(main_frame, text="链ID说明:").grid(row=len(inputs), column=0, sticky=tk.W, pady=5)
        # 第二行：显示链ID的具体说明信息
        # 在 "链ID说明:" 标签的下一行显示 chain_id_info，使用适当的上下间距
        ttk.Label(main_frame, text=chain_id_info, font=("Consolas", 10), wraplength=800).grid(row=len(inputs),
                                                                                              column=0, sticky=tk.W,
                                                                                              pady=(10))

        # 开始按钮
        # 开始按钮
        self.start_btn = ttk.Button(main_frame, text="开始批量发送", command=self.start_sending)
        self.start_btn.grid(row=len(inputs), column=0, columnspan=2, pady=(10, 0))  # 向上移动并减小间距

        # 暂停按钮
        self.stop_btn = ttk.Button(main_frame, text="暂停", command=self.stop_task)
        self.stop_btn.grid(row=len(inputs), column=0, columnspan=2, pady=(120, 5))  # 向上移动并减小间距

        # 日志区
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        ttk.Label(log_frame, text="运行日志:", font=('Consolas', 11, 'bold')).pack(anchor=tk.W)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=25,
            state='disabled',
            bg='#000000',
            fg='white',
           # fg='#00ff41',  # 亮绿
            insertbackground='#00ff41',
            font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def stop_task(self):
        global stop_flag
        stop_flag = True
        self.log("\n【用户已手动暂停任务，等待当前钱包完成或超时后停止】\n")

        # 不要关窗口！只恢复开始按钮，让用户可以重新开始
        self.root.after(500, lambda: self.start_btn.config(state='normal'))

        # 把暂停按钮变成灰色，防止重复点
        self.stop_btn.config(text="已暂停", state='disabled')

    def log(self, message):
        self.log_text.configure(state='normal')
        # 设置颜色标签：黄色
        self.log_text.tag_configure('warning', foreground='yellow')
        self.log_text.tag_configure('success', foreground='#00ff41', font=('Consolas', 10, 'bold'))  # 成功用亮黄+加粗
        # 如果消息中有 "☣" 符号，应用黄色标签
        if "☣" in message:
            message = message.replace("☣", "☣")  # 仅替换"☣"符号
            self.log_text.insert(tk.END, message, 'warning')  # 插入带有颜色的消息
        elif "✅" in message:
            self.log_text.insert(tk.END, message, 'success')  # 成功高亮
        else:
            self.log_text.insert(tk.END, message)  # 普通消息

        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def start_sending(self):
        # 恢复暂停按钮为可用状态
        self.stop_btn.config(text="暂停", state='normal')
        self.start_btn.config(state='disabled')
        self.log_text.delete(1.0, tk.END)

        # 每次重新开始前，重置 stop_flag
        global stop_flag
        stop_flag = False

        threading.Thread(target=self.run_batch_send, daemon=True).start()

    def run_batch_send(self):
        try:
            # 更新全局变量
            global TOKEN_ADDRESS, CHAIN_ID, START_ID, END_ID, SEND_PERCENT, w3
            TOKEN_ADDRESS = self.token_addr_var.get().strip()
            CHAIN_ID = self.chain_id_var.get()
            START_ID = self.start_id_var.get()
            END_ID = self.end_id_var.get()
            SEND_PERCENT = self.send_percent_var.get()   # 转为小数

            # 参数校验
            if not TOKEN_ADDRESS.startswith("0x") or len(TOKEN_ADDRESS) != 42:
                raise ValueError("代币合约地址格式不正确！")
            if START_ID < 1 or END_ID < START_ID or END_ID > total_wallets:
                raise ValueError(f"钱包序号范围错误！必须 1 ≤ START_ID ≤ END_ID ≤ {total_wallets}")

            self.log("参数校验通过，开始执行...")
            self.log(f"代币地址: {TOKEN_ADDRESS}")
            self.log(f"链ID: {CHAIN_ID}")
            self.log(f"钱包范围: {START_ID} ~ {END_ID}")
            self.log(f"发送比例: {SEND_PERCENT * 100}%")
            self.log("=" * 60)

            w3 = init_web3(CHAIN_ID)

            # 重定向输出到日志
            class Logger:
                def __init__(self, gui):
                    self.gui = gui

                def write(self, text):
                    if text := text.rstrip():
                        self.gui.log(text)

                def flush(self): pass

            sys.stdout = sys.stderr = Logger(self)

            batch_send()

            self.log("\n【所有任务执行完毕】")

        except Exception as e:
            self.log(f"\n错误: {e}")
            self.root.after(0, lambda: messagebox.showerror("运行错误", str(e)))
        finally:
            self.root.after(0, lambda: self.start_btn.config(state='normal'))


if __name__ == "__main__":
    root = tk.Tk()
    app = TokenSenderGUI(root)
    root.mainloop()