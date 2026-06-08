"""
后台搜索工作进程 — 独立于 Streamlit 运行
通过文件系统通信：写入进度/结果到 data/search_tasks/

启动方式: python search_worker.py
"""

import json
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent / "data"
TASK_DIR = DATA_DIR / "search_tasks"
TASK_DIR.mkdir(parents=True, exist_ok=True)


def is_cancelled(task_id: str) -> bool:
    """检查任务是否被取消"""
    cancel_file = TASK_DIR / f"{task_id}_cancel.json"
    return cancel_file.exists()


def cancel_task(task_id: str):
    """取消任务（由UI调用）"""
    cancel_file = TASK_DIR / f"{task_id}_cancel.json"
    cancel_file.write_text("cancelled")
    update_progress(task_id, "cancelled", "用户取消")


def run_overseas_search(task_id: str, params: dict):
    """执行海外平台搜索"""
    terms = params.get("keywords", [])
    countries = params.get("countries", [])
    platforms = params.get("platforms", ["indeed"])
    hours_old = params.get("hours_old", 168)

    update_progress(task_id, "running", f"开始搜索 {len(terms)} 个关键词...")
    all_results = []

    try:
        from jobspy import scrape_jobs
        import pandas as pd

        total = len(terms) * len(countries) * len(platforms)
        count = 0

        for term in terms[:5]:
            if is_cancelled(task_id):
                update_progress(task_id, "cancelled", "用户取消")
                return
            for country_disp in countries[:3]:
                if is_cancelled(task_id):
                    return
                for plat in platforms[:2]:
                    count += 1
                    update_progress(task_id, "running",
                                    f"({count}/{min(total, 30)}) {plat}: {term} in {country_disp}")

                    try:
                        kwargs = {
                            "site_name": plat,
                            "search_term": term,
                            "results_wanted": 30,
                            "hours_old": hours_old,
                            "country_indeed": country_disp.lower(),
                        }
                        if plat == "google":
                            kwargs["google_search_term"] = f"{term} jobs"

                        df = scrape_jobs(**kwargs)
                        if df is not None and not df.empty:
                            df["source_platform"] = plat
                            df["source_country"] = country_disp
                            all_results.append(df)
                    except Exception as e:
                        update_progress(task_id, "running", f"  ⚠️ 跳过: {str(e)[:80]}")

                    time.sleep(1)  # 避免请求过快

        if all_results:
            combined = pd.concat(all_results, ignore_index=True)
            combined = combined.drop_duplicates(subset=["job_url"], keep="first")
            jobs = combined.head(100).to_dict("records")

            save_results(task_id, jobs)
            update_progress(task_id, "completed", f"完成！共找到 {len(jobs)} 个职位")
        else:
            update_progress(task_id, "completed", "未找到匹配的职位")

    except ImportError as e:
        update_progress(task_id, "error", f"缺少依赖: {e}")
    except Exception as e:
        update_progress(task_id, "error", f"搜索失败: {str(e)[:200]}")
        traceback.print_exc()


def run_ai_search(task_id: str, params: dict):
    """执行 AI 全网搜索"""
    zh_keywords = params.get("zh_keywords", [])
    en_keywords = params.get("en_keywords", [])
    max_per = params.get("max_per_keyword", 15)

    update_progress(task_id, "running", "开始 AI 全网搜索...")

    try:
        from modules.llm import LLMClient
        from modules.ai_searcher import AISearcher

        llm = LLMClient()
        searcher = AISearcher(llm)

        all_jobs = []

        for kw in (zh_keywords + en_keywords)[:12]:
            if is_cancelled(task_id):
                update_progress(task_id, "cancelled", "用户取消")
                return
            update_progress(task_id, "running", f"🔍 搜索: {kw}")
            results = searcher._search_single(kw, max_per)
            all_jobs.extend(results)
            time.sleep(1)

        if all_jobs:
            save_results(task_id, all_jobs)
            update_progress(task_id, "completed", f"完成！共找到 {len(all_jobs)} 个职位")
        else:
            update_progress(task_id, "completed", "未找到匹配的职位")

    except Exception as e:
        update_progress(task_id, "error", f"AI搜索失败: {str(e)[:200]}")


def update_progress(task_id: str, status: str, message: str):
    """更新任务进度文件"""
    progress = {
        "task_id": task_id,
        "status": status,
        "message": message,
        "updated_at": datetime.now().isoformat(),
    }
    filepath = TASK_DIR / f"{task_id}_progress.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def save_results(task_id: str, jobs: list):
    """保存搜索结果"""
    filepath = TASK_DIR / f"{task_id}_results.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def get_task_status(task_id: str) -> dict:
    """获取任务状态"""
    filepath = TASK_DIR / f"{task_id}_progress.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"task_id": task_id, "status": "unknown", "message": ""}


def get_task_results(task_id: str) -> list:
    """获取任务结果"""
    filepath = TASK_DIR / f"{task_id}_results.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def poll_tasks():
    """轮询新任务并执行"""
    print("🔍 后台搜索工作进程已启动")
    print(f"📂 任务目录: {TASK_DIR}")
    print("⏳ 等待新任务...")

    while True:
        # 查找待处理的任务
        for task_file in sorted(TASK_DIR.glob("*_task.json")):
            task_id = task_file.stem.replace("_task", "")

            # 检查是否已经在处理
            progress_file = TASK_DIR / f"{task_id}_progress.json"
            if progress_file.exists():
                continue

            # 读取任务参数
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)

            task_type = task.get("type", "overseas")
            params = task.get("params", {})

            print(f"\n🚀 开始执行任务: {task_id} (类型: {task_type})")

            if task_type == "overseas":
                run_overseas_search(task_id, params)
            elif task_type == "ai_search":
                run_ai_search(task_id, params)
            else:
                print(f"  ⚠️ 未知任务类型: {task_type}")

        time.sleep(3)


def submit_task(task_type: str, params: dict) -> str:
    """提交一个搜索任务，返回 task_id"""
    task_id = f"{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    task = {
        "task_id": task_id,
        "type": task_type,
        "params": params,
        "created_at": datetime.now().isoformat(),
    }
    filepath = TASK_DIR / f"{task_id}_task.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    return task_id


if __name__ == "__main__":
    poll_tasks()
