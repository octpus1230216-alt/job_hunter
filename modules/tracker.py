"""
投递追踪模块 — 记录和管理投递状态
"""

import json
from pathlib import Path
from datetime import datetime


class ApplicationTracker:
    """投递状态追踪"""

    STATUSES = {
        "saved": "已收藏",
        "applied": "已投递",
        "screening": "简历筛选",
        "interview_1": "一面",
        "interview_2": "二面",
        "interview_3": "三面",
        "interview_final": "终面",
        "offer": "已获Offer",
        "rejected": "已拒绝",
        "withdrawn": "已撤回",
        "accepted": "已接受",
        "declined": "已拒绝Offer",
    }

    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "applications"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.applications_file = self.data_dir / "applications.json"

    def load(self) -> list:
        """加载所有投递记录"""
        if self.applications_file.exists():
            with open(self.applications_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save(self, applications: list):
        """保存投递记录"""
        with open(self.applications_file, "w", encoding="utf-8") as f:
            json.dump(applications, f, ensure_ascii=False, indent=2)

    def add(self, company: str, title: str, job_url: str = "",
            source: str = "", match_score: int = 0,
            status: str = "saved", notes: str = "") -> dict:
        """添加投递记录"""
        apps = self.load()

        application = {
            "id": str(len(apps) + 1).zfill(4),
            "company": company,
            "title": title,
            "job_url": job_url,
            "source": source,
            "match_score": match_score,
            "status": status,
            "notes": notes,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "history": [
                {"status": status, "timestamp": datetime.now().isoformat(), "note": "创建"}
            ],
            "resume_file": "",
            "cover_letter_file": "",
        }

        apps.append(application)
        self.save(apps)
        return application

    def update_status(self, app_id: str, status: str, note: str = ""):
        """更新投递状态"""
        apps = self.load()
        for app in apps:
            if app["id"] == app_id:
                app["status"] = status
                app["updated_at"] = datetime.now().isoformat()
                app["history"].append({
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "note": note,
                })
                break
        self.save(apps)

    def update_file_paths(self, app_id: str, resume_path: str, cl_path: str):
        """关联生成的简历和Cover Letter文件"""
        apps = self.load()
        for app in apps:
            if app["id"] == app_id:
                app["resume_file"] = resume_path
                app["cover_letter_file"] = cl_path
                app["updated_at"] = datetime.now().isoformat()
                break
        self.save(apps)

    def get_by_status(self, status: str) -> list:
        """按状态筛选"""
        apps = self.load()
        return [a for a in apps if a["status"] == status]

    def get_stats(self) -> dict:
        """统计"""
        apps = self.load()
        stats = {status: 0 for status in self.STATUSES}
        for app in apps:
            status = app["status"]
            if status in stats:
                stats[status] += 1

        return {
            "total": len(apps),
            "by_status": stats,
            "active": len(apps) - stats.get("rejected", 0) - stats.get("withdrawn", 0) - stats.get("declined", 0),
        }

    def delete(self, app_id: str):
        """删除记录"""
        apps = self.load()
        apps = [a for a in apps if a["id"] != app_id]
        self.save(apps)
