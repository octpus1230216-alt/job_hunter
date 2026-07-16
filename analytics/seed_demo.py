"""seed_demo.py — 写入示例数据并跑通 Phase 0 全链路（免 key）。

场景：两版简历（v1 弱、v2 增强），投了若干岗位，出现 rejected / no_response / interview。
其中特意埋了「高 fit + rejected」的信号，用来验证 analyzer 的交叉分析能抓到它。

运行：python seed_demo.py
"""

from __future__ import annotations

from pathlib import Path

from modules.store import DEFAULT_DB, init_db, add_application, add_resume, _archive_slug

ROOT = Path(__file__).resolve().parent


PROFILE_V1 = """张三 简历 v1
技能：Excel、基础 SQL、PPT。
经历：1 年电商运营助理，做过活动表格整理、社群打卡。
教育：某大学 市场营销 本科。"""

PROFILE_V2 = """张三 简历 v2
技能：SQL、Python(Pandas)、Tableau 可视化、AB 实验、指标体系搭建、Excel、PPT。
经历：
- 2 年数据分析，搭建 GMV/留存指标体系，用 SQL+Python 产出周报看板。
- 主导 3 次 AB 实验，提升转化 8%。
- 电商运营助理 1 年，活动策划与社群运营。
教育：某大学 市场营销 本科。"""


def seed(conn) -> None:
    add_resume(conn, "v1", PROFILE_V1, "2026-06-01", "初版，仅基础技能")
    add_resume(conn, "v2", PROFILE_V2, "2026-07-01", "增补 SQL/Python/可视化/AB实验/指标体系")

    apps = [
        # 这两条预填「高 fit」用于演示交叉信号（模拟 LLM/人工精准评分），不被 heuristic 覆盖
        dict(platform="BOSS", company="示例科技", sector="互联网", role="数据分析师", role_type="中级",
             channel="主动沟通", applied_date="2026-07-01",
             source_url="https://example.com/jd/1",
             jd_text="要求 SQL、Python、数据可视化，3 年以上数据分析经验，能搭建指标体系。",
             hr_reply="", resume_version="v1", last_status="rejected", status_date="2026-07-05",
             fit_technical=82, fit_experience=80, fit_behavioral=70, fit_location="PASS",
             fit_career=85, fit_overall=80, job_quality=3, notes="技能不匹配（实际是 v1 没写全）"),
        dict(platform="BOSS", company="数据驱动公司", sector="互联网", role="数据分析师", role_type="中级",
             channel="内推", applied_date="2026-07-04",
             source_url="https://example.com/jd/4",
             jd_text="要求 SQL、Python、指标体系、AB 实验，2 年以上。",
             hr_reply="", resume_version="v2", last_status="rejected", status_date="2026-07-09",
             fit_technical=85, fit_experience=82, fit_behavioral=72, fit_location="PASS",
             fit_career=88, fit_overall=83, job_quality=4,
             notes="高 fit 却被拒——简历可能没讲清匹配点（重点信号）"),
        # 以下三条不预填 fit，交给 score.py heuristic 演示离线评分
        dict(platform="脉脉", company="某某金融", sector="金融", role="数据产品经理", role_type="高级",
             channel="猎头推荐", applied_date="2026-07-02",
             source_url="https://example.com/jd/2",
             jd_text="要求指标体系搭建、AB 实验设计、跨部门沟通，5 年以上。",
             hr_reply="", resume_version="v1", last_status="no_response",
             job_quality=4, notes="已读不回"),
        dict(platform="BOSS", company="成长型企业", sector="电商", role="运营专员", role_type="初级",
             channel="海投", applied_date="2026-07-03",
             source_url="https://example.com/jd/3",
             jd_text="要求活动策划、社群运营。",
             hr_reply="", resume_version="v2", last_status="interview", status_date="2026-07-10",
             job_quality=3, notes="进入面试"),
        dict(platform="脉脉", company="远方电商", sector="电商", role="高级运营专家", role_type="专家",
             channel="猎头推荐", applied_date="2026-07-05",
             source_url="https://example.com/jd/5",
             jd_text="要求 10 年电商全盘运营、带团队、海外经验。",
             hr_reply="", resume_version="v2", last_status="rejected", status_date="2026-07-08",
             job_quality=5, notes="明显超纲，低 fit 被拒意料之中"),
    ]
    for a in apps:
        company, role = a["company"], a["role"]
        a["archive_path"] = f"data/applications/{_archive_slug(company, role)}"
        add_application(conn, **a)
        # 归档 JD + outcome
        d = ROOT / "data" / "applications" / _archive_slug(company, role)
        d.mkdir(parents=True, exist_ok=True)
        (d / "job_posting.md").write_text(a.get("jd_text", ""), encoding="utf-8")
        (d / "outcome.md").write_text(
            f"# Outcome: {company} — {role}\n\n**Status:** {a['last_status']}\n\n## Notes\n{a.get('notes','')}\n",
            encoding="utf-8",
        )


def main() -> None:
    conn = init_db(DEFAULT_DB)
    # 清空旧示例，保证可重复跑
    conn.execute("DELETE FROM applications")
    conn.execute("DELETE FROM resumes")
    conn.commit()
    seed(conn)
    n = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    conn.close()
    print(f"✅ 已写入 {n} 条示例投递 + 2 版简历到 {DEFAULT_DB}")


if __name__ == "__main__":
    main()
