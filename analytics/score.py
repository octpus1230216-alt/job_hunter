"""score.py — 五维岗位匹配度评分（借 MadsLorentzen 04-job-evaluation.md）。

五维：技能 / 经验 / 文化 / 地点(PASS/FAIL) / 职业契合，各 0-100，加权(技30/经25/文15/职30)出 fit_overall。
双通道：
  python score.py --all                     # 离线 heuristic 评分（零依赖，可跑）
  python score.py --id 3 --mode llm         # LLM 直连（需 OPENAI_API_KEY，可选依赖 openai）
  python score.py --id 3 --export-prompt    # 打印「贴给 WorkBuddy」的评分提示词（免 key）

写入 store.update_fit()。job_quality(岗位本身好坏) 为手动字段，本模块不评。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from modules.store import (
    DEFAULT_DB, WEIGHTS, init_db, get_all, get_by_id, get_latest_resume, get_unscored, update_fit,
)

ROOT = Path(__file__).resolve().parent

# 五维权重（与 MadsLorentzen 对齐）
NUM_DIMS = ["fit_technical", "fit_experience", "fit_behavioral", "fit_career"]
RUBRIC = """五维匹配度评分（各 0-100）：
1. Technical Skills（技能）：必需要求与候选人能力的重合度
2. Experience Match（经验）：工作履历与该岗位的匹配
3. Behavioral/Culture Fit（文化）：团队文化/行为风格契合
4. Career Alignment（职业）：是否推进职业目标、任务是否让人有动力
5. Location & Logistics（地点）：PASS（通勤/远程可接受）/ FAIL（需异地，deal-breaker）/ FLAG（频繁出差，待确认）
加权：技能30% 经验25% 文化15% 职业30%，地点不参与加权。
总评 = 四舍五入(技能*0.3 + 经验*0.25 + 文化*0.15 + 职业*0.3)。"""


def _tokens(text: str) -> set:
    """极简中文/英文关键词抽取：去标点、小写，按非字母数字切分，保留长度>=2 的片段。"""
    text = re.sub(r"[\s，。、；：,.;:!！?？()（）\[\]【】\"'\"'/\\|]+", " ", text.lower())
    toks = set()
    for chunk in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text):
        if len(chunk) >= 2:
            toks.add(chunk)
    return toks


def heuristic_score(jd_text: str, profile_text: str) -> dict:
    """离线启发式评分：以 JD 与简历的关键词重叠率作为代理信号。

    说明：这是无 LLM 时的基线，仅让管道可跑；真实评分请用 --mode llm 或 --export-prompt。
    文化/地点无法从文本推断，给中性默认分。
    """
    if not jd_text or not profile_text:
        return {"fit_technical": 50, "fit_experience": 50, "fit_behavioral": 55,
                "fit_location": "PASS", "fit_career": 50, "fit_overall": 51}
    jd = _tokens(jd_text)
    pf = _tokens(profile_text)
    if not jd:
        overlap = 0.0
    else:
        overlap = len(jd & pf) / len(jd)
    # 重叠率映射到 30-95 区间，避免极端
    base = int(30 + overlap * 65)
    technical = min(95, base + 5)
    experience = min(95, base)
    career = min(95, base + 3)
    behavioral = 55  # 文本不可推断，中性
    overall = round(technical * WEIGHTS["fit_technical"] + experience * WEIGHTS["fit_experience"]
                    + behavioral * WEIGHTS["fit_behavioral"] + career * WEIGHTS["fit_career"])
    return {"technical": technical, "experience": experience,
            "behavioral": behavioral, "location": "PASS",
            "career": career, "overall": overall}


def build_llm_prompt(company: str, role: str, jd_text: str, profile_text: str) -> str:
    return (
        f"请为以下岗位做五维匹配度评分。\n\n岗位：{company} — {role}\n\n"
        f"JD：\n{jd_text}\n\n候选人档案：\n{profile_text}\n\n"
        f"{RUBRIC}\n\n"
        "只输出 JSON："
        '{"fit_technical":0-100,"fit_experience":0-100,"fit_behavioral":0-100,'
        '"fit_location":"PASS/FAIL/FLAG","fit_career":0-100}'
    )


def score_with_llm(app_row, profile_text: str) -> dict:
    """直连 LLM（OpenAI 兼容）。需环境变量 OPENAI_API_KEY，且 pip install openai。"""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise SystemExit("未安装 openai，请先: pip install openai （或改用默认 heuristic / --export-prompt）")
    import os
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = build_llm_prompt(app_row["company"], app_row["role"], app_row["jd_text"] or "", profile_text)
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    technical = int(data["fit_technical"]); experience = int(data["fit_experience"])
    behavioral = int(data["fit_behavioral"]); career = int(data["fit_career"])
    overall = round(technical * WEIGHTS["fit_technical"] + experience * WEIGHTS["fit_experience"]
                    + behavioral * WEIGHTS["fit_behavioral"] + career * WEIGHTS["fit_career"])
    return {"technical": technical, "experience": experience,
            "behavioral": behavioral, "location": data.get("fit_location", "PASS"),
            "career": career, "overall": overall}


def _profile_text(conn, profile_file: str) -> str:
    if profile_file:
        p = Path(profile_file)
        if p.exists():
            return p.read_text(encoding="utf-8")
    row = get_latest_resume(conn)
    return row["text"] if row else ""


def score_one(conn, app_row, mode: str, profile_text: str) -> dict:
    if mode == "llm":
        return score_with_llm(app_row, profile_text)
    if mode == "heuristic":
        return heuristic_score(app_row["jd_text"] or "", profile_text)
    raise ValueError(mode)


def main() -> None:
    ap = argparse.ArgumentParser(description="score.py — 五维匹配度评分")
    ap.add_argument("--id", type=int, help="指定投递 id")
    ap.add_argument("--all", action="store_true", help="对所有有 JD 的记录评分")
    ap.add_argument("--mode", choices=["heuristic", "llm"], default="heuristic")
    ap.add_argument("--export-prompt", action="store_true", help="打印贴给 WorkBuddy 的评分提示词（免 key）")
    ap.add_argument("--profile", default="", help="候选人档案文件（默认取最新简历）")
    args = ap.parse_args()

    conn = init_db()
    profile_text = _profile_text(conn, args.profile)

    targets = []
    if args.id:
        row = get_by_id(conn, args.id)
        if row:
            targets = [row]
    elif args.all:
        # 默认只评 fit_overall 为空的记录，避免 heuristic 覆盖 LLM/人工预填的精准分
        targets = get_unscored(conn)
        if not targets:
            print("没有待评分的记录（已有 fit_overall 的不重评；用 --id 强制单条）。")
            conn.close()
            return

    if not targets:
        print("没有可评分的记录（用 collect 录入带 JD 的投递，或用 --id）。")
        conn.close()
        return

    for row in targets:
        if args.export_prompt:
            print(f"--- id={row['id']} {row['company']} — {row['role']} ---")
            print(build_llm_prompt(row["company"], row["role"], row["jd_text"] or "", profile_text))
            print()
            continue
        res = score_one(conn, row, args.mode, profile_text)
        update_fit(conn, row["id"], **res)
        print(f"✅ id={row['id']} {row['company']} — {row['role']}: "
              f"技{res['technical']} 经{res['experience']} 文{res['behavioral']} "
              f"职{res['career']} 地点{res['location']} => 总评 {res['overall']}")
    conn.close()


if __name__ == "__main__":
    main()
