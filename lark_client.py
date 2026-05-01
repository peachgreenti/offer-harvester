"""
OFFER收割机 × 飞书 CLI — 飞书 API 封装层
通过 lark-cli 命令行工具调用飞书 API
"""
import subprocess
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _run_cli(args: list, timeout: int = 60, cwd: str = None) -> dict:
    """执行 lark-cli 命令并返回 JSON 结果"""
    cmd = ["lark-cli"] + args
    logger.debug(f"执行命令: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        if result.returncode != 0:
            logger.error(f"CLI 错误: {result.stderr}")
            return {"ok": False, "error": result.stderr}
        # 解析输出中的 JSON
        output = result.stdout.strip()
        # 跳过 ANSI 色彩码和 banner，提取 JSON 块
        lines = output.split("\n")
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("{"):
                in_json = True
            if in_json:
                json_lines.append(line)  # 保留原始缩进
            if in_json and stripped.endswith("}"):
                # 检查是否是完整的 JSON（简单启发式）
                try:
                    json_str = "\n".join(json_lines)
                    json.loads(json_str)
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass  # 可能是嵌套 JSON，继续收集
        # 兜底：尝试整个输出解析
        if json_lines:
            json_str = "\n".join(json_lines)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        return {"ok": True, "raw": output}
    except subprocess.TimeoutExpired:
        logger.error(f"命令超时: {' '.join(cmd)}")
        return {"ok": False, "error": "命令执行超时"}
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}, 原始输出: {output[:500]}")
        return {"ok": False, "error": f"JSON 解析失败: {e}"}
    except Exception as e:
        logger.error(f"命令执行异常: {e}")
        return {"ok": False, "error": str(e)}


class LarkClient:
    """飞书 CLI 封装客户端"""

    def __init__(self):
        try:
            from .config import BASE_TOKEN, CHAT_ID
        except ImportError:
            from config import BASE_TOKEN, CHAT_ID
        self.base_token = BASE_TOKEN
        self.chat_id = CHAT_ID
        self.base_url = "https://my.feishu.cn/"

    # ==================== 消息相关 ====================

    def list_messages(self, count: int = 10, container_id_type: str = "chat") -> dict:
        """拉取群聊最新消息"""
        return _run_cli([
            "im", "+chat-messages-list",
            "--chat-id", self.chat_id,
            "--page-size", str(count),
            "--sort", "desc",
            "--format", "json",
        ])

    def send_text(self, text: str) -> dict:
        """发送纯文本消息"""
        return _run_cli([
            "im", "+messages-send",
            "--chat-id", self.chat_id,
            "--text", text,
        ])

    def send_markdown(self, markdown: str) -> dict:
        """发送 Markdown 格式消息"""
        return _run_cli([
            "im", "+messages-send",
            "--chat-id", self.chat_id,
            "--markdown", markdown,
        ])

    def reply_text(self, message_id: str, text: str) -> dict:
        """回复消息（纯文本）"""
        return _run_cli([
            "im", "+messages-reply",
            "--message-id", message_id,
            "--text", text,
        ])

    def reply_markdown(self, message_id: str, markdown: str) -> dict:
        """回复消息（Markdown）"""
        return _run_cli([
            "im", "+messages-reply",
            "--message-id", message_id,
            "--markdown", markdown,
        ])

    # ==================== 多维表格相关 ====================

    def create_records(self, table_id: str, fields: list, rows: list) -> dict:
        """批量创建记录"""
        json_data = json.dumps({
            "fields": fields,
            "rows": rows,
        }, ensure_ascii=False)
        return _run_cli([
            "base", "+record-batch-create",
            "--base-token", self.base_token,
            "--table-id", table_id,
            "--json", json_data,
        ], timeout=30)

    def list_records(self, table_id: str, limit: int = 100, offset: int = 0) -> dict:
        """查询表记录，返回统一格式 {ok, total, fields, items}"""
        raw = _run_cli([
            "base", "+record-list",
            "--base-token", self.base_token,
            "--table-id", table_id,
            "--limit", str(limit),
            "--offset", str(offset),
            "--format", "json",
        ])
        if not raw.get("ok"):
            return raw

        # 解析飞书 CLI 返回的二维数组格式
        data = raw.get("data", {})
        inner = data.get("data", [])
        field_names = data.get("fields", [])
        record_ids = data.get("record_id_list", [])

        items = []
        for i, row in enumerate(inner):
            record = {"record_id": record_ids[i] if i < len(record_ids) else ""}
            for j, val in enumerate(row):
                if j < len(field_names):
                    record[field_names[j]] = val
            items.append(record)

        return {
            "ok": True,
            "total": len(items),
            "has_more": data.get("has_more", False),
            "fields": field_names,
            "items": items,
        }

    def get_record(self, table_id: str, record_id: str) -> dict:
        """获取单条记录"""
        return _run_cli([
            "base", "+record-get",
            "--base-token", self.base_token,
            "--table-id", table_id,
            "--record-id", record_id,
        ])

    def update_record(self, table_id: str, record_id: str, fields: list, values: list) -> dict:
        """更新记录（fields 和 values 对应）"""
        rows_json = json.dumps({"fields": fields, "rows": [values]})
        return _run_cli([
            "base", "+record-update",
            "--base-token", self.base_token,
            "--table-id", table_id,
            "--record-id", record_id,
            "--json", rows_json,
        ])

    def poll_record(self, table_id: str, record_id: str,
                    check_field: str, initial_value: str = "",
                    max_wait: int = 180, poll_interval: int = 10) -> dict:
        """
        轮询等待记录中某个字段被自动化填充
        当 check_field 的值不再是 initial_value 时返回完整记录
        超时返回 {"ok": False, "error": "timeout"}
        """
        import time as _time
        waited = 0
        while waited < max_wait:
            _time.sleep(poll_interval)
            waited += poll_interval

            result = self.get_record(table_id, record_id)
            if not result.get("ok"):
                logger.debug(f"轮询读取失败: {result.get('error')}")
                continue

            record = result.get("data", {}).get("record", {})
            if not record:
                continue

            val = record.get(check_field, "")
            if val is None:
                val = ""
            if isinstance(val, list) and val:
                val = val[0].get("text", str(val[0])) if isinstance(val[0], dict) else str(val[0])

            if val and val != initial_value:
                logger.info(f"轮询成功: {check_field} = {val[:50]}")
                return {"ok": True, "record": record, "waited": waited}

            if waited % 30 == 0:
                logger.info(f"轮询中... 已等待 {waited}s")

        logger.warning(f"轮询超时: {max_wait}s")
        return {"ok": False, "error": f"等待自动化分析超时（{max_wait // 60} 分钟）"}

    # ==================== 文档相关 ====================

    def fetch_doc(self, doc_url_or_token: str) -> dict:
        """读取飞书云文档内容（支持 URL 或 token）"""
        return _run_cli([
            "docs", "+fetch",
            "--doc", doc_url_or_token,
            "--format", "json",
        ], timeout=30)

    def create_doc(self, title: str, markdown: str) -> dict:
        """创建飞书文档（Markdown）"""
        return _run_cli([
            "docs", "+create",
            "--title", title,
            "--markdown", markdown,
        ], timeout=30)

    # ==================== 图片/附件相关 ====================

    def download_message_image(self, message_id: str, image_key: str, save_path: str) -> dict:
        """下载消息中的图片"""
        import os
        # lark-cli 要求相对路径
        rel_path = os.path.basename(save_path)
        return _run_cli([
            "im", "+messages-resources-download",
            "--message-id", message_id,
            "--file-key", image_key,
            "--type", "image",
            "--output", rel_path,
        ], timeout=30)

    def upload_attachment(self, table_id: str, record_id: str, field_name: str, file_path: str, file_name: str = "") -> dict:
        """上传附件到多维表格记录"""
        import os
        if not file_name:
            file_name = os.path.basename(file_path)
        # lark-cli 要求相对路径，先切到文件所在目录
        file_dir = os.path.dirname(file_path) or "."
        rel_file = os.path.basename(file_path)
        return _run_cli([
            "base", "+record-upload-attachment",
            "--base-token", self.base_token,
            "--table-id", table_id,
            "--record-id", record_id,
            "--field-id", field_name,
            "--file", rel_file,
            "--name", file_name,
        ], timeout=60, cwd=file_dir)

    # ==================== 妙记相关 ====================

    def get_minutes(self, minutes_token: str) -> dict:
        """获取妙记信息"""
        return _run_cli([
            "minutes", "minutes", "get",
            "--params", json.dumps({"minutes_id": minutes_token}),
        ])
