"""
AI 职业定位引擎
分析简历，输出：核心方向、可迁移方向、弱项提醒、中英双语关键词、薪资锚定
"""

import json
from pathlib import Path
from datetime import datetime


CAREER_ADVISOR_PROMPT = """你是一位资深的职业规划顾问。请深入分析候选人的简历，输出一份职业定位报告。

核心任务：
1. **能力拆解**：将候选人的技能和经验拆解为基础能力、专业能力、软技能
2. **双轨策略**：
   - 策略A（行业→职位）：从候选人熟悉的行业出发，列出该行业中适合的职位
   - 策略B（职位→行业）：从候选人的核心能力出发，反推哪些行业需要这些能力
3. **市场洞察**：基于当前市场情况，判断哪些方向最有价值

关键词生成规则（极重要）：
- **不要生成具体的职位名称**（如"国际气候合作项目主管"）
- **使用行业-职位分类格式**（如"金融-ESG分析师"、"咨询-可持续发展"）
- 行业名称要通用（参考招聘平台的行业分类）
- 职位名称要宽泛（能让搜索引擎匹配到更多结果）
- 例如：不是"南南合作项目官员"，而是"国际组织-项目管理"或"NGO-政策研究"

搜索关键词格式：
- 中文：用行业大类+职位方向组合，如"金融 ESG分析师"、"国际组织 项目管理"
- 英文：用 industry + role 组合，如"ESG analyst finance"、"climate policy research"
- 关键词应短（2-4个词），不要长句

返回 JSON 格式，**必须**严格按以下结构：

{
  "report_title": "报告标题",
  "generated_at": "生成时间",

  "strategy_a": {
    "description": "策略A：从行业出发找职位",
    "items": [
      {
        "industry": "行业大类（如金融、国际组织、咨询）",
        "roles": ["该行业中适合的职位方向"],
        "keywords_zh": ["搜索关键词（行业+职位组合，2-4字）"],
        "keywords_en": ["English search keywords"]
      }
    ]
  },

  "strategy_b": {
    "description": "策略B：从能力出发找行业",
    "items": [
      {
        "skill": "核心能力（如政策研究、项目管理）",
        "industries": ["需要该能力的行业"],
        "keywords_zh": ["搜索关键词（行业+职位组合）"],
        "keywords_en": ["English search keywords"]
      }
    ]
  },

  "weakness_alerts": [
    {
      "area": "弱项领域",
      "severity": "high/medium/low",
      "description": "具体描述",
      "suggestion": "建议"
    }
  ],

  "salary_anchor": {
    "current_estimated_range": "基于简历估计的薪资",
    "market_range": "市场范围",
    "note": "说明"
  },

  "search_keywords": {
    "zh": ["所有中文搜索关键词的汇总列表"],
    "en": ["所有英文搜索关键词的汇总列表"]
  },

  "search_strategy": {
    "recommended_platforms": ["推荐平台"],
    "tips": ["搜索建议"]
  }
}

注意：
1. search_keywords 是策略A和策略B所有关键词的去重汇总，方便直接用于搜索
2. 行业名称参考：金融、咨询、互联网、国际组织、能源、环保、教育、医疗、制造、法律、媒体
3. 职位方向参考：项目经理、分析师、研究员、顾问、产品经理、运营、工程师、设计师"""


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
1. 用双轨策略（行业→职位 + 能力→行业）尽可能扩大覆盖面
2. 关键词要短（2-4词），不要具体职位名，要行业+职位方向组合
3. 目标是"广撒网"——尽可能多发现可能的岗位，后续由AI匹配筛选
4. 薪资建议基于当前市场数据，候选人不接受降薪"""

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

    def get_search_keywords(self, report: dict, lang: str = "zh") -> list:
        """从报告中提取搜索关键词"""
        keywords = report.get("search_keywords", {})
        return keywords.get(lang, keywords.get("zh", []))
