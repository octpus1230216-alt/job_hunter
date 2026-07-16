"""collect.py — 多源录入「我的投递结果」（双通道）。

用法：
  python collect.py add                        # 交互式逐条录入
  python collect.py import-csv <file.csv>      # 批量导入（见 csv_template/）
  python collect.py image <截图.png>           # 截图 → 打印「贴给 WorkBuddy」的提示词（OCR 免 key）
  python collect.py image --json <回填.json>   # 把 WorkBuddy 返回的 JSON 草稿导入库
  python collect.py scraper                     # 预留爬虫接口（暂不实现，仅展示扩展位）

设计：每种输入 = 一个适配器，统一产出字段 dict，交给 store.add_application 入库。
对应 v3 方案「核心四件套」第 2 项；截图 OCR 走 WorkBuddy 通道（免 API key）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from modules.store import (
    DEFAULT_DB, add_application, init_db, STATUS_ENUM, _archive_slug,
)

ROOT = Path(__file__).resolve().parent


# ---------- 归档（借 MadsLorentzen documents/applications/<company>_<role>/outcome.md） ----------
def write_archive(company: str, role: str, status: str, jd_text: str = "", notes: str = "") -> str:
    slug = _archive_slug(company, role)
    d = ROOT / "data" / "applications" / slug
    d.mkdir(parents=True, exist_ok=True)
    md = d / "outcome.md"
    if not md.exists():
        md.write_text(
            f"# Outcome: {company} — {role}\n\n"
            f"**Status:** {status}\n\n"
            f"## Interview stages reached\n"
            f"- [ ] Phone screen\n- [ ] Technical interview\n"
            f"- [ ] Case interview\n- [ ] Final round\n- [ ] Offer received\n\n"
            f"## Notes\n{notes}\n",
            encoding="utf-8",
        )
    # JD 单独存一份，供 analyzer 做差距分析
    jd_file = d / "job_posting.md"
    if jd_text and not jd_file.exists():
        jd_file.write_text(jd_text, encoding="utf-8")
    return f"data/applications/{slug}"


# ---------- 适配器 1：手动交互 ----------
def cmd_add() -> None:
    print("=== 录入一条投递结果（回车留空跳过）===")
    fields = {}
    fields["platform"] = input("平台 (BOSS/脉脉/其他): ") or ""
    fields["company"] = input("公司: ") or ""
    fields["sector"] = input("行业: ") or ""
    fields["role"] = input("岗位: ") or ""
    fields["role_type"] = input("级别 (实习/初级/中级/高级/专家): ") or ""
    fields["channel"] = input("渠道: ") or ""
    fields["applied_date"] = input("投递日期 (YYYY-MM-DD): ") or ""
    fields["source_url"] = input("JD 链接: ") or ""
    fields["jd_text"] = input("JD 关键段落 (可粘贴): ") or ""
    fields["hr_reply"] = input("HR 原话 (可选): ") or ""
    fields["resume_version"] = input("用的简历版本 (如 v1/v2): ") or ""
    print("可选状态:", ", ".join(STATUS_ENUM))
    print("  · prospect = 新岗位待分析（先评估、暂不投递，目标 A 入口）")
    fields["last_status"] = input("结果状态 (prospect/applied/rejected/...): ") or "applied"
    fields["status_date"] = input("状态更新日期 (YYYY-MM-DD): ") or ""
    jq = input("岗位本身好坏 job_quality (1-5，可选): ") or ""
    fields["job_quality"] = int(jq) if jq.isdigit() else None
    fields["notes"] = input("备注: ") or ""
    if not fields["company"] or not fields["role"]:
        print("公司/岗位为必填，已取消。")
        return
    fields["archive_path"] = write_archive(
        fields["company"], fields["role"], fields["last_status"], fields["jd_text"], fields["notes"]
    )
    conn = init_db()
    aid = add_application(conn, **fields)
    conn.close()
    print(f"✅ 已入库 id={aid}，归档于 {fields['archive_path']}")


# ---------- 适配器 2：CSV 批量 ----------
def cmd_import_csv(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"文件不存在: {path}")
        return
    conn = init_db()
    n = 0
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {k: (v if v != "" else None) for k, v in row.items()}
            if row.get("job_quality") and str(row["job_quality"]).isdigit():
                row["job_quality"] = int(row["job_quality"])
            if not row.get("company") or not row.get("role"):
                continue
            row["archive_path"] = write_archive(
                row["company"], row["role"], row.get("last_status") or "applied",
                row.get("jd_text") or "", row.get("notes") or "",
            )
            add_application(conn, **row)
            n += 1
    conn.close()
    print(f"✅ 已导入 {n} 条")


# ---------- 适配器 3：截图 OCR（双通道：WorkBuddy 提示词 / JSON 回填） ----------
IMAGE_PROMPT = """请把这张招聘/聊天截图里的投递信息抽成下面的 JSON 结构（中文），只输出 JSON：

{
  "platform": "BOSS/脉脉/其他",
  "company": "公司名",
  "sector": "行业（如未知留空）",
  "role": "岗位名",
  "role_type": "实习/初级/中级/高级/专家（如未知留空）",
  "channel": "渠道（如未知留空）",
  "applied_date": "YYYY-MM-DD（如未知留空）",
  "source_url": "JD 链接（如未知留空）",
  "jd_text": "JD 关键段落，尽量原文",
  "hr_reply": "HR 原话（如未知留空）",
  "resume_version": "用的简历版本（如未知留空）",
  "last_status": "prospect(新岗位待分析)/applied/rejected/no_response/interview/offer 之一",
  "status_date": "YYYY-MM-DD（如未知留空）",
  "job_quality": "1-5 整数或留空",
  "notes": "备注"
}

注意：
- rejected = 明确不合适；no_response = 已读不回（沉默）；interview = 进入面试。
- 诚实抽取，缺失字段填空字符串，不要编造。
- 只要 JSON，不要解释。"""


def cmd_image(image_path: str = "", json_path: str = "") -> None:
    if json_path:
        p = Path(json_path)
        if not p.exists():
            print(f"JSON 文件不存在: {json_path}")
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        if not data.get("company") or not data.get("role"):
            print("JSON 缺少 company/role，已取消。")
            return
        jq = data.get("job_quality")
        data["job_quality"] = int(jq) if isinstance(jq, (int, float)) else None
        data["archive_path"] = write_archive(
            data["company"], data["role"], data.get("last_status") or "applied",
            data.get("jd_text") or "", data.get("notes") or "",
        )
        conn = init_db()
        aid = add_application(conn, **data)
        conn.close()
        print(f"✅ 截图草稿已入库 id={aid}")
        return
    # 没给 JSON → 打印提示词，让用户把截图贴给 WorkBuddy
    if image_path:
        print(f"[待识别截图] {image_path}\n")
    print("=" * 60)
    print("把这张截图贴给 WorkBuddy，并把下面提示词一起发：")
    print("=" * 60)
    print(IMAGE_PROMPT)
    print("=" * 60)
    print("WorkBuddy 会回你一段 JSON。把它存成 result.json，再运行：")
    print(f"  python collect.py image --json result.json")
    print("（也可直接把 JSON 贴到终端，本工具后续可加 --paste 支持。）")


# ---------- 适配器 4：爬虫预留接口 ----------
class ScraperAdapter:
    """预留：未来接 BOSS/脉脉 合规数据源（平台导出 / 可抓站点）即插即用。

    实现 fetch() -> list[dict]，字段与 add_application 一致即可。
    当前不实现具体爬取（BOSS/脉脉 强反爬 + 合规风险，见 v3 方案）。
    """

    def fetch(self) -> list[dict]:
        raise NotImplementedError("爬虫接口预留：未接入具体数据源。未来做成 portal skill 即插即用。")


def cmd_scraper() -> None:
    print("=== 爬虫接口（预留，暂不实现）===")
    print("设计：每个数据源 = 一个 portal adapter，实现 fetch() -> list[dict]。")
    print("BOSS 直聘 / 脉脉 当前不可直接爬（移动端+登录+强反爬，且有合规风险）。")
    print("未来接入方式（对齐 MadsLorentzen 可插拔 portal 架构）：")
    print("  connectors/boss_portal.py  /  connectors/maimai_portal.py")
    print("  fetch() 只抓【你自己的投递记录】，遵守平台条款，不碰他人数据。")
    try:
        ScraperAdapter().fetch()
    except NotImplementedError as e:
        print(f"⏸  {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="collect.py — 多源录入我的投递结果")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("add", help="交互式逐条录入")
    p_csv = sub.add_parser("import-csv", help="批量导入 CSV")
    p_csv.add_argument("file")
    p_img = sub.add_parser("image", help="截图 OCR（双通道）")
    p_img.add_argument("image", nargs="?", default="")
    p_img.add_argument("--json", default="", help="WorkBuddy 返回的 JSON 草稿路径")
    sub.add_parser("scraper", help="预留爬虫接口")
    args = ap.parse_args()

    if args.cmd == "add":
        cmd_add()
    elif args.cmd == "import-csv":
        cmd_import_csv(args.file)
    elif args.cmd == "image":
        cmd_image(args.image, args.json)
    elif args.cmd == "scraper":
        cmd_scraper()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
