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
            status: str = "saved", notes: str = "",
            competition_level: str = "", llm_apply=None,
            llm_pass_prob=None, llm_reason: str = "") -> dict:
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
            "competition_level": competition_level,
            "llm_apply": llm_apply,
            "llm_pass_prob": llm_pass_prob,
            "llm_reason": llm_reason,
        }

        apps.append(application)
        self.save(apps)
        self._sync_sqlite(application)
        return application

    def update_status(self, app_id: str, status: str, note: str = ""):
        """更新投递状态"""
        apps = self.load()
        matched = None
        for app in apps:
            if app["id"] == app_id:
                app["status"] = status
                app["updated_at"] = datetime.now().isoformat()
                app["history"].append({
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "note": note,
                })
                matched = app
                break
        self.save(apps)
        if matched:
            self._sync_sqlite(matched)

    def update_file_paths(self, app_id: str, resume_path: str, cl_path: str):
        """关联生成的简历和Cover Letter文件"""
        apps = self.load()
        for app in apps:
            if app["id"] == app_id:
                app["resume_file"] = resume_path
                app["cover_letter_file"] = cl_path
                app["updated_at"] = datetime.now().isoformat()
                matched = app
                break
        self.save(apps)
        if matched:
            self._sync_sqlite(matched)

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

    # ============================================================
    # 与 analytics SQLite 打通（双存储孤岛 → 单源回流校准）
    # ============================================================
    # tracker 状态枚举 → analytics.applications.last_status 枚举
    _STATUS_TO_ANALYTICS = {
        "saved": "prospect",
        "applied": "applied",
        "screening": "in_progress",
        "interview_1": "interview",
        "interview_2": "interview",
        "interview_3": "interview",
        "interview_final": "interview",
        "offer": "offer",
        "accepted": "hired",
        "rejected": "rejected",
        "withdrawn": "withdrawn",
        "declined": "offer_declined",
    }

    def _sync_sqlite(self, app: dict) -> None:
        """把一条 JSON 记录回灌到 analytics SQLite（打通双存储孤岛）。失败静默。"""
        try:
            from analytics.modules import store as _store
        except Exception:
            return
        try:
            conn = _store.init_db()
            analytics_status = self._STATUS_TO_ANALYTICS.get(
                app.get("status", "applied"), "applied")
            comp = app.get("competition_level") or _store.infer_competition(app.get("company", ""))
            fields = {
                "last_status": analytics_status,
                "platform": app.get("source", app.get("source_platform", "")),
                "competition_level": comp,
                "fit_overall": app.get("match_score")
                if isinstance(app.get("match_score"), int) else None,
            }
            if app.get("llm_apply") is not None:
                fields["llm_apply"] = app["llm_apply"]
            if app.get("llm_pass_prob") is not None:
                fields["llm_pass_prob"] = app["llm_pass_prob"]
            if app.get("llm_reason"):
                fields["llm_reason"] = app["llm_reason"]
            if app.get("resume_file"):
                fields["archive_path"] = app["resume_file"]
            _store.upsert_application_by_key(
                conn, app.get("company", ""), app.get("title", ""),
                app.get("job_url", ""), **fields)
            _store.close(conn)
        except Exception:
            # SQLite 不可用时不影响 UI（JSON 仍是主存储）
            pass

    def sync_all(self) -> int:
        """把 JSON 中所有记录重新回灌 SQLite（幂等回填）。返回同步条数。"""
        n = 0
        for app in self.load():
            self._sync_sqlite(app)
            n += 1
        return n
