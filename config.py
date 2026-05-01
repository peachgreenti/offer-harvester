"""
OFFER收割机 × 飞书 CLI — 配置管理

使用前请将下方 ABC 占位符替换为你自己的真实参数，
或通过环境变量设置（优先读取环境变量）。
"""
import os

# ==================== 飞书多维表格 ====================
BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", "ABC_BASE_TOKEN")

TABLE_IDS = {
    "resume": os.environ.get("TABLE_ID_RESUME", "ABC_TABLE_ID_RESUME"),           # 02简历库
    "job_analysis": os.environ.get("TABLE_ID_JOB_ANALYSIS", "ABC_TABLE_ID_JOB_ANALYSIS"),  # 03岗位分析
    "resume_opt": os.environ.get("TABLE_ID_RESUME_OPT", "ABC_TABLE_ID_RESUME_OPT"),  # 04简历优化
    "company_bg": os.environ.get("TABLE_ID_COMPANY_BG", "ABC_TABLE_ID_COMPANY_BG"),  # 06公司背调
    "interview": os.environ.get("TABLE_ID_INTERVIEW", "ABC_TABLE_ID_INTERVIEW"),     # 07面试辅导
    "offer": os.environ.get("TABLE_ID_OFFER", "ABC_TABLE_ID_OFFER"),                 # 08OFFER参考军师
    "dashboard": os.environ.get("BLOCK_ID_DASHBOARD", "ABC_BLOCK_ID_DASHBOARD"),     # 09求职仪表盘
}

# ==================== 飞书群聊 ====================
CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "ABC_CHAT_ID")

# ==================== 豆包大模型 ====================
ARK_API_KEY = os.environ.get("ARK_API_KEY", "ABC_ARK_API_KEY")
# 豆包 API 端点（火山引擎方舟）
ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.environ.get("ARK_MODEL", "ABC_ARK_MODEL")  # 接入点 ID

# ==================== 轮询配置 ====================
POLL_INTERVAL = 5  # 消息轮询间隔（秒）
POLL_COUNT = 10    # 每次拉取消息数

# ==================== 指令定义 ====================
COMMANDS = {
    "/岗位": "analyze_job",
    "/背调": "company_check",
    "/复盘": "review_summary",
    "/进度": "dashboard_summary",
    "/帮助": "show_help",
}
