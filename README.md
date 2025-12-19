# Token Bulk Sender GUI

一个基于Python + Tkinter的ERC20代币批量转账工具，支持多链（Ethereum、Base、Arbitrum等）、代理、自动RPC切换。

## 功能特点
- 从多个钱包批量发送指定比例的代币到目标地址
- 支持代理（适合国内用户）
- 自动从 chains.json 加载RPC节点
- GUI界面，易上手
- 暂停/日志实时显示
- 如果不会使用、使用我压缩好的EXE。无需pyhon,可以直接运行。

## ⚠️ 重要安全警告
- 本工具会直接读取明文私钥！请仅在离线/可信电脑上使用！
- 永远不要将包含真实私钥的 wallets.json 上传或分享！
- 使用前请充分测试（建议先在测试网），所有风险自负！

## 使用方法
1. 安装依赖：`pip install web3 eth-account requests tkinter`
2. 创建 `chains.json`（参考 chains.json.example）
3. 创建 `wallets.json`（格式见 wallets.json.example）
4. 运行：`python token_sender.py`

## 免责声明
作者不承担任何资金损失责任。请谨慎使用。
