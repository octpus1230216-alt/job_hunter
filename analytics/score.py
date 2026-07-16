"""score.py — 七维岗位匹配度评分（在 MadsLorentzen 五维基础上扩展）。

七维：技能 / 经验 / 文化 / 职业 / 背景契合 / 薪资匹配 / 层级匹配，各 0-100，
加权(技0.24/经0.20/文0.12/职0.24/背0.12/薪0.04/级0.04)出 fit_overall；地点(PASS/FAIL/FLAG)不参与加权。
额外：competition_level（公司竞争力档位，不计入 fit）+ realistic_prob（= fit_overall × 竞争力因子，真实命中率估计）。
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
    DEFAULT_DB, WEIGHTS, init_db, get_all, get_by_id, get_latest_resume, get_resume,
    get_unscored, update_fit, infer_competition, COMPETITION_FACTOR,
)

ROOT = Path(__file__).resolve().parent

# 七维权重（与 MadsLorentzen 五维对齐，扩展背景/薪资/层级）
RUBRIC = """七维匹配度评分（各 0-100）：
1. Technical Skills（技能）：必需要求与候选人能力的重合度
2. Experience Match（经验）：工作履历与该岗位的匹配
3. Behavioral/Culture Fit（文化）：团队文化/行为风格契合
4. Career Alignment（职业）：是否推进职业目标、任务是否让人有动力
5. Background Fit（背景/领域契合）：行业/领域/项目背景与岗位的隐性契合（如政府/国企背景契合体制内岗、C 端背景契合消费级岗）
6. Salary Match（薪资期望匹配）：候选人期望薪资与岗位薪资区间的匹配（期望远低于岗位上限易触发初级筛选；远高于则无竞争力）
7. Level Match（目标层级匹配）：岗位级别（初级/中级/资深/专家）与候选人资历的匹配
地点（Location）：单独 PASS / FAIL / FLAG，不参与加权。
公司竞争力（competition_level）：顶级厂/一线大厂/中厂B轮C轮/初创天使轮/未知——同一 fit 在顶级厂真实命中率更低，由 realistic_prob = fit_overall × 竞争力因子 体现。
总评 = 四舍五入(技能*0.24 + 经验*0.20 + 文化*0.12 + 职业*0.24 + 背景*0.12 + 薪资*0.04 + 层级*0.04)。"""


def _tokens(text: str) -> set:
    """极简中文/英文关键词抽取：去标点、小写，按非字母数字切分，保留长度>=2 的片段。"""
    text = re.sub(r"[\s，。、；：,.;:!！?？()（）\[\]【】\"'\"'/\\|]+", " ", text.lower())
    toks = set()
    for chunk in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text):
        if len(chunk) >= 2:
            toks.add(chunk)
    return toks


def _parse_salary(text: str):
    """从文本抽 'aK-bK' / 'a万-b万' / 'a-bk' 区间，返回 (low, high) 千元；无则返回 None。"""
    if not text:
        return None
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*[kK万]", text)]
    if not nums:
        return None
    if len(nums) >= 2:
        return min(nums), max(nums)
    return nums[0], nums[0]


def _parse_years(text: str):
    """抽 'X-Y年' 或 'X年以上' 经验要求，返回 (low, high) 年；无则返回 None。"""
    if not text:
        return None
    m = re.findall(r"(\d+)\s*-\s*(\d+)\s*年", text)
    if m:
        return int(m[0][0]), int(m[0][1])
    m2 = re.findall(r"(\d+)\s*年(以上|及|经验|以|相关)", text)
    if m2:
        lo = int(m2[0][0])
        return lo, lo + 3
    return None


def heuristic_score(jd_text: str, profile_text: str, company: str = "") -> dict:
    """离线启发式评分（七维 + 竞争力 + 真实概率）。

    说明：无 LLM 时的基线，仅让管道可跑；真实评分请用 --mode llm 或 --export-prompt。
    文化/背景无法从文本可靠推断，给中性默认分；薪资/层级用简单规则解析。
    """
    comp = infer_competition(company)
    if not jd_text or not profile_text:
        return {"technical": 50, "experience": 50, "behavioral": 55, "career": 50,
                "background": 50, "salary": 60, "level": 60, "location": "PASS",
                "competition": comp, "overall": 51,
                "realistic": round(51 * COMPETITION_FACTOR[comp])}
    jd = _tokens(jd_text)
    pf = _tokens(profile_text)
    overlap = len(jd & pf) / len(jd) if jd else 0.0
    # 重叠率映射到 30-95 区间，避免极端
    base = int(30 + overlap * 65)
    technical = min(95, base + 5)
    experience = min(95, base)
    career = min(95, base + 3)
    behavioral = 55  # 文本不可推断，中性
    background = min(95, base - 3)  # 文本不可推断，略低于技能代理
    # 薪资匹配：JD 区间上限 vs 简历期望
    jd_sal = _parse_salary(jd_text)
    exp_sal = _parse_salary(profile_text)
    if jd_sal and exp_sal:
        j_high = jd_sal[1]
        e_high = exp_sal[1]
        if e_high <= j_high:
            salary = 80
        elif e_high <= j_high * 1.3:
            salary = 55
        else:
            salary = 25
    else:
        salary = 60  # 缺信息，中性
    # 层级匹配：JD 经验要求 vs 简历年限
    jd_years = _parse_years(jd_text)
    cv_years = _parse_years(profile_text)
    if jd_years and cv_years:
        if cv_years[0] >= jd_years[0]:
            level = 75 if cv_years[1] <= (jd_years[1] or jd_years[0] + 3) else 45
        else:
            level = 35  # 资历不足
    else:
        level = 60
    overall = round(technical * WEIGHTS["fit_technical"] + experience * WEIGHTS["fit_experience"]
                    + behavioral * WEIGHTS["fit_behavioral"] + career * WEIGHTS["fit_career"]
                    + background * WEIGHTS["fit_background"] + salary * WEIGHTS["fit_salary"]
                    + level * WEIGHTS["fit_level"])
    realistic = round(overall * COMPETITION_FACTOR[comp])
    return {"technical": technical, "experience": experience, "behavioral": behavioral,
            "career": career, "background": background, "salary": salary, "level": level,
            "location": "PASS", "competition": comp, "overall": overall, "realistic": realistic}


def build_llm_prompt(company: str, role: str, jd_text: str, profile_text: str) -> str:
    return (
        f"请为以下岗位做七维匹配度评分，并判定公司竞争力。\n\n岗位：{company} — {role}\n\n"
        f"JD：\n{jd_text}\n\n候选人档案：\n{profile_text}\n\n"
        f"{RUBRIC}\n\n"
        "只输出 JSON："
        '{"fit_technical":0-100,"fit_experience":0-100,"fit_behavioral":0-100,'
        '"fit_career":0-100,"fit_background":0-100,"fit_salary":0-100,"fit_level":0-100,'
        '"fit_location":"PASS/FAIL/FLAG",'
        '"competition_level":"顶级厂/一线大厂/中厂B轮C轮/初创天使轮/未知",'
        '"realistic_prob":0-100}'
        "（realistic_prob 由你依据 fit 与公司竞争力综合给出，顶级厂显著压低）"
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
    background = int(data.get("fit_background", 50)); salary = int(data.get("fit_salary", 60))
    level = int(data.get("fit_level", 60))
    overall = round(technical * WEIGHTS["fit_technical"] + experience * WEIGHTS["fit_experience"]
                    + behavioral * WEIGHTS["fit_behavioral"] + career * WEIGHTS["fit_career"]
                    + background * WEIGHTS["fit_background"] + salary * WEIGHTS["fit_salary"]
                    + level * WEIGHTS["fit_level"])
    competition = data.get("competition_level") or infer_competition(app_row["company"])
    realistic = int(data.get("realistic_prob", round(overall * COMPETITION_FACTOR.get(competition, 0.6))))
    return {"technical": technical, "experience": experience, "behavioral": behavioral,
            "career": career, "background": background, "salary": salary, "level": level,
            "location": data.get("fit_location", "PASS"), "competition": competition,
            "overall": overall, "realistic": realistic}


def _profile_text(conn, profile_file: str) -> str:
    if profile_file:
        p = Path(profile_file)
        if p.exists():
            return p.read_text(encoding="utf-8")
    row = get_latest_resume(conn)
    return row["text"] if row else ""


def _profile_for_app(conn, app_row, profile_file: str = "") -> str:
    """优先用该投递记录的 resume_version 文本（A/B 对照准确性）；
    否则回退到 --profile 指定文件，再回退最新简历。"""
    version = app_row.get("resume_version") or ""
    if version:
        r = get_resume(conn, version)
        if r and r["text"]:
            return r["text"]
    return _profile_text(conn, profile_file)


def score_one(conn, app_row, mode: str, profile_file: str = "") -> dict:
    # 用该投递实际用的简历版本做对照（A/B 准确性）
    profile_text = _profile_for_app(conn, app_row, profile_file)
    if mode == "llm":
        return score_with_llm(app_row, profile_text)
    if mode == "heuristic":
        return heuristic_score(app_row["jd_text"] or "", profile_text, app_row.get("company", ""))
    raise ValueError(mode)


def main() -> None:
    ap = argparse.ArgumentParser(description="score.py — 七维匹配度评分（+公司竞争力/真实概率）")
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
        res = score_one(conn, row, args.mode, args.profile)
        update_fit(conn, row["id"], **res)
        print(f"✅ id={row['id']} {row['company']} — {row['role']}: "
              f"技{res['technical']} 经{res['experience']} 文{res['behavioral']} "
              f"职{res['career']} 背{res['background']} 薪{res['salary']} 级{res['level']} "
              f"地点{res['location']} 竞争[{res['competition']}] => 总评 {res['overall']} / 真实 {res['realistic']}")
    conn.close()


if __name__ == "__main__":
    main()
