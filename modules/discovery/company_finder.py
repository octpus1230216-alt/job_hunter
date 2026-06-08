"""
公司发现引擎 — 三层扩展策略
Layer 1: 从职位搜索结果中提取公司
Layer 2: 通过LLM搜索行业榜单和相似公司
Layer 3: 验证公司官网并扫描其ATS
"""

import json
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup


class CompanyFinder:
    """
    三层公司发现策略：

    Layer 1 - 直接提取：从所有职位数据中提取公司名称（已有）
    Layer 2 - 智能扩展：根据已有公司列表，通过LLM发现同行业/同类型公司
    Layer 3 - Web搜索：搜索行业榜单、最佳雇主榜单、高增长公司等
    """

    # 常见公司的 ATS 系统模式
    ATS_PATTERNS = {
        "greenhouse": ["greenhouse.io", "boards.greenhouse.io"],
        "lever": ["jobs.lever.co", "lever.co"],
        "workday": ["myworkdayjobs.com", "workday.com"],
        "ashby": ["jobs.ashbyhq.com"],
        "bamboohr": ["bamboohr.com/careers"],
        "smartrecruiters": ["smartrecruiters.com"],
        "icims": ["icims.com"],
        "taleo": ["taleo.net"],
        "successfactors": ["successfactors.com"],
    }

    # 常见 career 页面路径
    CAREER_PATH_PATTERNS = [
        "/careers", "/jobs", "/join-us", "/work-with-us",
        "/about/careers", "/company/careers", "/team", "/open-positions",
        "/hiring", "/employment", "/opportunities",
    ]

    def __init__(self, config: dict, llm_client, data_dir: Path = None):
        self.config = config
        self.llm = llm_client
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data" / "companies"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # Layer 1: 从职位数据提取公司
    # ============================================================
    def extract_from_jobs(self, jobs_df) -> list:
        """从职位DataFrame提取公司名"""
        if jobs_df is None or jobs_df.empty:
            return []
        if "company" not in jobs_df.columns:
            return []
        companies = jobs_df["company"].dropna().unique().tolist()
        return sorted(companies)

    # ============================================================
    # Layer 2: 智能扩展 — LLM发现同类型公司
    # ============================================================
    def expand_with_llm(self, existing_companies: list,
                        industries: list, locations: list,
                        max_new: int = 50) -> list:
        """
        根据已有公司 + 行业偏好，让 LLM 推荐值得投递的公司

        这个方法不依赖网络搜索，纯靠 LLM 知识
        """
        if not self.llm:
            return []

        from modules.llm import COMPANY_DISCOVERY_PROMPT

        user_prompt = f"""请根据以下信息推荐公司：

已有公司（参考行业和规模）：{existing_companies[:30]}

目标行业：{industries}
目标地区：{locations}
扩展策略：
1. 同行业竞争对手
2. 上下游生态公司  
3. 同地区同规模公司
4. 目标行业中的高增长/值得关注的公司

最多推荐 {max_new} 家公司，优先推荐正在扩张招聘的公司。"""

        try:
            result = self.llm.chat_json(COMPANY_DISCOVERY_PROMPT, user_prompt)
            companies = result.get("companies", [])
            suggestions = result.get("search_suggestions", [])
            return companies
        except Exception as e:
            print(f"LLM 公司扩展失败: {e}")
            return []

    # ============================================================
    # Layer 3: Web搜索 — 搜索榜单和发现新公司
    # ============================================================
    async def search_industry_rankings(self, industries: list,
                                       locations: list = None) -> list:
        """
        通过网络搜索发现公司：
        - 行业榜单（"top AI companies 2026"）
        - 最佳雇主榜单
        - 高增长公司榜单
        - 远程优先公司榜单

        注意：这个方法尝试直接用 httpx 获取搜索结果，
        但在实际使用中可能需要搜索引擎 API。
        """
        companies = []

        # 构建搜索关键词
        keywords = self._build_search_keywords(industries, locations)

        for kw in keywords:
            try:
                results = await self._search_web(kw)
                companies.extend(results)
            except Exception as e:
                print(f"搜索 '{kw}' 失败: {e}")

        # 去重
        seen = set()
        unique = []
        for c in companies:
            name = c.get("name", "").lower()
            if name and name not in seen:
                seen.add(name)
                unique.append(c)

        return unique

    def _build_search_keywords(self, industries: list, locations: list) -> list:
        """构建搜索关键词"""
        keywords = []

        # 行业榜单
        for industry in industries:
            keywords.extend([
                f"top {industry} companies hiring 2026",
                f"best {industry} companies to work for",
                f"fastest growing {industry} startups",
                f"{industry} companies with great culture",
            ])

        # 通用榜单
        keywords.extend([
            "top tech companies hiring now",
            "best remote-first companies 2026",
            "fastest growing tech companies",
            "best workplaces in technology",
            "companies with best engineering culture",
        ])

        # 按地点
        if locations:
            for loc in locations:
                if loc.lower() not in ("远程", "remote"):
                    keywords.append(f"best tech companies to work for in {loc}")

        return keywords

    async def _search_web(self, query: str) -> list:
        """
        执行 Web 搜索并提取公司名称
        这里使用简单的 HTTP 请求，实际部署时可能需要搜索引擎 API
        """
        companies = []

        # 使用 DuckDuckGo 搜索（免费，无 API key）
        url = f"https://html.duckduckgo.com/html/?q={query}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    # 提取搜索结果中的公司名称
                    results = soup.select(".result__body")
                    for result in results[:10]:
                        text = result.get_text()
                        # 简单提取（实际中需要更复杂的NLP）
                        companies.append({
                            "name": text.split(" ")[0][:50],
                            "source": "web_search",
                            "query": query
                        })
        except Exception:
            pass

        return companies

    # ============================================================
    # ATS 发现: 找到公司的招聘页面
    # ============================================================
    async def find_careers_page(self, company_name: str, company_url: str = None) -> Optional[dict]:
        """
        尝试找到公司的招聘页面
        1. 先试常见URL模式（careers.xxx.com, xxx.com/careers）
        2. 如果都有，检查是哪种ATS
        """
        domains_to_try = []

        # 如果提供了公司URL
        if company_url:
            domain = company_url.rstrip("/")
            domains_to_try.append(domain)
            # 尝试常见子域名
            for pattern in ["careers", "jobs", "join"]:
                domains_to_try.append(f"https://{pattern}.{self._extract_root_domain(domain)}")

        # 搜索公司名 + careers
        if company_name:
            domains_to_try.append(f"https://careers.{company_name.lower().replace(' ', '')}.com")
            domains_to_try.append(f"https://www.{company_name.lower().replace(' ', '')}.com/careers")
            domains_to_try.append(f"https://www.{company_name.lower().replace(' ', '')}.com/jobs")

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for url in domains_to_try:
                try:
                    response = await client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    if response.status_code == 200:
                        ats_type = self._detect_ats(str(response.url), response.text)
                        return {
                            "careers_url": str(response.url),
                            "ats_type": ats_type,
                            "status": "found"
                        }
                except Exception:
                    continue

        return {"status": "not_found", "tried_urls": domains_to_try}

    def _detect_ats(self, url: str, html: str) -> Optional[str]:
        """检测 ATS 系统类型"""
        url_lower = url.lower()
        html_lower = html.lower()

        for ats_name, patterns in self.ATS_PATTERNS.items():
            for pattern in patterns:
                if pattern in url_lower or pattern in html_lower:
                    return ats_name
        return "unknown"

    def _extract_root_domain(self, url: str) -> str:
        """提取根域名"""
        url = url.replace("https://", "").replace("http://", "")
        parts = url.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return url

    # ============================================================
    # 综合发现方法
    # ============================================================
    def discover_all(self, existing_jobs_df=None,
                     industries: list = None,
                     locations: list = None,
                     existing_companies: list = None) -> dict:
        """
        综合三层发现策略，返回统一的公司列表

        返回: {
            "companies": [...],
            "total_found": 数量,
            "by_source": { "extracted": N, "llm_expanded": N, "web_search": N }
        }
        """
        all_companies = {}
        sources_count = {"extracted": 0, "llm_expanded": 0, "web_search": 0}

        # Layer 1: 从职位提取
        if existing_jobs_df is not None:
            extracted = self.extract_from_jobs(existing_jobs_df)
            for name in extracted:
                if name not in all_companies:
                    all_companies[name] = {"name": name, "source": "job_extraction"}
            sources_count["extracted"] = len(extracted)

        # Layer 2: LLM扩展（同步，因为Streamlit不支持原生的async）
        if existing_companies or all_companies:
            base_list = existing_companies or list(all_companies.keys())
            industries = industries or ["人工智能", "互联网", "金融科技"]
            locations = locations or ["远程", "北京", "上海"]
            expanded = self.expand_with_llm(base_list, industries, locations)
            for c in expanded:
                name = c.get("name", "")
                if name and name not in all_companies:
                    all_companies[name] = {**c, "source": "llm_expansion"}
            sources_count["llm_expanded"] = len(expanded)

        result = {
            "companies": list(all_companies.values()),
            "total_found": len(all_companies),
            "by_source": sources_count,
            "discovered_at": datetime.now().isoformat()
        }

        # 保存结果
        self._save_companies(result)

        return result

    def _save_companies(self, result: dict):
        """保存公司发现结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.data_dir / f"companies_{timestamp}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    def load_latest_companies(self) -> Optional[dict]:
        """加载最近的公司发现结果"""
        json_files = sorted(self.data_dir.glob("companies_*.json"), reverse=True)
        if json_files:
            with open(json_files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        return None
