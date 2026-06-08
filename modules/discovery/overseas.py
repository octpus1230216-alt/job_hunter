"""
海外职位发现 - 集成 JobSpy
支持 LinkedIn, Indeed, Glassdoor, Google Jobs 等平台
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional


class OverseasJobDiscovery:
    """海外职位发现引擎"""

    # 支持的平台
    PLATFORMS = {
        "linkedin": "LinkedIn",
        "indeed": "Indeed",
        "glassdoor": "Glassdoor",
        "google": "Google Jobs",
        "ziprecruiter": "ZipRecruiter",
    }

    def __init__(self, config: dict, data_dir: Path = None):
        """
        config: discovery.overseas 部分的配置
        data_dir: 数据存储目录
        """
        self.config = config
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data" / "jobs"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def search_all(self, search_terms: list = None, countries: list = None,
                   hours_old: int = None, platforms: list = None,
                   progress_callback=None) -> pd.DataFrame:
        """
        在所有平台搜索职位

        参数:
            search_terms: 搜索关键词列表
            countries: 国家代码列表
            hours_old: 发布时间限制（小时）
            platforms: 使用的平台列表（默认全部）
            progress_callback: 进度回调函数

        返回: 聚合的 DataFrame
        """
        search_terms = search_terms or self.config.get("search_terms", ["software engineer"])
        countries = countries or self.config.get("countries", ["US"])
        hours_old = hours_old or self.config.get("hours_old", 168)
        platforms = platforms or list(self.PLATFORMS.keys())

        all_jobs = []

        for platform in platforms:
            if platform not in self.PLATFORMS:
                continue

            if progress_callback:
                progress_callback(f"正在搜索 {self.PLATFORMS[platform]}...")

            for term in search_terms:
                for country in countries:
                    try:
                        df = self._search_platform(platform, term, country, hours_old)
                        if df is not None and not df.empty:
                            all_jobs.append(df)
                    except Exception as e:
                        if progress_callback:
                            progress_callback(f"  {self.PLATFORMS[platform]} 搜索 '{term}' 在 {country} 失败: {e}")

        if not all_jobs:
            return pd.DataFrame()

        result = pd.concat(all_jobs, ignore_index=True)
        result = result.drop_duplicates(subset=["job_url"], keep="first")
        return result

    def _search_platform(self, platform: str, search_term: str,
                         country: str, hours_old: int) -> Optional[pd.DataFrame]:
        """在单个平台搜索"""
        from jobspy import scrape_jobs

        kwargs = {
            "site_name": platform,
            "search_term": search_term,
            "results_wanted": self.config.get("max_results", 200),
            "hours_old": hours_old,
            "country_indeed": country,
        }

        # LinkedIn 特定参数
        if platform == "linkedin":
            proxy = self.config.get("proxy", "")
            if proxy:
                kwargs["proxy"] = proxy

        # Google Jobs 特定参数
        if platform == "google":
            kwargs["google_search_term"] = f"{search_term} jobs"

        try:
            jobs_df = scrape_jobs(**kwargs)
            if jobs_df is not None and not jobs_df.empty:
                jobs_df["source_platform"] = platform
                jobs_df["source_country"] = country
                jobs_df["discovered_at"] = datetime.now().isoformat()
            return jobs_df
        except Exception:
            return None

    def save_results(self, df: pd.DataFrame, filename: str = None):
        """保存搜索结果"""
        if df.empty:
            return None

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"overseas_jobs_{timestamp}"

        # 保存 CSV
        csv_path = self.data_dir / f"{filename}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        # 保存 JSON（更方便后续处理）
        json_path = self.data_dir / f"{filename}.json"
        df.to_json(json_path, orient="records", force_ascii=False, indent=2)

        return {"csv": str(csv_path), "json": str(json_path)}

    def load_latest_results(self) -> Optional[pd.DataFrame]:
        """加载最近一次搜索结果"""
        json_files = sorted(self.data_dir.glob("overseas_jobs_*.json"), reverse=True)
        if json_files:
            return pd.read_json(json_files[0], orient="records")
        return None

    def extract_companies(self, df: pd.DataFrame) -> list:
        """从职位数据中提取公司列表（去重）"""
        if df.empty or "company" not in df.columns:
            return []
        companies = df["company"].dropna().unique().tolist()
        return sorted(companies)
