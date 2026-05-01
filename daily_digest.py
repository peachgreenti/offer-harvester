"""
OFFER收割机 × 飞书 CLI — 第四轮（下）：每日求职简报
daily_digest.py — 汇总各表数据，生成求职进度摘要并推送
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def dashboard_summary(lark_client, ai_client) -> str:
    """
    处理 /进度 指令
    1. 查询各表记录数和状态统计
    2. 查询今日面试安排
    3. AI 生成进度摘要
    4. 返回求职进度报告
    """
    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    stats = {}
    today = datetime.now().strftime("%Y-%m-%d")

    # 统计各表数据
    table_stats = {
        "job_analysis": ("岗位分析", TABLE_IDS["job_analysis"]),
        "resume": ("简历", TABLE_IDS["resume"]),
        "resume_opt": ("简历优化", TABLE_IDS["resume_opt"]),
        "company_bg": ("公司背调", TABLE_IDS["company_bg"]),
        "interview": ("面试记录", TABLE_IDS["interview"]),
        "offer": ("OFFER", TABLE_IDS["offer"]),
    }

    for key, (name, table_id) in table_stats.items():
        result = lark_client.list_records(table_id=table_id, limit=1)
        if result.get("ok"):
            stats[name] = result.get("total", 0)
        else:
            stats[name] = "?"
            logger.warning(f"查询 {name} 失败: {result.get('error', '')}")

    # 获取最新面试信息
    interview_result = lark_client.list_records(table_id=TABLE_IDS["interview"], limit=5)
    recent_interviews = []
    if interview_result.get("ok"):
        items = interview_result.get("items", [])
        for item in items[:5]:
            job_title = item.get("岗位", "") or item.get("岗位名称", "")
            company = item.get("公司名称", "")
            if job_title or company:
                recent_interviews.append(f"{job_title} @ {company}")

    # 获取最新 OFFER 信息
    offer_result = lark_client.list_records(table_id=TABLE_IDS["offer"], limit=5)
    recent_offers = []
    if offer_result.get("ok"):
        items = offer_result.get("items", [])
        for item in items[:5]:
            company = _get_field_text(item, "公司名称")
            job_title = _get_field_text(item, "岗位名称")
            if company or job_title:
                name = f"{company}-{job_title}" if company and job_title else (company or job_title)
                recent_offers.append(name)

    # AI 生成摘要
    logger.info("AI 生成求职进度摘要...")
    digest_data = {
        "date": today,
        "stats": stats,
        "recent_interviews": recent_interviews,
        "recent_offers": recent_offers,
    }

    try:
        ai_summary = ai_client.generate_dashboard_summary(digest_data)
    except Exception as e:
        logger.error(f"AI 生成摘要失败: {e}")
        ai_summary = ""

    # 手动构建摘要（兜底）
    response = f"""📈 **求职进度报告（{today}）**

📊 **数据总览**:
  📋 已分析岗位：{stats.get('岗位分析', 0)} 个
  📄 已保存简历：{stats.get('简历', 0)} 份
  🎯 已优化简历：{stats.get('简历优化', 0)} 份
  🔍 已背调公司：{stats.get('公司背调', 0)} 家
  🎤 面试记录：{stats.get('面试记录', 0)} 条
  📬 OFFER：{stats.get('OFFER', 0)} 个"""

    if recent_interviews:
        response += "\n\n🎤 **最近面试**:"
        for i, iv in enumerate(recent_interviews[:3]):
            response += f"\n  {i+1}. {iv}"

    if recent_offers:
        response += "\n\n📬 **最近 OFFER**:"
        for i, of in enumerate(recent_offers[:3]):
            response += f"\n  {i+1}. {of}"

    if ai_summary:
        response += f"\n\n💡 **AI 建议**:\n{ai_summary}"

    response += "\n\n📝 数据来源：OFFER收割机多维表格"

    return response


def _get_field_text(fields: dict, field_name: str) -> str:
    """从字段字典中提取文本值（兼容扁平格式和旧嵌套格式）"""
    val = fields.get(field_name, "")
    if isinstance(val, list) and val and isinstance(val[0], dict):
        return val[0].get("text", str(val[0]))
    return str(val) if val else ""
