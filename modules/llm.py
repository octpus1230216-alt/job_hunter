"""
LLM 抽象层 - 支持 DeepSeek / OpenAI / Ollama 三种后端
统一接口，配置中切换 provider 即可
"""

import yaml
import os
from pathlib import Path
from typing import Optional

class LLMClient:
    """统一的 LLM 客户端"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.llm_config = self.config.get("llm", {})
        self.provider = self.llm_config.get("provider", "deepseek")
        self._client = None

    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is not None:
            return self._client

        if self.provider == "deepseek":
            from openai import OpenAI
            cfg = self.llm_config.get("deepseek", {})
            api_key = cfg.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
            self._client = OpenAI(
                api_key=api_key,
                base_url=cfg.get("base_url", "https://api.deepseek.com")
            )
            self._model = cfg.get("model", "deepseek-chat")

        elif self.provider == "openai":
            from openai import OpenAI
            cfg = self.llm_config.get("openai", {})
            api_key = cfg.get("api_key", "") or os.environ.get("OPENAI_API_KEY", "")
            self._client = OpenAI(
                api_key=api_key,
                base_url=cfg.get("base_url", "https://api.openai.com/v1")
            )
            self._model = cfg.get("model", "gpt-4o")

        elif self.provider == "ollama":
            import ollama
            cfg = self.llm_config.get("ollama", {})
            self._client = ollama
            self._model = cfg.get("model", "qwen2.5:14b")
            self._base_url = cfg.get("base_url", "http://localhost:11434")

        elif self.provider == "custom":
            # 任何兼容 OpenAI /v1/chat/completions 的端点（通义千问/智谱/GLM/Kimi/Claude 代理等）
            from openai import OpenAI
            cfg = self.llm_config.get("custom", {})
            api_key = cfg.get("api_key", "") or os.environ.get("CUSTOM_API_KEY", "")
            self._client = OpenAI(
                api_key=api_key,
                base_url=cfg.get("base_url", "https://api.openai.com/v1")
            )
            self._model = cfg.get("model", "gpt-4o")

        else:
            raise ValueError(f"不支持的 LLM provider: {self.provider}")

        return self._client

    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.3, max_tokens: int = 4096) -> str:
        """
        发送聊天请求，返回文本响应
        """
        client = self._get_client()

        if self.provider in ("deepseek", "openai", "custom"):
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content

        elif self.provider == "ollama":
            # Ollama Python client
            import ollama
            client = ollama.Client(host=self._base_url)
            response = client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                options={"temperature": temperature}
            )
            return response["message"]["content"]

    def chat_json(self, system_prompt: str, user_prompt: str,
                  temperature: float = 0.1, max_tokens: int = 4096) -> dict:
        """
        发送聊天请求，返回 JSON 解析后的 dict
        """
        response = self.chat(system_prompt, user_prompt, temperature, max_tokens)
        # 尝试提取 JSON
        import json
        response = response.strip()
        # 移除可能的 markdown 代码块标记
        if response.startswith("```"):
            lines = response.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response = "\n".join(lines)
        return json.loads(response)

    def switch_provider(self, provider: str):
        """切换 LLM 提供商"""
        if provider not in ("deepseek", "openai", "ollama", "custom"):
            raise ValueError(f"不支持的 provider: {provider}")
        self.provider = provider
        self._client = None  # 重置客户端

    @property
    def available_providers(self):
        """检查哪些 provider 可用"""
        available = []
        # DeepSeek
        cfg = self.llm_config.get("deepseek", {})
        if cfg.get("api_key") or os.environ.get("DEEPSEEK_API_KEY"):
            available.append("deepseek")
        # OpenAI
        cfg = self.llm_config.get("openai", {})
        if cfg.get("api_key") or os.environ.get("OPENAI_API_KEY"):
            available.append("openai")
        # Ollama - 总是显示为可配置
        available.append("ollama")
        # Custom (OpenAI 兼容)
        cfg = self.llm_config.get("custom", {})
        if cfg.get("api_key") or os.environ.get("CUSTOM_API_KEY"):
            available.append("custom")
        return available


# 预设的 System Prompts

MATCHING_SYSTEM_PROMPT = """你是一位资深的招聘顾问和简历专家。你的任务是：
1. 分析候选人的简历和目标职位的JD
2. 从多个维度评估匹配度
3. 指出关键的匹配点和差距

请务必客观、具体，以数据驱动的方式给出评分。不要过度乐观。

返回 JSON 格式，包含以下字段：
{
  "overall_score": 0-100 的整数,
  "skill_match": { "score": 0-100, "matched": ["匹配的技能"], "missing": ["缺失的关键技能"] },
  "experience_match": { "score": 0-100, "analysis": "经验匹配分析" },
  "education_match": { "score": 0-100, "analysis": "学历匹配分析" },
  "culture_fit": { "score": 0-100, "analysis": "文化契合度分析" },
  "strengths": ["候选人的核心优势"],
  "weaknesses": ["候选人的主要不足"],
  "recommendation": "是否推荐投递及理由"
}"""

STYLE_ANALYSIS_PROMPT = """你是一位企业文化和品牌风格分析师。分析目标公司的风格类型。

返回 JSON 格式：
{
  "style_category": "tech_giant / startup / corporate / consulting",
  "tone": "direct / balanced / formal",
  "language_style": "结果导向 / 协作导向 / 权威专业",
  "resume_template": "推荐的简历模板名称",
  "key_values": ["公司核心价值观关键词"],
  "cover_letter_angle": "Cover Letter 的切入角度建议",
  "what_they_look_for": "这个风格的公司最看重候选人什么"
}"""

RESUME_CUSTOMIZATION_PROMPT = """你是一位专业的简历定制师。根据主简历和JD，为特定岗位定制简历。

规则：
1. 主简历中的经历都是真实的，不允许编造
2. 可以调整措辞、重新排序、突出与JD匹配的经验
3. 对于JD要求但简历中确实没有的技能，在"技能"部分如实体现但不夸大
4. 语言风格参考 target_style 的描述
5. 量化成果优先（数字、百分比、具体影响）
6. 如果要求双语，同时生成中文和英文两个版本

返回 JSON 格式：
{
  "summary": "定制后的个人总结",
  "summary_en": "English version of summary (if bilingual)",
  "skills": ["技能列表"],
  "skills_en": ["English skills (if bilingual)"],
  "experience": [
    {
      "company": "公司名",
      "title": "职位",
      "title_en": "English title",
      "duration": "时间段",
      "bullets": ["中文要点"],
      "bullets_en": ["English bullets (if bilingual)"]
    }
  ],
  "projects": [
    {
      "name": "项目名",
      "name_en": "English name",
      "description": "项目描述",
      "description_en": "English description",
      "highlights": ["项目亮点"],
      "highlights_en": ["English highlights"]
    }
  ],
  "education": [{ "school": "学校", "degree": "学位", "major": "专业" }],
  "customization_notes": "定制说明"
}"""

COVER_LETTER_PROMPT = """你是一位Cover Letter撰写专家。根据候选人的简历和目标岗位，撰写专业的求职信。

要求：
1. 长度适中（英文300-400词，中文500-600字）
2. 开头要有冲击力，展示你对公司的了解和热情
3. 中间段落用1-2个具体项目/经历证明你能胜任
4. 结尾表达期待，但不卑微
5. 语言风格与目标公司文化匹配
6. 如果要求双语，同时生成中文和英文版本

返回 JSON 格式：
{
  "subject": "中文邮件主题",
  "subject_en": "English subject (if bilingual)",
  "body": "中文正文",
  "body_en": "English body (if bilingual)",
  "language": "zh/en/bilingual",
  "tone_description": "语气说明"
}"""

COMPANY_DISCOVERY_PROMPT = """你是一位行业研究分析师。根据给定的行业和偏好，推荐值得投递的公司。

返回 JSON 格式：
{
  "companies": [
    {
      "name": "公司名称",
      "industry": "所属行业",
      "why_recommend": "推荐理由",
      "size": "大厂/中型/创业",
      "locations": ["主要办公地点"],
      "known_for": "公司以什么闻名",
      "careers_page": "如果知道招聘页面URL就提供，否则留空"
    }
  ],
  "search_suggestions": ["后续可以搜索的关键词建议"]
}"""
