"""
每日精选推荐 — 自动搜索+匹配，输出当天最适合投递的岗位

运行方式：
    手动运行: python daily_digest.py
    定时运行: 配合 Windows Task Scheduler 或 GitHub Actions
"""

import json
import sys
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent / "data"
DIGEST_DIR = DATA_DIR / "daily_digests"
DIGEST_DIR.mkdir(parents=True, exist_ok=True)


def load_resume():
    """加载简历"""
    resume_file = DATA_DIR / "resume_parsed.json"
    if resume_file.exists():
        with open(resume_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_career_report():
    """加载最新的职业定位报告"""
    import glob
    files = sorted(DATA_DIR.glob("career_report_*.json"), reverse=True)
    if files:
        with open(files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def search_overseas(keywords: list) -> list:
    """搜索海外平台"""
    jobs = []
    try:
        from jobspy import scrape_jobs
        import pandas as pd

        countries = ["usa", "china", "singapore", "germany", "uk/united kingdom"]
        platforms = ["indeed"]

        for kw in keywords[:8]:
            for country in countries[:3]:
                try:
                    df = scrape_jobs(
                        site_name="indeed",
                        search_term=kw,
                        results_wanted=15,
                        hours_old=24,
                        country_indeed=country,
                    )
                    if df is not None and not df.empty:
                        records = df.head(10).to_dict("records")
                        for r in records:
                            r["source_platform"] = "indeed_daily"
                        jobs.extend(records)
                except Exception:
                    continue
    except ImportError:
        print("⚠️ JobSpy 未安装，跳过海外搜索")

    return jobs


def search_ai(keywords: list) -> list:
    """AI 全网搜索"""
    jobs = []
    try:
        from modules.llm import LLMClient
        from modules.ai_searcher import AISearcher

        llm = LLMClient()
        searcher = AISearcher(llm)

        for kw in keywords[:6]:
            try:
                results = searcher._search_single(kw, 10)
                jobs.extend(results)
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ AI搜索失败: {e}")

    return jobs


def match_jobs(jobs: list, resume: dict) -> list:
    """对岗位进行匹配打分"""
    try:
        from modules.llm import LLMClient
        from modules.matcher import JobMatcher

        llm = LLMClient()
        matcher = JobMatcher(llm)

        matched = []
        for i, job in enumerate(jobs[:50]):
            try:
                match = matcher.match_single(resume, job)
                job["_match_score"] = match.get("overall_score", 0)
                job["_match_strengths"] = match.get("strengths", [])
                matched.append(job)
            except Exception:
                job["_match_score"] = 0
                matched.append(job)

            print(f"  ({i+1}/{min(len(jobs), 50)}) {job.get('company', '?')} — {job.get('title', '?')} : {job.get('_match_score', 0)}分")

        matched.sort(key=lambda x: x.get("_match_score", 0), reverse=True)
        return matched
    except Exception as e:
        print(f"⚠️ 匹配失败: {e}")
        return jobs


def save_digest(jobs: list, keywords: list):
    """保存每日精选"""
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = DIGEST_DIR / f"digest_{today}.json"

    top_20 = jobs[:20]

    digest = {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "total_found": len(jobs),
        "top_20": top_20,
        "search_keywords": keywords,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 每日精选已保存: {filepath}")
    print(f"   共发现 {len(jobs)} 个岗位，精选前 20 个")

    # 打印摘要
    print("\n📊 今日 Top 5:")
    for i, job in enumerate(top_20[:5]):
        score = job.get("_match_score", "?")
        print(f"  #{i+1} [{score}分] {job.get('company', '?')} — {job.get('title', '?')}")

    return filepath


def load_latest_digest() -> dict:
    """加载最新的每日精选"""
    files = sorted(DIGEST_DIR.glob("digest_*.json"), reverse=True)
    if files:
        with open(files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_digests(days: int = 7) -> list:
    """加载最近N天的精选"""
    files = sorted(DIGEST_DIR.glob("digest_*.json"), reverse=True)[:days]
    digests = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            digests.append(json.load(fh))
    return digests


def main():
    print("=" * 50)
    print("  📊 每日精选推荐")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 加载简历
    resume = load_resume()
    if not resume:
        print("❌ 未找到简历，请先在工具中上传并解析简历")
        return

    # 加载职业定位报告
    report = load_career_report()
    keywords_zh = []
    keywords_en = ["ESG analyst", "climate policy", "sustainability", "carbon market"]

    if report:
        kw = report.get("search_keywords", {})
        keywords_zh = kw.get("zh", [])[:5]
        keywords_en = kw.get("en", [])[:5]
        print(f"📋 关键词: {keywords_zh[:3]} | {keywords_en[:3]}")
    else:
        print("⚠️ 未找到职业定位报告，使用默认关键词")

    all_keywords = keywords_zh + keywords_en

    # 搜索
    print("\n🌍 搜索海外平台...")
    overseas_jobs = search_overseas(keywords_en)
    print(f"   海外: {len(overseas_jobs)} 个")

    print("\n🤖 AI 全网搜索...")
    ai_jobs = search_ai(all_keywords)
    print(f"   AI搜索: {len(ai_jobs)} 个")

    all_jobs = overseas_jobs + ai_jobs

    if not all_jobs:
        print("❌ 未找到任何岗位")
        return

    # 匹配
    print(f"\n🧠 匹配打分（共 {len(all_jobs)} 个）...")
    matched = match_jobs(all_jobs, resume)

    # 保存
    save_digest(matched, all_keywords)


if __name__ == "__main__":
    main()
