"""
AI 全网搜索 — 利用搜索引擎+LLM发现公开职位
"""

import json
import httpx
from pathlib import Path
from datetime import datetime


AI_SEARCH_PARSE_PROMPT = """你是一位招聘数据分析师。从以下搜索结果中提取真实招聘信息。

规则：
1. 只提取看起来像真实招聘信息的条目
2. 如果无法确定是招聘信息，跳过
3. 提取公司名、职位名、地点（如果有的话）
4. 不要编造信息

搜索结果：
{search_results}

返回 JSON 列表：
[
  {
    "company": "公司名",
    "title": "职位名",
    "location": "工作地点",
    "source_url": "原始URL",
    "snippet": "搜索结果摘要"
  }
]"""


class AISearcher:
    """AI 全网职位搜索"""

    def __init__(self, llm_client, data_dir: Path = None):
        self.llm = llm_client
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def search(self, keywords: list, max_per_keyword: int = 15,
               progress_callback=None) -> list:
        """
        对每个关键词执行搜索，聚合结果

        返回：解析后的职位列表
        """
        all_jobs = []

        for i, kw in enumerate(keywords):
            if progress_callback:
                progress_callback(f"🔍 搜索: {kw} ({i+1}/{len(keywords)})")

            try:
                results = self._search_single(kw, max_per_keyword)
                all_jobs.extend(results)
            except Exception as e:
                if progress_callback:
                    progress_callback(f"  ⚠️ {kw} 搜索失败: {str(e)[:80]}")

        return all_jobs

    def _search_single(self, keyword: str, max_results: int = 15) -> list:
        """单关键词搜索"""
        results = []

        # 用 DuckDuckGo HTML 搜索
        url = f"https://html.duckduckgo.com/html/?q={keyword}+jobs+hiring+2026"

        try:
            resp = httpx.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, timeout=15, follow_redirects=True)

            if resp.status_code != 200:
                return []

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            snippets = []
            for result in soup.select(".result__body")[:max_results]:
                title_el = result.select_one(".result__title")
                snippet_el = result.select_one(".result__snippet")
                url_el = result.select_one(".result__url")

                if title_el and snippet_el:
                    snippets.append({
                        "title": title_el.get_text(strip=True),
                        "snippet": snippet_el.get_text(strip=True)[:300],
                        "url": url_el.get_text(strip=True) if url_el else "",
                    })

            if not snippets:
                return []

            # 用 LLM 解析搜索结果
            search_text = "\n\n---\n\n".join([
                f"标题: {s['title']}\n内容: {s['snippet']}\nURL: {s['url']}"
                for s in snippets
            ])

            ai_prompt = AI_SEARCH_PARSE_PROMPT.replace("{search_results}", search_text)
            parsed = self.llm.chat_json(ai_prompt, ai_prompt)

            # 标准化
            for job in parsed:
                job["description"] = job.get("snippet", "")
                job["source_platform"] = "ai_search"
                job["keyword"] = keyword
                job["discovered_at"] = datetime.now().isoformat()

            return parsed

        except Exception:
            return []

    def search_bilingual(self, zh_keywords: list, en_keywords: list,
                         max_per: int = 15, progress_callback=None) -> dict:
        """中英文双语搜索"""
        results = {"zh": [], "en": []}

        if zh_keywords:
            if progress_callback:
                progress_callback("🌏 开始中文搜索...")
            results["zh"] = self.search(zh_keywords, max_per, progress_callback)

        if en_keywords:
            if progress_callback:
                progress_callback("🌍 开始英文搜索...")
            results["en"] = self.search(en_keywords, max_per, progress_callback)

        return results

    def save_results(self, jobs: list) -> Path:
        """保存搜索结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.data_dir / f"ai_search_{timestamp}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
        return filepath
