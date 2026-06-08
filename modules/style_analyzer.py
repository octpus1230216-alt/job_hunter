"""
公司风格分析器 — 识别公司文化，匹配简历模板和语言风格
"""

from pathlib import Path


class StyleAnalyzer:
    """
    分析目标公司的风格类型，决定：
    1. 使用哪种简历模板
    2. 采用哪种语言风格
    3. Cover Letter 的切入角度
    """

    # 四大风格类别
    STYLES = {
        "tech_giant": {
            "name": "互联网大厂",
            "tone": "direct",
            "description": "结果导向、数据驱动、技术栈突出",
            "template": "tech_china",
            "cover_angle": "展示量化成果和技术深度，强调能独立owner项目",
            "key_phrases": ["数据驱动", "业务增长", "技术深度", "owner意识", "跨团队协作"],
            "examples": ["阿里巴巴", "字节跳动", "腾讯", "Google", "Meta", "Amazon"],
        },
        "startup": {
            "name": "创业公司",
            "tone": "direct",
            "description": "全栈能力、主动性、ownership、从0到1",
            "template": "startup",
            "cover_angle": "展示多面手能力和创业心态，强调快速学习和对产品的热情",
            "key_phrases": ["从0到1", "快速迭代", "全栈能力", "用户导向", "自驱力"],
            "examples": ["早期Startup", "YC孵化公司", "A/B轮公司"],
        },
        "corporate": {
            "name": "传统外企/大企业",
            "tone": "balanced",
            "description": "专业严谨、团队协作、长期价值",
            "template": "corporate",
            "cover_angle": "展示专业素养和团队协作能力，强调长期贡献和稳定性",
            "key_phrases": ["团队协作", "专业严谨", "流程优化", "跨部门沟通", "最佳实践"],
            "examples": ["Microsoft", "IBM", "Oracle", "SAP", "Siemens"],
        },
        "consulting": {
            "name": "咨询/金融/专业服务",
            "tone": "formal",
            "description": "分析能力、领导力、精英形象",
            "template": "consulting",
            "cover_angle": "展示分析框架和领导力，强调解决问题的结构化和影响力",
            "key_phrases": ["分析框架", "领导力", "结构化思维", "客户导向", "影响力"],
            "examples": ["McKinsey", "Goldman Sachs", "BCG", "Deloitte"],
        },
    }

    def __init__(self, llm_client):
        self.llm = llm_client

    def analyze(self, job: dict, company_info: dict = None) -> dict:
        """
        分析公司风格

        输入：
        - job: 包含JD的岗位信息
        - company_info: 额外的公司信息（可选）

        返回风格分析结果
        """
        from modules.llm import STYLE_ANALYSIS_PROMPT

        # 构建分析输入
        company_name = job.get("company", "")
        job_title = job.get("title", "")
        job_desc = job.get("description", "")[:2000]
        company_industry = job.get("company_industry", "")
        company_size = company_info.get("size", "unknown") if company_info else "unknown"

        user_prompt = f"""请分析以下公司的风格类型：

公司：{company_name}
职位：{job_title}
行业：{company_industry}
规模：{company_size}

职位描述摘要：
{job_desc}

请判断这家公司最接近哪种风格类型，并给出理由。"""

        try:
            result = self.llm.chat_json(STYLE_ANALYSIS_PROMPT, user_prompt)
            category = result.get("style_category", "corporate")
            # 确保是合法的风格类别
            if category not in self.STYLES:
                category = "corporate"
            result["style_detail"] = self.STYLES.get(category, self.STYLES["corporate"])
            return result
        except Exception as e:
            # 默认返回企业风格
            return {
                "style_category": "corporate",
                "tone": "balanced",
                "language_style": "专业严谨",
                "resume_template": "corporate",
                "key_values": ["专业", "协作"],
                "cover_letter_angle": "展示专业能力和团队协作",
                "style_detail": self.STYLES["corporate"],
                "error": str(e),
            }

    def get_template_path(self, style_category: str) -> Path:
        """获取对应风格的模板路径"""
        templates_dir = Path(__file__).parent.parent / "templates"
        template_name = self.STYLES.get(style_category, self.STYLES["corporate"])["template"]
        return templates_dir / template_name

    def get_cover_letter_config(self, style_category: str) -> dict:
        """获取 Cover Letter 配置"""
        style = self.STYLES.get(style_category, self.STYLES["corporate"])
        return {
            "tone": style["tone"],
            "angle": style["cover_angle"],
            "key_phrases": style["key_phrases"],
        }
