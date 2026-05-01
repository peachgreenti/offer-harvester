"""
OFFER收割机 × 飞书 CLI — 豆包大模型 AI 客户端
通过火山引擎方舟 API 调用豆包模型
"""
import json
import logging
import re
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)


class AIClient:
    """豆包大模型客户端（兼容 OpenAI API 格式）"""

    def __init__(self):
        try:
            from .config import ARK_API_KEY, ARK_BASE_URL, ARK_MODEL
        except ImportError:
            from config import ARK_API_KEY, ARK_BASE_URL, ARK_MODEL
        self.api_key = ARK_API_KEY
        self.base_url = ARK_BASE_URL
        self.model = ARK_MODEL

    def _request(self, messages: list, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        """发送请求到豆包 API"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                logger.debug(f"AI 响应: {content[:200]}...")
                return content
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.error(f"API 请求失败 [{e.code}]: {error_body}")
            raise RuntimeError(f"豆包 API 错误 [{e.code}]: {error_body}")
        except Exception as e:
            logger.error(f"API 请求异常: {e}")
            raise RuntimeError(f"豆包 API 异常: {e}")

    def chat(self, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
        """单轮对话"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self._request(messages, temperature)

    def chat_json(self, system_prompt: str, user_message: str, temperature: float = 0.3) -> dict:
        """单轮对话，期望返回 JSON 格式"""
        system_prompt = f"{system_prompt}\n\n请务必以纯 JSON 格式返回结果，不要包含任何其他文字说明。"
        raw = self.chat(system_prompt, user_message, temperature)
        # 提取 JSON
        raw = raw.strip()
        # 去掉 markdown 代码块包裹
        if raw.startswith("```"):
            lines = raw.split("\n")
            # 去掉首行 ```json 和末行 ```
            start = 1
            end = len(lines)
            if end > 1 and lines[-1].strip() == "```":
                end -= 1
            raw = "\n".join(lines[start:end])
        # 清理控制字符
        raw = re.sub(r'[\x00-\x1f\x7f]', ' ', raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 最后尝试：从文本中提取第一个完整的 JSON 对象
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise RuntimeError(f"AI 返回的内容无法解析为 JSON: {raw[:200]}")

    # ==================== 业务场景封装 ====================

    def analyze_jd(self, jd_text: str) -> dict:
        """分析岗位 JD，提取结构化信息"""
        system = """你是一位资深 HR 和职业规划专家。请分析以下岗位 JD，提取关键信息并以 JSON 格式返回。
JSON 结构：
{
  "job_title": "岗位名称",
  "company": "公司名称",
  "salary": "薪资范围",
  "experience": "工作年限要求",
  "education": "学历要求",
  "location": "工作地点",
  "core_requirements": "核心要求（3-5条，用分号分隔）",
  "hard_skills": "硬技能关键词（用逗号分隔）",
  "soft_skills": "软技能关键词（用逗号分隔）",
  "daily_work": "日常工作内容描述（3-5条，用分号分隔）",
  "mbti_fit": "适合的 MBTI 性格（如 INTJ, ENFJ 等）",
  "risk_notes": "风险提示或注意事项（如有）"
}"""
        return self.chat_json(system, f"请分析以下岗位 JD：\n\n{jd_text}")

    def match_resume(self, resume_text: str, job_analysis: dict) -> dict:
        """简历与岗位匹配度分析"""
        system = """你是一位简历优化专家。请对比简历内容和岗位要求，给出匹配度分析。
JSON 结构：
{
  "match_score": 75,
  "matched_items": ["匹配项1", "匹配项2"],
  "missing_items": ["缺失项1", "缺失项2"],
  "suggestions": ["修改建议1", "修改建议2"],
  "highlight_projects": ["可重点突出的项目经历"],
  "summary": "总体评价（100字以内）"
}"""
        user_msg = f"""请分析以下简历与岗位的匹配度：

【岗位信息】
岗位：{job_analysis.get('job_title', '未知')}
公司：{job_analysis.get('company', '未知')}
核心要求：{job_analysis.get('core_requirements', '')}
硬技能：{job_analysis.get('hard_skills', '')}
软技能：{job_analysis.get('soft_skills', '')}

【简历内容】
{resume_text[:3000]}"""
        return self.chat_json(system, user_msg)

    def generate_interview_questions(self, job_analysis: dict, count: int = 10) -> dict:
        """生成面试模拟题"""
        system = f"""你是一位资深面试官。根据岗位要求生成 {count} 道面试题。
JSON 结构：
{{
  "questions": [
    {{"id": 1, "category": "技术/项目/行为/开放", "question": "问题内容", "tips": "回答要点提示"}},
    ...
  ],
  "preparation_tips": ["面试准备建议1", "面试准备建议2"]
}}"""
        user_msg = f"""请为以下岗位生成面试题：

岗位：{job_analysis.get('job_title', '未知')}
公司：{job_analysis.get('company', '未知')}
核心要求：{job_analysis.get('core_requirements', '')}
硬技能：{job_analysis.get('hard_skills', '')}
软技能：{job_analysis.get('soft_skills', '')}
日常工作：{job_analysis.get('daily_work', '')}"""
        return self.chat_json(system, user_msg)

    def analyze_interview_review(self, transcript_text: str, job_analysis: dict) -> dict:
        """分析面试复盘（基于妙记转写内容）"""
        system = """你是一位面试辅导专家。根据面试转写内容，分析表现并给出改进建议。
JSON 结构：
{
  "good_answers": ["回答好的问题1（简述原因）"],
  "weak_answers": ["需要改进的问题1（简述原因+建议）"],
  "overall_score": 70,
  "key_improvements": ["核心改进方向1", "核心改进方向2"],
  "next_steps": ["下一步行动计划"],
  "summary": "总体评价（150字以内）"
}"""
        user_msg = f"""请分析以下面试转写内容：

【面试岗位】{job_analysis.get('job_title', '未知')} - {job_analysis.get('company', '未知')}

【面试转写】
{transcript_text[:5000]}"""
        return self.chat_json(system, user_msg)

    def compare_offers(self, offers: list) -> dict:
        """OFFER 多维对比分析"""
        system = """你是一位职业规划专家。请对多个 OFFER 进行五维对比分析。
五个维度：薪资待遇、岗位发展、企业发展、行业发展、工作内容
每个维度 1-5 分。
JSON 结构：
{
  "comparison": [
    {
      "company": "公司名",
      "position": "岗位",
      "salary_score": 5,
      "career_score": 4,
      "company_score": 5,
      "industry_score": 4,
      "work_score": 4,
      "total": 22,
      "pros": ["优势1"],
      "cons": ["劣势1"],
      "risk_notes": "风险提示"
    }
  ],
  "recommendation": "综合推荐（200字以内）",
  "ranked": ["推荐排序：公司1", "公司2"]
}"""
        offers_text = "\n\n".join([
            f"OFFER {i+1}:\n公司: {o.get('company','')}\n岗位: {o.get('position','')}\n薪资: {o.get('salary','')}\n其他: {o.get('notes','')}"
            for i, o in enumerate(offers)
        ])
        return self.chat_json(system, f"请对比以下 OFFER：\n\n{offers_text}")

    def company_background_check(self, company_name: str) -> dict:
        """公司背景调查"""
        system = """你是一位企业调研专家。请对目标公司进行背景分析。
注意：如果不确定的信息，请标注"待核实"。
JSON 结构：
{
  "company_name": "公司全称",
  "industry": "所属行业",
  "scale": "公司规模",
  "stage": "发展阶段（初创/成长/成熟/上市）",
  "reputation": "业界口碑（综合评价）",
  "culture": "企业文化特点",
  "pros": ["优势1", "优势2"],
  "cons": ["风险/劣势1", "风险/劣势2"],
  "salary_level": "薪资水平评价",
  "work_life_balance": "工作生活平衡评价",
  "career_development": "职业发展空间评价",
  "risk_notes": "重要风险提示",
  "suggestion": "给求职者的建议（100字以内）"
}"""
        return self.chat_json(system, f"请对以下公司进行背景调查：{company_name}")

    def generate_dashboard_summary(self, stats: dict) -> str:
        """生成求职仪表盘摘要"""
        system = """你是一位求职顾问。请根据求职数据生成一段简洁的进度摘要。
使用 Markdown 格式，包含 emoji，语气友好鼓励。控制在 300 字以内。"""
        user_msg = f"""请根据以下求职数据生成今日进度摘要：

{json.dumps(stats, ensure_ascii=False, indent=2)}"""
        return self.chat(system, user_msg, temperature=0.8)

    def optimize_resume_content(self, resume_text: str, job_title: str, company: str, suggestions: str) -> dict:
        """根据匹配建议优化简历"""
        system = """你是一位资深简历优化专家。请根据岗位匹配分析的建议，对原始简历进行优化。
要求：
1. 保持简历的真实性，不编造经历
2. 针对匹配建议中的缺失项，合理调整简历内容的表述方式
3. 突出与目标岗位相关的经验和技能
4. 优化简历结构和措辞，使其更专业
5. 输出优化后的完整简历内容

JSON 结构：
{
  "optimized_resume": "优化后的完整简历内容（Markdown 格式）",
  "key_changes": ["主要修改点1", "主要修改点2", "主要修改点3"],
  "improved_score": 85
}"""
        user_msg = f"""请根据以下信息优化简历：

【目标岗位】{job_title} @ {company}

【匹配修改建议】
{suggestions}

【原始简历】
{resume_text[:5000]}"""
        return self.chat_json(system, user_msg, temperature=0.5)
