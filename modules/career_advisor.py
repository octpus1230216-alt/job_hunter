"""
AI 职业定位引擎
分析简历，输出：核心方向、可迁移方向、弱项提醒、中英双语关键词、薪资锚定
"""

import json
from pathlib import Path
from datetime import datetime


CAREER_ADVISOR_PROMPT = """你是一位资深的职业规划顾问和技术猎头。请深入分析候选人的简历，输出一份职业定位报告。

核心任务：
1. **能力拆解**：将候选人的技能和经验拆解为基础能力、专业能力、软技能
2. **行业映射**：思考这些能力在不同行业中可以如何复用
3. **市场洞察**：基于当前市场情况，判断哪些方向和行业对候选人最有价值

特别注意可迁移方向：
- 不要局限于候选人当前行业
- 思考能力的底层结构：比如"高并发系统设计"可以迁移到金融交易、游戏后端、云计算
- 对每个可迁移方向，说明能力的可复用性和需要补充的知识

返回 JSON 格式，**必须**严格按以下结构：

{
  "report_title": "报告标题",
  "generated_at": "生成时间",

  "core_directions": [
    {
      "role": "核心职位名称",
      "match_score": 0-100,
      "reason": "为什么这是核心方向",
      "key_strengths": ["候选人在这方向的优势"]
    }
  ],

  "transferable_directions": [
    {
      "role": "可迁移职位名称",
      "new_industry": "目标新行业",
      "transferability_score": 0-100,
      "transferable_skills": ["可以直接迁移的能力"],
      "skill_gaps": ["需要补充的知识或技能"],
      "learning_path": "建议的学习路径",
      "example_companies": ["这类岗位的典型公司"],
      "reason": "为什么这个方向值得考虑"
    }
  ],

  "weakness_alerts": [
    {
      "area": "弱项领域",
      "severity": "high/medium/low",
      "description": "具体描述",
      "suggestion": "建议"
    }
  ],

  "salary_anchor": {
    "current_estimated_range": "基于简历经验估计的当前薪资范围",
    "core_direction_range": "核心方向的市场薪资范围",
    "transferable_range": "可迁移方向的市场薪资范围",
    "note": "薪资基于当前市场数据的估计"
  },

  "search_keywords": {
    "zh": {
      "core": ["核心方向中文搜索关键词"],
      "transferable": ["可迁移方向中文搜索关键词"]
    },
    "en": {
      "core": ["核心方向英文搜索关键词"],
      "transferable": ["可迁移方向英文搜索关键词"]
    }
  },

  "search_strategy": {
    "recommended_platforms": ["推荐的搜索平台"],
    "priority_order": "搜索优先级建议",
    "tips": ["搜索技巧提示"]
  }
}"""


class CareerAdvisor:
    """AI 职业规划顾问"""

    def __init__(self, llm_client, data_dir: Path = None):
        self.llm = llm_client
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, resume: dict, preferences: dict = None,
                salary_stance: str = "no_decrease") -> dict:
        """
        分析简历并生成职业定位报告

        参数：
        - resume: 解析后的简历数据
        - preferences: 用户偏好（行业、地点等）
        - salary_stance: 薪资态度 "no_decrease" / "flexible"
        """
        salary_instruction = ""
        if salary_stance == "no_decrease":
            salary_instruction = "\n**薪资要求：不降薪**。只推荐薪资不低于候选人当前水平的岗位。如果某个可迁移方向需要降薪才能入行，请在报告中明确指出。"

        user_prompt = f"""请分析以下候选人的简历，生成职业定位报告。{salary_instruction}

=== 候选人简历 ===
{json.dumps(resume, ensure_ascii=False, indent=2)}

=== 候选人偏好 ===
{json.dumps(preferences or {}, ensure_ascii=False)}

请重点分析：
1. 候选人的能力可以迁移到哪些新行业/新方向
2. 对每个可迁移方向，既要展示机会，也要诚实指出差距
3. 中英文搜索关键词要具体、实用，不要过于宽泛
4. 薪资建议基于当前市场数据"""

        try:
            result = self.llm.chat_json(CAREER_ADVISOR_PROMPT, user_prompt)
            result["generated_at"] = datetime.now().isoformat()
            result["salary_stance"] = salary_stance
            return result
        except Exception as e:
            return {"error": str(e), "generated_at": datetime.now().isoformat()}

    def save_report(self, report: dict) -> Path:
        """保存定位报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.data_dir / f"career_report_{timestamp}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return filepath

    def load_latest_report(self) -> dict:
        """加载最新的定位报告"""
        files = sorted(self.data_dir.glob("career_report_*.json"), reverse=True)
        if files:
            with open(files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def get_search_keywords(self, report: dict, lang: str = "zh",
                            include_transferable: bool = True) -> list:
        """从报告中提取搜索关键词"""
        keywords = report.get("search_keywords", {})

        lang_data = keywords.get(lang, keywords.get("zh", {}))
        result = lang_data.get("core", [])

        if include_transferable:
            result.extend(lang_data.get("transferable", []))

        return result
