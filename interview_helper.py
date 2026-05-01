"""
OFFER收割机 × 飞书 CLI — 求职复盘
interview_helper.py — 汇总时间段内所有记录，生成复盘报告
"""
import re
import logging

logger = logging.getLogger(__name__)


def _get_text(record: dict, field_name: str) -> str:
    """从记录中提取文本值（兼容多种格式）"""
    val = record.get(field_name, "")
    if val is None:
        return ""
    if isinstance(val, list) and val and isinstance(val[0], dict):
        return val[0].get("text", str(val[0]))
    return str(val) if val else ""


def review_summary(params: str, lark_client, ai_client) -> str:
    """
    处理 /复盘 指令
    汇总指定时间段内多维表格的所有记录，生成求职复盘报告

    参数格式：
    - 空：汇总最近 7 天
    - "7天" / "1周"：汇总最近 7 天
    - "30天" / "1月"：汇总最近 30 天
    - "2025-01-01 2025-01-31"：汇总指定日期范围
    """
    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    # 解析时间范围
    days = 7  # 默认7天
    params = params.strip()

    if not params:
        days = 7
    elif params in ("7天", "一周", "1周"):
        days = 7
    elif params in ("30天", "一月", "1月"):
        days = 30
    elif params in ("90天", "三月", "3月", "一季度"):
        days = 90
    else:
        # 尝试解析数字+天
        m = re.search(r'(\d+)\s*天', params)
        if m:
            days = int(m.group(1))
        else:
            return "❓ 时间格式不正确。\n\n用法：`复盘`（默认7天）或 `复盘 30天`"

    logger.info(f"开始汇总最近 {days} 天的求职数据...")

    # 读取各表数据
    job_records = _list_all(lark_client, TABLE_IDS["job_analysis"])
    match_records = _list_all(lark_client, TABLE_IDS["resume_opt"])
    company_records = _list_all(lark_client, TABLE_IDS["company_bg"])

    # 统计
    total_jobs = len(job_records)
    total_matches = len(match_records)
    total_companies = len(company_records)

    # 岗位分析汇总
    job_summary = []
    for item in job_records:
        title = _get_text(item, "岗位名称")
        company = _get_text(item, "公司名称")
        salary = _get_text(item, "薪资待遇")
        status = _get_text(item, "跟踪状态")
        if title:
            status_icon = {"准备简历": "📝", "已投简历": "📨", "笔试邀约": "✍️",
                          "面试邀约": "🎤", "拿下offer": "🎉"}.get(status, "📋")
            job_summary.append(f"  {status_icon} {title} @ {company} | {salary} | {status}")

    # 匹配度汇总
    match_summary = []
    for item in match_records:
        job = _get_text(item, "岗位名称")
        company = _get_text(item, "公司名称")
        score = _get_text(item, "匹配度")
        if job and score:
            try:
                score_num = int(re.search(r'(\d+)', score).group(1))
                emoji = "🟢" if score_num >= 80 else "🟡" if score_num >= 60 else "🔴"
                match_summary.append(f"  {emoji} {job} @ {company} — {score}")
            except (AttributeError, ValueError):
                match_summary.append(f"  ⚪ {job} @ {company} — {score}")

    # 背调汇总
    company_summary = []
    for item in company_records:
        name = _get_text(item, "公司名称")
        evaluation = _get_text(item, "公司综合评价")
        risk = _get_text(item, "风险提示")
        if name:
            risk_flag = " ⚠️" if risk else ""
            company_summary.append(f"  🏢 {name}: {evaluation[:50]}{risk_flag}")

    # 生成飞书云文档
    doc_md = f"# 求职复盘报告（最近 {days} 天）\n\n"
    doc_md += f"## 📊 数据概览\n"
    doc_md += f"- 分析岗位：{total_jobs} 个\n"
    doc_md += f"- 简历匹配：{total_matches} 次\n"
    doc_md += f"- 公司背调：{total_companies} 家\n\n"

    if job_summary:
        doc_md += "## 📋 岗位跟踪\n"
        doc_md += "\n".join(job_summary) + "\n\n"

    if match_summary:
        doc_md += "## 📊 匹配度汇总\n"
        doc_md += "\n".join(match_summary) + "\n\n"

    if company_summary:
        doc_md += "## 🔍 公司背调汇总\n"
        doc_md += "\n".join(company_summary) + "\n\n"

    # 创建飞书文档
    doc_result = lark_client.create_doc(
        title=f"求职复盘报告（最近{days}天）",
        markdown=doc_md,
    )
    doc_url = ""
    if doc_result.get("ok"):
        doc_url = doc_result.get("data", {}).get("doc_url", "")
        logger.info("✅ 复盘报告文档已创建")

    doc_link = f"\n📄 [查看完整复盘报告]({doc_url})" if doc_url else ""

    # 截断展示
    job_display = "\n".join(job_summary[-10:]) if job_summary else "  （暂无）"
    match_display = "\n".join(match_summary[-10:]) if match_summary else "  （暂无）"
    company_display = "\n".join(company_summary[-5:]) if company_summary else "  （暂无）"

    if len(job_summary) > 10:
        job_display += f"\n  ... 共 {len(job_summary)} 条"
    if len(match_summary) > 10:
        match_display += f"\n  ... 共 {len(match_summary)} 条"

    return f"""📊 **求职复盘报告（最近 {days} 天）**

📈 **数据概览**
📋 分析岗位：{total_jobs} 个
🎯 简历匹配：{total_matches} 次
🔍 公司背调：{total_companies} 家

📋 **岗位跟踪**:
{job_display}

📊 **匹配度汇总**:
{match_display}

🔍 **公司背调**:
{company_display}
{doc_link}

📝 复盘报告已生成飞书云文档"""


def _list_all(lark_client, table_id: str, limit: int = 100) -> list:
    """获取表中所有记录"""
    result = lark_client.list_records(table_id=table_id, limit=limit)
    if result.get("ok"):
        return result.get("items", [])
    return []
