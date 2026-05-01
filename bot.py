"""
OFFER收割机 × 飞书 CLI — 飞书消息监听与指令路由
bot.py — 监听群聊消息，识别求职指令，路由到对应处理模块
"""
import time
import json
import logging
import re
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 记录已处理的消息 ID，避免重复处理
processed_messages = set()
# 处理锁：同一时间只处理一条指令
processing = False

# Bot 回复消息的特征前缀，用于过滤自身消息
BOT_PREFIXES = ("⏳", "🤖", "📊", "🔍", "📄", "🎤", "📝", "📈", "❓", "⚠️", "💡", "✅", "━")


def parse_command(text: str) -> tuple:
    """
    解析用户消息，提取指令和参数
    支持带斜杠和不带斜杠两种格式
    支持指令在多行文本的任意位置（如截图+文字组合发送）
    返回: (command, params)
    """
    # 去掉图片标记等噪声
    cleaned = re.sub(r'\[Image:[^\]]*\]', '', text).strip()

    # 在清理后的文本中搜索指令
    # 先尝试带斜杠
    for cmd in ["/岗位", "/背调", "/复盘", "/进度", "/帮助"]:
        idx = cleaned.find(cmd)
        if idx >= 0:
            params = cleaned[idx + len(cmd):].strip()
            return cmd, params

    # 再尝试不带斜杠（必须是独立词，避免误匹配）
    for cmd in ["岗位", "背调", "复盘", "进度", "帮助"]:
        # 用正则匹配独立词：行首、或前面是空白/换行
        pattern = rf'(?:^|\n|\s)({re.escape(cmd)})(?:\s|$|\n)'
        match = re.search(pattern, cleaned)
        if match:
            start = match.start(1)
            params = cleaned[start + len(cmd):].strip()
            return f"/{cmd}", params

    return None, text


def show_help() -> str:
    """返回帮助信息"""
    return """🤖 **OFFER收割机 — AI 求职教练**

支持以下指令：

📋 `岗位 <JD文本或截图>` — 分析岗位，自动创建匹配记录
🔍 `背调 <公司名>` — 公司背景调查
📝 `复盘` — 求职复盘报告（默认7天，可加 `30天`）
📈 `进度` — 查看求职进度
❓ `帮助` — 显示此帮助信息

💡 **使用流程**: 岗位 → 在04表操作 → 复盘"""


def _is_bot_message(text: str) -> bool:
    """判断是否是 Bot 自己发送的消息"""
    if not text:
        return True
    stripped = text.lstrip()
    return stripped.startswith(BOT_PREFIXES) or "指令处理" in text


def _extract_text_and_images(item: dict) -> tuple:
    """
    从消息中提取文本内容和图片 key 列表
    兼容 text 类型（纯文本）和 post 类型（富文本/图片+文字）
    返回: (text, [image_keys])
    """
    msg_type = item.get("msg_type", "")
    text = ""
    image_keys = []

    if msg_type == "text":
        content = item.get("content", "")
        if isinstance(content, str):
            text = content

    elif msg_type == "post":
        content = item.get("content", "")
        if isinstance(content, str):
            try:
                post_obj = json.loads(content)
                post_content = post_obj.get("content", [])
                for block in post_content:
                    if isinstance(block, list):
                        for node in block:
                            if isinstance(node, dict):
                                if node.get("tag") == "text":
                                    text += node.get("text", "")
                                elif node.get("tag") == "img" or node.get("tag") == "image":
                                    image_keys.append(node.get("image_key", node.get("file_key", "")))
                    elif isinstance(block, str):
                        text += block
            except (json.JSONDecodeError, TypeError):
                text = content

    # 从文本中提取 [Image: img_xxx] 格式的图片 key（lark-cli 简化格式）
    import re
    img_pattern = r'\[Image:\s*(img_v3_[a-zA-Z0-9_-]+)\]'
    for match in re.finditer(img_pattern, text):
        key = match.group(1)
        if key not in image_keys:
            image_keys.append(key)
    # 清理掉 [Image: xxx] 标记
    text = re.sub(r'\[Image:[^\]]*\]', '', text).strip()

    return text, image_keys


def handle_command(command: str, params: str, lark_client, ai_client, image_keys: list = None, source_msg_id: str = ""):
    """根据指令路由到对应处理模块"""
    try:
        if command == "/帮助":
            return show_help()

        elif command == "/岗位":
            try:
                from .job_analyzer import analyze_job
            except ImportError:
                from job_analyzer import analyze_job
            return analyze_job(params, lark_client, ai_client, image_keys=image_keys, source_msg_id=source_msg_id)

        elif command == "/背调":
            try:
                from .resume_matcher import company_check
            except ImportError:
                from resume_matcher import company_check
            return company_check(params, lark_client, ai_client)

        elif command == "/复盘":
            try:
                from .interview_helper import review_summary
            except ImportError:
                from interview_helper import review_summary
            return review_summary(params, lark_client, ai_client)

        elif command == "/进度":
            try:
                from .daily_digest import dashboard_summary
            except ImportError:
                from daily_digest import dashboard_summary
            return dashboard_summary(lark_client, ai_client)

        else:
            return "❓ 未识别的指令，发送 `帮助` 查看支持的指令列表。"

    except Exception as e:
        logger.error(f"处理指令异常 [{command}]: {e}", exc_info=True)
        return f"⚠️ 处理出错：{str(e)}\n请稍后重试。"


def process_messages(lark_client, ai_client):
    """拉取并处理新消息"""
    global processing
    try:
        from .config import POLL_COUNT
    except ImportError:
        from config import POLL_COUNT

    result = lark_client.list_messages(count=POLL_COUNT)
    if not result.get("ok"):
        logger.warning(f"拉取消息失败: {result.get('error', '未知错误')}")
        return

    data = result.get("data", {})
    items = data.get("messages", []) or data.get("items", [])

    if not items:
        return

    for item in items:
        msg_id = item.get("message_id", "")
        if not msg_id or msg_id in processed_messages:
            continue

        processed_messages.add(msg_id)

        # 提取文本内容和图片（兼容 text 和 post 类型）
        text, image_keys = _extract_text_and_images(item)

        if not text.strip():
            continue

        # 忽略 Bot 自己发送的消息
        if _is_bot_message(text):
            continue

        # 如果正在处理指令，跳过
        if processing:
            logger.info(f"跳过消息（正在处理中）: {text[:50]}")
            continue

        logger.info(f"收到消息 [{msg_id}]: {text[:100]}")

        # 解析指令
        command, params = parse_command(text)
        if command is None:
            continue  # 非指令消息，忽略

        logger.info(f"识别指令: {command}, 参数: {params[:100]}")

        # 加锁
        processing = True

        # 处理指令
        response = handle_command(command, params, lark_client, ai_client,
                                  image_keys=image_keys, source_msg_id=msg_id)

        # 回复结果（直接发群消息，不用 reply 避免堆积在回复线程）
        if response:
            lark_client.send_markdown(response)
        logger.info(f"指令处理完成: {command}")

        # 解锁
        processing = False


def main():
    """主入口：启动消息监听循环"""
    logger.info("=" * 50)
    logger.info("🤖 OFFER收割机 启动中...")
    logger.info("=" * 50)

    try:
        from .lark_client import LarkClient
    except ImportError:
        from lark_client import LarkClient
    try:
        from .ai_client import AIClient
    except ImportError:
        from ai_client import AIClient

    lark_client = LarkClient()
    ai_client = AIClient()

    # 测试连接
    logger.info("测试飞书连接...")
    test = lark_client.list_messages(count=1)
    if test.get("ok"):
        logger.info("✅ 飞书连接成功")
    else:
        logger.error(f"❌ 飞书连接失败: {test.get('error')}")
        sys.exit(1)

    try:
        from .config import CHAT_ID, POLL_INTERVAL
    except ImportError:
        from config import CHAT_ID, POLL_INTERVAL
    logger.info(f"监听群聊: {CHAT_ID}")
    logger.info(f"轮询间隔: {POLL_INTERVAL}秒")
    logger.info("发送 帮助 查看支持的指令")
    logger.info("=" * 50)

    # 启动时拉取最新消息作为水位线
    logger.info("加载水位线...")
    init_result = lark_client.list_messages(count=1)
    if init_result.get("ok"):
        init_data = init_result.get("data", {})
        init_msgs = init_data.get("messages", []) or init_data.get("items", [])
        for msg in init_msgs:
            msg_id = msg.get("message_id", "")
            if msg_id:
                processed_messages.add(msg_id)
        logger.info(f"水位线已设置: {len(processed_messages)} 条")

    # 优雅退出
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        logger.info("正在停止...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 主循环
    consecutive_errors = 0
    while running:
        try:
            process_messages(lark_client, ai_client)
            consecutive_errors = 0  # 成功后重置错误计数
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"消息处理循环异常 ({consecutive_errors}): {e}")
            if consecutive_errors >= 5:
                logger.error("连续 5 次异常，等待 30 秒后重试...")
                time.sleep(30)
                consecutive_errors = 0

        # 限制已处理消息集合大小
        if len(processed_messages) > 1000:
            recent = list(processed_messages)[-500:]
            processed_messages.clear()
            processed_messages.update(recent)

        time.sleep(POLL_INTERVAL)

    logger.info("🤖 OFFER收割机 已停止")


if __name__ == "__main__":
    main()
