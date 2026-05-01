"""
OFFER收割机 × 飞书 CLI — 简历匹配 + 公司背调 + 简历生成
resume_matcher.py — 写入表格，等待自动化完成，读取结果回复
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


def _find_resume_record(lark_client, table_id: str, doc_url: str) -> dict:
    """
    在02简历库中查找是否已存在该云文档链接的记录
    返回: {"found": True, "record_id": "xxx", "record": {...}} 或 {"found": False}
    """
    result = lark_client.list_records(table_id=table_id, limit=50)
    if not result.get("ok"):
        return {"found": False}

    for item in result.get("items", []):
        # 检查简历云文档字段
        cloud_doc = _get_text(item, "简历云文档")
        if cloud_doc and doc_url in cloud_doc:
            return {"found": True, "record_id": item.get("record_id", ""), "record": item}

        # 也检查简历内容读取字段中是否包含该链接
        content = _get_text(item, "简历内容读取")
        if content and doc_url in content:
            return {"found": True, "record_id": item.get("record_id", ""), "record": item}

    return {"found": False}


def match_resume(params: str, lark_client, ai_client) -> str:
    """
    处理 /匹配 指令
    1. 从飞书云文档链接读取简历内容
    2. 检查02表是否已存在该简历（通过云文档链接匹配）
       - 已存在：找到对应记录，不重复创建
       - 不存在：在02表创建新记录
    3. 不在04表创建记录（03表的工作流会自动在04表创建）
    4. 轮询04表，等待匹配度/简历优化建议被填充
    5. 读取结果回复
    """
    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    if not params:
        return "❓ 请提供简历的飞书云文档链接。\n\n用法：`匹配 <飞书云文档链接>`"

    # 提取飞书文档链接
    doc_url = params.strip()
    feishu_pattern = r'https?://[^\s<>"{}|\\^`\[\]]*feishu\.cn/[^\s<>"{}|\\^`\[\]]*'
    match = re.search(feishu_pattern, doc_url)
    if match:
        doc_url = match.group(0)
    elif not doc_url.startswith("http"):
        return "❓ 请提供有效的飞书云文档链接。\n\n用法：`匹配 <飞书云文档链接>`"

    # 读取飞书文档内容
    logger.info(f"读取飞书文档: {doc_url}")
    doc_result = lark_client.fetch_doc(doc_url)
    if not doc_result.get("ok"):
        return f"⚠️ 读取文档失败：{doc_result.get('error', '请确认链接是有效的飞书云文档')}"

    doc_data = doc_result.get("data", {})
    resume_text = doc_data.get("markdown", "") or doc_data.get("content", "")
    if not resume_text:
        return "⚠️ 文档内容为空，请确认文档中有简历内容。"

    logger.info(f"简历内容长度: {len(resume_text)} 字符")

    # 检查02表是否已存在该简历
    existing = _find_resume_record(lark_client, TABLE_IDS["resume"], doc_url)

    if existing.get("found"):
        logger.info(f"02表已存在该简历: {existing['record_id']}")
    else:
        # 在02表创建新记录
        create_result = lark_client.create_records(
            table_id=TABLE_IDS["resume"],
            fields=["简历内容读取", "简历云文档"],
            rows=[[resume_text[:5000], doc_url]],
        )
        if create_result.get("ok"):
            record_ids = create_result.get("data", {}).get("record_id_list", [])
            logger.info(f"✅ 简历已写入简历库: {record_ids[0] if record_ids else ''}")
        else:
            logger.warning(f"写入简历库失败: {create_result.get('error')}")

    # 不在04表创建记录，等待03表的工作流自动在04表创建
    # 轮询04表最新记录，等待匹配度被填充
    logger.info("等待表格自动化匹配分析...")

    # 先获取04表当前最新记录作为基准
    before_result = lark_client.list_records(table_id=TABLE_IDS["resume_opt"], limit=1)
    before_items = before_result.get("items", [])
    before_id = before_items[0].get("record_id", "") if before_items else ""

    # 轮询等待新记录出现且匹配度被填充
    import time as _time
    max_wait = 300
    poll_interval = 10
    waited = 0
    target_record = None

    while waited < max_wait:
        _time.sleep(poll_interval)
        waited += poll_interval

        list_result = lark_client.list_records(table_id=TABLE_IDS["resume_opt"], limit=5)
        if not list_result.get("ok"):
            continue

        for item in list_result.get("items", []):
            rid = item.get("record_id", "")
            # 跳过轮询开始前就存在的记录
            if rid == before_id:
                continue

            score = _get_text(item, "匹配度")
            if score:
                target_record = item
                break

        if target_record:
            break

        if waited % 30 == 0:
            logger.info(f"轮询中... 已等待 {waited}s")

    if not target_record:
        return f"⏳ 简历已写入简历库\n\n⚠️ 等待表格自动化匹配分析超时（{max_wait // 60} 分钟）\n请检查多维表格中04表是否有新的匹配记录。"

    # 读取完整记录
    record_id = target_record.get("record_id", "")
    full_result = lark_client.get_record(table_id=TABLE_IDS["resume_opt"], record_id=record_id)
    if full_result.get("ok"):
        record = full_result.get("data", {}).get("record", {})
    else:
        record = target_record

    return _format_match_result(record)


def _format_match_result(record: dict) -> str:
    """格式化匹配结果"""
    job_name = _get_text(record, "岗位名称")
    company = _get_text(record, "公司名称")
    score = _get_text(record, "匹配度")
    suggestions = _get_text(record, "简历修改建议（该岗位）")
    readability = _get_text(record, "可读性建议")
    keyword_analysis = _get_text(record, "关键词分布分析")

    # 匹配度 emoji
    score_num = 0
    try:
        score_num = int(re.search(r'(\d+)', score).group(1)) if score else 0
    except (AttributeError, ValueError):
        pass
    score_emoji = "🟢" if score_num >= 80 else "🟡" if score_num >= 60 else "🔴"

    # 截断过长的内容
    if len(suggestions) > 500:
        suggestions = suggestions[:500] + "..."
    if len(readability) > 300:
        readability = readability[:300] + "..."
    if len(keyword_analysis) > 300:
        keyword_analysis = keyword_analysis[:300] + "..."

    keyword_line = f"\n📊 **关键词分布**: {keyword_analysis}" if keyword_analysis else ""

    return f"""📊 **简历匹配报告**
━━━━━━━━━━━━━━━━━━
{score_emoji} **匹配度: {score}**
━━━━━━━━━━━━━━━━━━

📋 **岗位**: {job_name} @ {company}

📝 **修改建议**:
{suggestions}

📖 **可读性建议**:
{readability}
{keyword_line}

📝 详细信息已同步到「04简历优化大师」

---
💡 接下来你可以：
- 发送 `简历` 一键生成优化简历
- 发送 `背调 <公司名>` 了解公司背景"""


def generate_resume(lark_client, ai_client, source_msg_id: str = "") -> str:
    """
    处理 /简历 指令
    1. 找到04表最新的匹配记录
    2. 如果已有云文档链接，直接展示
    3. 如果没有，提示用户去表格点击「一键生成简历」按钮，然后轮询等待
    4. 检测到链接后自动回复
    """
    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    import time as _time

    # 获取04表最新记录
    result = lark_client.list_records(table_id=TABLE_IDS["resume_opt"], limit=1)
    if not result.get("ok"):
        return f"⚠️ 读取简历优化表失败：{result.get('error', '')}"

    items = result.get("items", [])
    if not items:
        return "❓ 尚无匹配记录，请先执行 `匹配 <简历云文档链接>`。"

    latest = items[0]
    record_id = latest.get("record_id", "")

    # 读完整记录
    full_result = lark_client.get_record(table_id=TABLE_IDS["resume_opt"], record_id=record_id)
    if full_result.get("ok"):
        record = full_result.get("data", {}).get("record", {})
    else:
        record = latest

    job_name = _get_text(record, "岗位名称")
    company = _get_text(record, "公司名称")
    score = _get_text(record, "匹配度")
    doc_link = _get_text(record, "生成云文档链接")

    # 如果已有云文档链接，直接返回
    if doc_link:
        return f"""📄 **优化简历已生成！**

📋 **岗位**: {job_name} @ {company}
📊 **匹配度**: {score}

📄 [查看优化简历云文档]({doc_link})

📝 已同步到「04简历优化大师」"""

    # 没有链接，需要用户去表格点击按钮
    # 先回复提示消息
    if source_msg_id:
        lark_client.reply_text(source_msg_id,
            "⏳ 请在多维表格「04简历优化大师」中点击该记录的「一键生成简历」按钮。\n"
            "点击后我会自动检测并回复简历链接，请稍候...")

    # 轮询等待「生成云文档链接」被填充
    logger.info(f"等待用户点击「一键生成简历」按钮... record_id={record_id}")

    max_wait = 600  # 最多等10分钟（用户需要手动操作）
    poll_interval = 10
    waited = 0

    while waited < max_wait:
        _time.sleep(poll_interval)
        waited += poll_interval

        poll_result = lark_client.get_record(
            table_id=TABLE_IDS["resume_opt"],
            record_id=record_id,
        )
        if not poll_result.get("ok"):
            continue

        poll_record = poll_result.get("data", {}).get("record", {})
        link = _get_text(poll_record, "生成云文档链接")

        if link:
            logger.info(f"✅ 云文档链接已生成: {link[:80]}")
            # 用回复消息展示结果
            if source_msg_id:
                lark_client.reply_markdown(source_msg_id,
                    f"""📄 **优化简历已生成！**

📋 **岗位**: {job_name} @ {company}
📊 **匹配度**: {score}

📄 [查看优化简历云文档]({link})

📝 已同步到「04简历优化大师」""")
            return ""  # 已经通过 reply 回复了，不需要再返回

        if waited % 60 == 0:
            logger.info(f"轮询中... 已等待 {waited}s")

    # 超时
    return f"⏳ 等待简历生成超时（{max_wait // 60} 分钟），请稍后再发送 `简历` 查看结果。"


def company_check(params: str, lark_client, ai_client) -> str:
    """
    处理 /背调 指令
    1. 在06表创建记录
    2. 等60秒
    3. 读06表分析结果，一次性回复
    """
    import time as _time

    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    if not params:
        return "❓ 请提供公司名称。\n\n用法：`背调 <公司名>`"

    company_name = params.strip()

    create_result = lark_client.create_records(
        table_id=TABLE_IDS["company_bg"],
        fields=["公司名称"],
        rows=[[company_name]],
    )
    if not create_result.get("ok"):
        return f"⚠️ 创建背调记录失败：{create_result.get('error', '')}"

    record_ids = create_result.get("data", {}).get("record_id_list", [])
    record_id = record_ids[0] if record_ids else ""
    if not record_id:
        return "⚠️ 创建背调记录失败"

    logger.info(f"已创建背调记录: {record_id}，等待60秒...")

    # 等60秒让表格自动化完成分析
    _time.sleep(60)

    # 读06表分析结果
    get_result = lark_client.get_record(
        table_id=TABLE_IDS["company_bg"],
        record_id=record_id,
    )
    if not get_result.get("ok"):
        return f"⚠️ 读取背调结果失败：{get_result.get('error', '')}"

    record = get_result.get("data", {}).get("record", {})
    logger.info(f"背调结果读取成功，公司: {_get_text(record, '公司名称')}")

    return _format_company_result(record, record_id, lark_client)


def _format_company_result(record: dict, record_id: str = "", lark_client=None) -> str:
    """格式化背调结果"""
    name = _get_text(record, "公司名称")
    basic_info = _get_text(record, "公司基本信息")
    salary = _get_text(record, "员工待遇")
    prospect = _get_text(record, "发展前景")
    evaluation = _get_text(record, "公司综合评价")
    main_business = _get_text(record, "主营业务与产品")
    risk = _get_text(record, "风险提示")
    interview_advice = _get_text(record, "面试建议")
    apply_advice = _get_text(record, "应聘建议")

    if len(basic_info) > 300:
        basic_info = basic_info[:300] + "..."
    if len(main_business) > 300:
        main_business = main_business[:300] + "..."
    if len(evaluation) > 300:
        evaluation = evaluation[:300] + "..."

    risk_line = f"\n⚠️ **风险提示**: {risk}" if risk else ""

    # 构建记录链接
    record_link = ""
    if record_id and lark_client:
        try:
            from .config import TABLE_IDS
        except ImportError:
            from config import TABLE_IDS
        record_link = f"\n\n🔗 [查看背调详情]({lark_client.base_url}base/{lark_client.base_token}?table={TABLE_IDS['company_bg']}&rowId={record_id})"

    return f"""🔍 **公司背调报告：{name}**

📊 **基本信息**
{basic_info}

🏢 **主营业务**: {main_business}
💰 **员工待遇**: {salary}
📈 **发展前景**: {prospect}
⭐ **综合评价**: {evaluation}
{risk_line}

🎤 **面试建议**: {interview_advice}
💡 **应聘建议**: {apply_advice}
{record_link}
"""
