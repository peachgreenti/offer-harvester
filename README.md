# OFFER收割机 — AI 求职教练 Bot

基于飞书多维表格 + 豆包大模型的智能求职助手，通过飞书群聊指令驱动。

## 功能

| 指令 | 说明 |
|------|------|
| `岗位 <JD截图或文本>` | 上传JD截图到03表分析，自动在04表创建记录 |
| `背调 <公司名>` | 公司背景调查 |
| `复盘 [7天/30天]` | 求职复盘报告 |
| `进度` | 查看求职进度总览 |
| `帮助` | 显示帮助信息 |

## 前置依赖

- [lark-cli](https://github.com/nicepkg/lark-cli) — 飞书命令行工具，已登录授权
- Python 3.10+

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/offer-harvester.git
cd offer-harvester
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的真实参数
```

### 3. 启动 Bot

```bash
python3 bot.py
```

## 项目结构

```
offer_harvester/
├── bot.py              # 主入口：消息轮询 + 指令分发
├── config.py           # 配置管理（环境变量 / ABC占位符）
├── lark_client.py      # 飞书 API 封装
├── ai_client.py        # 豆包大模型封装
├── job_analyzer.py     # /岗位 指令
├── resume_matcher.py   # /背调 指令
├── interview_helper.py # /复盘 指令
├── daily_digest.py     # /进度 指令
├── offer_comparator.py # OFFER对比分析
├── .env.example        # 环境变量模板
└── .gitignore
```

## 配置说明

所有敏感参数通过环境变量设置，也可直接修改 `config.py` 中的 ABC 占位符：

| 参数 | 说明 |
|------|------|
| `FEISHU_BASE_TOKEN` | 飞书多维表格 Base Token |
| `TABLE_ID_*` | 各表的 Table ID |
| `FEISHU_CHAT_ID` | 监听的飞书群聊 ID |
| `ARK_API_KEY` | 豆包大模型 API Key |
| `ARK_MODEL` | 豆包接入点 ID |

## License

MIT
