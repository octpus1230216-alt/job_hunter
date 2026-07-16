"""store.py — 复盘分析模块的本地存储层（stdlib sqlite3，零重依赖）。

数据模型对齐 MadsLorentzen/ai-job-search 的 job_search_tracker.csv + outcome.md 归档约定，
并补齐 job_hunter 缺失的：no_response(已读不回) / rejected(不合适) 状态、五维 fit_* 子分、
resume_version(A/B 变量)。

所有字段一次建表，analyzer / score / collect 都只通过本模块读写，不直接碰 SQL。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

# 默认库位置：工作区 data/ 下（与 job_hunter 的 data/applications/ 同级）
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "job_search.db"

# 结果状态枚举（借 MadsLorentzen outcome.md；rejected=不合适, no_response=已读不回）
# prospect = 待分析/观望（新 JD 未投，目标 A 入口）；不参与目标 B 复盘统计
STATUS_ENUM = [
    "prospect",       # 待分析/观望（新 JD 已录入但未投递，目标 A 入口）
    "applied",        # 已投，待回音
    "in_progress",    # 流程中（面试阶段）
    "interview",      # 进入面试
    "offer",          # 拿到 offer
    "hired",          # 已入职
    "offer_declined", # 拒 offer
    "rejected",       # 不合适（主动拒绝）
    "no_response",    # 已读不回（沉默）
    "interview_only", # 面了但无下文
    "withdrawn",      # 主动撤投
]

# 复盘统计需排除的状态：prospect 是「未投递、仅评估」的待分析岗位，
# 不能算进「已投结果」的分布 / 交叉 / A-B 回复率，否则污染目标 B 结论。
EXCLUDE_FROM_REVIEW = {"prospect"}

# 五维评分字段（借 MadsLorentzen 04-job-evaluation.md）
FIT_DIMS = ["fit_technical", "fit_experience", "fit_behavioral", "fit_career"]
FIT_LOCATION = "fit_location"  # PASS / FAIL / FLAG

# 加权（技30/经25/文15/职30；location 不参与加权）
WEIGHTS = {"fit_technical": 0.30, "fit_experience": 0.25, "fit_behavioral": 0.15, "fit_career": 0.30}

# 强信号状态：这些才是"信息量大"的主动拒绝，重点分析
STRONG_SIGNAL = {"rejected"}
# 弱信号状态：沉默，不当因果（防误判）
WEAK_SIGNAL = {"no_response", "interview_only"}


def init_db(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            platform      TEXT,                       -- BOSS / 脉脉 / 其他
            company       TEXT NOT NULL,
            sector        TEXT,                       -- 行业
            role          TEXT,                       -- 岗位
            role_type     TEXT,                       -- 实习/初级/中级/高级/专家
            channel       TEXT,                       -- 来源渠道
            applied_date  TEXT,                       -- 投递日期 YYYY-MM-DD
            source_url    TEXT,                       -- JD 链接
            jd_text       TEXT,                       -- JD 关键段落
            hr_reply      TEXT,                       -- HR 原话（可选）
            resume_version TEXT,                      -- A/B 变量：用的第几版简历
            last_status   TEXT NOT NULL DEFAULT 'applied',
            status_date   TEXT,                       -- 状态更新日期
            fit_technical INTEGER,                    -- 五维子分 0-100
            fit_experience INTEGER,
            fit_behavioral INTEGER,
            fit_location  TEXT,                       -- PASS / FAIL / FLAG
            fit_career    INTEGER,
            fit_overall   INTEGER,                    -- 加权总分 0-100
            job_quality   INTEGER,                    -- 岗位本身好坏 1-5（手动）
            notes         TEXT,
            archive_path  TEXT                        -- documents/applications/<company>_<role>/
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS resumes (
            version       TEXT PRIMARY KEY,           -- 简历版本号（orig/v1/v2）
            text          TEXT,                        -- 简历正文（原简历上传后存解析文本）
            created_date  TEXT,
            change_log    TEXT,                        -- 这版改了啥（A/B 实验记录）
            source_file   TEXT,                        -- 原文件来源路径（FR9）
            source_format TEXT                         -- 原文件格式 doc/docx/pdf/txt/md/tex（FR9）
        )
        """
    )
    _migrate_resume_columns(conn)  # 兼容旧库：补 source_file / source_format
    conn.commit()
    return conn


def _migrate_resume_columns(conn: sqlite3.Connection) -> None:
    """兼容旧库：resumes 表若缺 source_file / source_format，则补列（FR9）。"""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(resumes)").fetchall()}
    for col in ("source_file", "source_format"):
        if col not in existing:
            conn.execute(f"ALTER TABLE resumes ADD COLUMN {col} TEXT")


def _archive_slug(company: str, role: str) -> str:
    """<company>_<role> 归档目录名（小写、空格转下划线），对齐 MadsLorentzen 约定。"""
    slug = f"{company}_{role}".lower().replace(" ", "_")
    slug = "".join(c if (c.isalnum() or c == "_") else "_" for c in slug)
    return slug


def add_application(conn: sqlite3.Connection, **fields) -> int:
    """插入一条投递记录。fields 取 applications 表列名。返回新 id。"""
    company = fields.get("company", "")
    role = fields.get("role", "")
    if company and role and not fields.get("archive_path"):
        fields["archive_path"] = f"data/applications/{_archive_slug(company, role)}"
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO applications ({cols}) VALUES ({placeholders})", list(fields.values()))
    conn.commit()
    return cur.lastrowid


def get_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM applications ORDER BY id").fetchall()


def get_by_status(conn: sqlite3.Connection, statuses: Iterable[str]) -> list[sqlite3.Row]:
    q = ",".join("?" for _ in statuses)
    return conn.execute(f"SELECT * FROM applications WHERE last_status IN ({q})", list(statuses)).fetchall()


def get_unscored(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """返回 fit_overall 仍为 NULL 的记录（避免 heuristic 覆盖 LLM/人工预填的精准分）。"""
    return conn.execute("SELECT * FROM applications WHERE fit_overall IS NULL AND jd_text IS NOT NULL").fetchall()


def get_by_id(conn: sqlite3.Connection, app_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()


def update_fit(conn: sqlite3.Connection, app_id: int, *,
               technical=None, experience=None, behavioral=None,
               location=None, career=None, overall=None) -> None:
    """回写五维评分（score.py 调用）。"""
    sets, vals = [], []
    mapping = {
        "fit_technical": technical, "fit_experience": experience,
        "fit_behavioral": behavioral, "fit_location": location,
        "fit_career": career, "fit_overall": overall,
    }
    for col, val in mapping.items():
        if val is not None:
            sets.append(f"{col} = ?")
            vals.append(val)
    if not sets:
        return
    vals.append(app_id)
    conn.execute(f"UPDATE applications SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def set_status(conn: sqlite3.Connection, app_id: int, status: str, status_date: str = "") -> None:
    conn.execute(
        "UPDATE applications SET last_status = ?, status_date = ? WHERE id = ?",
        (status, status_date, app_id),
    )
    conn.commit()


def add_resume(conn: sqlite3.Connection, version: str, text: str, created_date: str, change_log: str = "",
               source_file: str = None, source_format: str = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO resumes (version, text, created_date, change_log, source_file, source_format) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (version, text, created_date, change_log, source_file, source_format),
    )
    conn.commit()


def get_latest_resume(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM resumes ORDER BY created_date DESC, version DESC LIMIT 1").fetchone()


def get_resume(conn: sqlite3.Connection, version: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM resumes WHERE version = ?", (version,)).fetchone()


def count_by(conn: sqlite3.Connection, column: str, exclude_prospect: bool = True) -> list[tuple]:
    """通用分组计数，用于基础统计看板。

    exclude_prospect=True（默认，复盘口径）：排除 `prospect` 待分析岗位，
    保证看板只反映真实投递结果（目标 B）。若需含 prospect 可显式传 False。
    """
    allowed = {"platform", "last_status", "role_type", "sector"}
    if column not in allowed:
        raise ValueError(f"不允许的统计列: {column}")
    where = " WHERE last_status NOT IN ('prospect')" if exclude_prospect else ""
    return conn.execute(
        f"SELECT {column}, COUNT(*) AS n FROM applications{where} GROUP BY {column} ORDER BY n DESC"
    ).fetchall()


def fit_outcome_cross(conn: sqlite3.Connection, exclude_prospect: bool = True) -> list[sqlite3.Row]:
    """fit×outcome 交叉表：按 fit_overall 分档 × 状态计数。

    exclude_prospect=True（默认，复盘口径）：排除 `prospect` 待分析岗位。
    """
    extra = " AND last_status NOT IN ('prospect')" if exclude_prospect else ""
    return conn.execute(
        f"""
        SELECT
            CASE
                WHEN fit_overall >= 75 THEN 'Strong(75+)'
                WHEN fit_overall >= 60 THEN 'Good(60-74)'
                WHEN fit_overall >= 45 THEN 'Moderate(45-59)'
                WHEN fit_overall >= 30 THEN 'Weak(30-44)'
                ELSE 'Poor(<30)'
            END AS fit_band,
            last_status,
            COUNT(*) AS n
        FROM applications
        WHERE fit_overall IS NOT NULL{extra}
        GROUP BY fit_band, last_status
        ORDER BY fit_band, n DESC
        """
    ).fetchall()


def resume_ab(conn: sqlite3.Connection, exclude_prospect: bool = True) -> list[sqlite3.Row]:
    """简历版本 A/B：按 resume_version 分组，算投递数、正反馈数、回复率。

    正反馈 = interview / offer / hired / offer_declined（进入面试或更好）。
    回复率 = 正反馈数 / 投递数。用于对比「改简历有没有用」。

    exclude_prospect=True（默认，复盘口径）：排除 `prospect` 待分析岗位，
    避免未投递的评估记录混入 A/B 回复率。
    """
    extra = " AND last_status NOT IN ('prospect')" if exclude_prospect else ""
    return conn.execute(
        f"""
        SELECT resume_version,
               COUNT(*)                                          AS n,
               SUM(CASE WHEN last_status IN
                   ('interview','offer','hired','offer_declined') THEN 1 ELSE 0 END) AS positive
        FROM applications
        WHERE resume_version IS NOT NULL AND resume_version != ''{extra}
        GROUP BY resume_version
        ORDER BY resume_version
        """
    ).fetchall()


def close(conn: sqlite3.Connection) -> None:
    conn.close()
