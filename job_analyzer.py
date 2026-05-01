"""
OFFER收割机 × 飞书 CLI — 岗位分析
job_analyzer.py — 上传JD截图到03表，等16秒取04表链接，读03表分析结果，一次性回复
"""
import os
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


def analyze_job(params: str, lark_client, ai_client, image_keys: list = None, source_msg_id: str = "") -> str:
    """
    处理 /岗位 指令
    1. 上传截图/文本到03表
    2. 等16秒，取04表最新记录链接
    3. 读03表分析结果
    4. 一次性回复：04表链接 + 岗位分析内容
    """
    import time as _time

    try:
        from .config import TABLE_IDS
    except ImportError:
        from config import TABLE_IDS

    # ===== 流程A：有图片 =====
    if image_keys and source_msg_id:
        logger.info(f"检测到 {len(image_keys)} 张图片，启动截图分析流程...")

        image_key = image_keys[0]
        save_path = os.path.join("/tmp", f"jd_{image_key}.png")
        dl_result = lark_client.download_message_image(source_msg_id, image_key, save_path)
        if not dl_result.get("ok"):
            return f"⚠️ 图片下载失败：{dl_result.get('error', '')}"

        actual_path = dl_result.get("data", {}).get("saved_path", save_path)
        if not os.path.exists(actual_path):
            actual_path = save_path
        logger.info(f"图片已下载: {actual_path}")

        create_result = lark_client.create_records(
            table_id=TABLE_IDS["job_analysis"],
            fields=["岗位名称"],
            rows=[["待分析"]],
        )
        if not create_result.get("ok"):
            return f"⚠️ 创建记录失败：{create_result.get('error', '')}"

        record_ids = create_result.get("data", {}).get("record_id_list", [])
        record_id = record_ids[0] if record_ids else ""
        if not record_id:
            return "⚠️ 创建记录失败"

        logger.info(f"已创建03表记录: {record_id}")

        upload_result = lark_client.upload_attachment(
            table_id=TABLE_IDS["job_analysis"],
            record_id=record_id,
            field_name="JD长截图",
            file_path=actual_path,
            file_name="JD截图.png",
        )
        if not upload_result.get("ok"):
            return f"⚠️ 图片上传失败：{upload_result.get('error', '')}"

        logger.info("✅ 图片已上传")

    # ===== 流程B：纯文本 =====
    elif params and params.strip():
        jd_text = params.strip()

        create_result = lark_client.create_records(
            table_id=TABLE_IDS["job_analysis"],
            fields=["职位描述"],
            rows=[[jd_text[:5000]]],
        )
        if not create_result.get("ok"):
            return f"⚠️ 创建记录失败：{create_result.get('error', '')}"

        record_ids = create_result.get("data", {}).get("record_id_list", [])
        record_id = record_ids[0] if record_ids else ""
        if not record_id:
            return "⚠️ 创建记录失败"

        logger.info(f"已创建03表文本记录: {record_id}")

    else:
        return "❓ 请提供岗位 JD 文本或截图。\n\n用法：发送截图+`岗位`，或 `岗位 <JD文本>`"

    # ===== 等60秒，让工作流创建04表记录 + 03表分析完成 =====
    logger.info("等待工作流处理（60秒）...")
    _time.sleep(60)

    # ===== 取04表最新一条记录 =====
    opt_record_id = ""
    list_result = lark_client.list_records(table_id=TABLE_IDS["resume_opt"], limit=1)
    if list_result.get("ok"):
        items = list_result.get("items", [])
        if items:
            opt_record_id = items[0].get("record_id", "")
            logger.info(f"✅ 找到04表最新记录: {opt_record_id}")
    else:
        logger.warning(f"04表读取失败: {list_result.get('error')}")

    # ===== 读03表分析结果 =====
    job_record = {}
    get_result = lark_client.get_record(
        table_id=TABLE_IDS["job_analysis"],
        record_id=record_id,
    )
    if get_result.get("ok"):
        job_record = get_result.get("data", {}).get("record", {})
        logger.info(f"03表岗位名称: {_get_text(job_record, '岗位名称')}")
    else:
        logger.warning(f"03表读取失败: {get_result.get('error')}")

    # ===== 组装回复 =====
    # 04表链接
    opt_link = ""
    if opt_record_id:
        url = f"https://my.feishu.cn/base/{lark_client.base_token}?table={TABLE_IDS['resume_opt']}&rowId={opt_record_id}"
        opt_link = f"\n\n🔗 [点击进入04表记录页面操作]({url})"

    # 岗位分析内容
    job_title = _get_text(job_record, "岗位名称")
    if job_title and job_title != "待分析":
        # 分析已完成
        company = _get_text(job_record, "公司名称")
        salary = _get_text(job_record, "薪资待遇")
        location = _get_text(job_record, "工作地址")
        education = _get_text(job_record, "学历要求")
        experience = _get_text(job_record, "工作年限")
        core_req = _get_text(job_record, "核心要求")
        hard_skills = _get_text(job_record, "硬技能关键词")
        soft_skills = _get_text(job_record, "软技能关键词")
        mbti = _get_text(job_record, "MBTI性格")

        if len(core_req) > 500:
            core_req = core_req[:500] + "..."
        if len(hard_skills) > 300:
            hard_skills = hard_skills[:300] + "..."
        if len(soft_skills) > 300:
            soft_skills = soft_skills[:300] + "..."

        job_url = f"https://my.feishu.cn/base/{lark_client.base_token}?table={TABLE_IDS['job_analysis']}&rowId={record_id}"

        return f"""🔍 **岗位分析完成！**

📋 **岗位**: {job_title}
🏢 **公司**: {company}
💰 **薪资**: {salary}
📍 **地点**: {location}
🎓 **要求**: {education} | {experience}

💡 **核心要求**:
{core_req}

🎯 **硬技能**: {hard_skills}
🤝 **软技能**: {soft_skills}
🧠 **适合性格**: {mbti}
{opt_link}

🔗 [查看03表详情]({job_url})"""

    # 分析尚未完成，但04表链接已就绪
    return f"""🔍 **岗位分析已启动！**

✅ 已在「03岗位分析助手」创建记录
⏳ 岗位分析仍在进行中，结果稍后会自动更新
{opt_link}"""
