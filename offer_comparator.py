"""
OFFER收割机 × 飞书 CLI — 第三轮（下）：OFFER 对比分析
offer_comparator.py — 读取 OFFER 数据，AI 五维对比分析，生成文档
"""
import json
import logging

logger = logging.getLogger(__name__)


def compare_offers(lark_client, ai_client) -> str:
    """
    处理 /offer 指令
    1. 读取 08OFFER参考军师 所有 OFFER 记录
    2. 读取 06公司背调侦探 背调数据
    3. AI 五维对比分析
    4. 生成飞书文档
    5. 返回对比摘要
    """
    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    # 读取所有 OFFER 记录
    offer_result = lark_client.list_records(table_id=TABLE_IDS["offer"], limit=20)
    if not offer_result.get("ok"):
        return f"⚠️ 读取 OFFER 数据失败：{offer_result.get('error', '')}"

    offer_items = offer_result.get("items", [])

    if not offer_items:
        return """❓ OFFER 列表为空，请先在「08OFFER参考军师」中添加 OFFER 记录。

提示：在多维表格中添加 OFFER 信息后，再发送 `/offer` 查看对比分析。"""

    # 提取 OFFER 信息（兼容扁平格式和旧嵌套格式）
    offers = []
    for item in offer_items:
        offer = {}
        for key, val in item.items():
            if key == "record_id":
                continue
            if isinstance(val, list) and val and isinstance(val[0], dict):
                offer[key] = val[0].get("text", str(val[0]))
            elif isinstance(val, str):
                offer[key] = val
        offers.append(offer)

    if len(offers) < 2:
        return "❓ 至少需要 2 个 OFFER 才能进行对比分析。请在「08OFFER参考军师」中添加更多 OFFER。"

    # AI 对比分析
    logger.info(f"AI OFFER 对比分析中... ({len(offers)} 个 OFFER)")
    try:
        comparison = ai_client.compare_offers(offers)
    except Exception as e:
        logger.error(f"AI 对比分析失败: {e}")
        return f"⚠️ OFFER 对比分析失败：{str(e)}"

    # 生成飞书文档
    doc_title = "OFFER 对比分析报告"
    doc_md = _generate_comparison_doc(comparison)

    doc_result = lark_client.create_doc(title=doc_title, markdown=doc_md)
    doc_url = ""
    if doc_result.get("ok"):
        doc_data = doc_result.get("data", {})
        doc_url = doc_data.get("doc_url", "")
        logger.info(f"✅ 对比文档已创建: {doc_url}")

    # 生成回复
    comp_list = comparison.get("comparison", [])
    ranked = comparison.get("ranked", [])
    recommendation = comparison.get("recommendation", "")

    # 构建对比表格
    if comp_list:
        header = "| 维度 | " + " | ".join(c.get("company", "?")[:8] for c in comp_list) + " |"
        separator = "|:---| " + " | ".join(":---:" for _ in comp_list) + " |"

        dimensions = [
            ("薪资待遇", "salary_score"),
            ("岗位发展", "career_score"),
            ("企业发展", "company_score"),
            ("行业发展", "industry_score"),
            ("工作内容", "work_score"),
            ("总分", "total"),
        ]

        table_lines = [header, separator]
        for dim_name, dim_key in dimensions:
            row = f"| {dim_name} | " + " | ".join(
                str(c.get(dim_key, "-")) for c in comp_list
            ) + " |"
            table_lines.append(row)

        table_text = "\n".join(table_lines)
    else:
        table_text = "（对比数据生成失败）"

    ranked_text = "\n".join(
        f"  🥇 {r}" if i == 0 else f"  🥈 {r}" if i == 1 else f"  🥉 {r}" if i == 2 else f"  {i+1}. {r}"
        for i, r in enumerate(ranked[:5])
    )

    doc_link = f"\n📄 [查看完整报告]({doc_url})" if doc_url else ""

    response = f"""📊 **OFFER 对比分析报告**
━━━━━━━━━━━━━━━━━━━━━━━━

{table_text}

🏆 **推荐排序**:
{ranked_text}

💡 **综合推荐**:
{recommendation}
{doc_link}

📝 详细报告已同步到「08OFFER参考军师」"""

    return response


def _generate_comparison_doc(comparison: dict) -> str:
    """生成 OFFER 对比飞书文档 Markdown"""
    comp_list = comparison.get("comparison", [])
    recommendation = comparison.get("recommendation", "")
    ranked = comparison.get("ranked", [])

    lines = [
        "# OFFER 对比分析报告",
        "",
        "## 综合推荐",
        "",
        recommendation,
        "",
        "## 推荐排序",
        "",
    ]
    for i, r in enumerate(ranked):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {r}")

    lines.extend(["", "## 详细对比", ""])

    if comp_list:
        # 表格
        lines.append("| 维度 | " + " | ".join(c.get("company", "?") for c in comp_list) + " |")
        lines.append("|:---| " + " | ".join(":---:" for _ in comp_list) + " |")

        dimensions = [
            ("薪资待遇", "salary_score"),
            ("岗位发展", "career_score"),
            ("企业发展", "company_score"),
            ("行业发展", "industry_score"),
            ("工作内容", "work_score"),
            ("总分", "total"),
        ]
        for dim_name, dim_key in dimensions:
            lines.append(f"| {dim_name} | " + " | ".join(
                str(c.get(dim_key, "-")) for c in comp_list
            ) + " |")

        lines.append("")
        for c in comp_list:
            company = c.get("company", "未知公司")
            lines.extend([
                f"### {company}",
                "",
                f"**岗位**: {c.get('position', '未知')}",
                "",
            ])
            pros = c.get("pros", [])
            if pros:
                lines.append("**优势**:")
                for p in pros:
                    lines.append(f"- ✅ {p}")
                lines.append("")

            cons = c.get("cons", [])
            if cons:
                lines.append("**劣势**:")
                for c_item in cons:
                    lines.append(f"- ⚠️ {c_item}")
                lines.append("")

            risk = c.get("risk_notes", "")
            if risk:
                lines.append(f"**风险提示**: {risk}")
                lines.append("")

    return "\n".join(lines)
