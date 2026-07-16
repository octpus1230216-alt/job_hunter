"""revise.py — 对照岗位修改简历（Drafter-Reviewer 双代理，借 MadsLorentzen apply.md）。

作用：针对被拒 / 已读不回的岗位，基于 JD 差距生成「修改后简历草稿」，闭环你最初的目标
（收集 → 分析 → 对照岗位修改）。

双通道 / 三模式：
  python revise.py --id 3 --mode export      # 打印「贴给 WorkBuddy」的 Drafter+Reviewer 提示词（免 key）
  python revise.py --id 3 --mode heuristic   # 本地规则草稿（免 key 可跑，产出建议段落 + 改写草稿）
  python revise.py --id 3 --mode llm         # LLM 起草 + LLM 独立审查（需 OPENAI_API_KEY）

产出：revised_resume.md 写到 data/applications/<company>_<role>/ 下（不覆盖原简历）。
原则：诚实不虚构，缺口明说，不为凑关键词编造经历。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from modules.store import (
    DEFAULT_DB, STRONG_SIGNAL, WEAK_SIGNAL, init_db, get_by_id, get_by_status,
    get_resume, get_latest_resume, _archive_slug,
)

ROOT = Path(__file__).resolve().parent


# ---------- 关键词抽取（与 score.py 同源，本地复用） ----------
def _tokens(text: str) -> set:
    text = re.sub(r"[\s，。、；：,.;:!！?？()（）\[\]【】\"'\"'/\\|]+", " ", text.lower())
    return {chunk for chunk in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text) if len(chunk) >= 2}


# ---------- 目标岗位选取 ----------
def _targets(conn, args) -> list:
    if args.id:
        row = get_by_id(conn, args.id)
        return [row] if row else []
    # 默认：所有 rejected / no_response 且记录了简历版本的
    rows = get_by_status(conn, list(STRONG_SIGNAL | WEAK_SIGNAL))
    return [r for r in rows if r["resume_version"]]


# ----------  heuristic 草稿（免 key 可跑） ----------
def heuristic_revise(jd_text: str, resume_text: str) -> dict:
    """本地规则：找出 JD 有、简历没有的关键词，生成「建议补充」草稿。"""
    jd, rs = _tokens(jd_text or ""), _tokens(resume_text or "")
    missing = sorted(jd - rs)
    # 过滤掉太泛的词
    filler = {"以上", "经验", "能力", "要求", "优先", "相关", "以上经验", "岗位职责", "任职"}
    missing = [m for m in missing if m not in filler][:12]
    skills_line = "、".join(missing) if missing else "（关键词基本已覆盖）"
    draft = (
        f"# 修改后简历草稿（启发式建议，待你/WorkBuddy 润色）\n\n"
        f"## 建议补充的技能/关键词（JD 有、当前简历缺）\n- {skills_line}\n\n"
        f"## 改写建议\n"
        f"- 在「技能」区补上上述关键词，并配一句话证明你会用（不要只列名词）。\n"
        f"- 在「经历」里把与 JD 重合的项目量化（数字、结果），对齐 JD 看重的能力。\n"
        f"- 诚实优先：缺的能力明说「学习中/可迁移」，不编造经历。\n"
    )
    return {"missing": missing, "draft_markdown": draft}


# ----------  LLM 双代理（起草 + 审查） ----------
def _llm_client():
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise SystemExit("未安装 openai，请: pip install openai（或改用 --mode export / --mode heuristic）")
    import os
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _chat(client, model: str, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def llm_revise(company: str, role: str, jd_text: str, resume_text: str, model: str) -> dict:
    """Drafter 起草 → Reviewer 独立审查 → 返回最终改写草稿。"""
    client = _llm_client()
    # Drafter
    drafter_prompt = (
        f"你是简历优化助手。基于下面岗位 JD 和候选人当前简历，产出「修改后简历」JSON。\n"
        f"岗位：{company} — {role}\n\nJD：\n{jd_text}\n\n当前简历：\n{resume_text}\n\n"
        "只输出 JSON：{\"revised_resume\": \"<完整修改后简历文本，诚实不虚构，缺的能力明说>\"}"
    )
    draft_json = json.loads(_chat(client, model, drafter_prompt))
    draft_text = draft_json.get("revised_resume", "")
    # Reviewer（独立上下文，挑刺）
    reviewer_prompt = (
        f"你是资深招聘经理，独立审查这份修改后简历是否真的匹配岗位。\n"
        f"岗位：{company} — {role}\n\nJD：\n{jd_text}\n\n修改后简历：\n{draft_text}\n\n"
        "只输出 JSON：{\"critique\": \"<挑刺：漏了啥关键词/哪段弱/有无套话>\", "
        "\"improved_resume\": \"<根据 critique 再改一版的简历文本>\"}"
    )
    rev_json = json.loads(_chat(client, model, reviewer_prompt))
    return {"draft": draft_text, "critique": rev_json.get("critique", ""),
            "final": rev_json.get("improved_resume", draft_text)}


# ----------  export 模式：贴给 WorkBuddy 的提示词 ----------
def build_workbuddy_prompt(company, role, jd_text, resume_text) -> str:
    return (
        f"请作为简历优化助手，对照下面岗位 JD 修改我的简历（诚实不虚构）。\n\n"
        f"岗位：{company} — {role}\n\n"
        f"JD：\n{jd_text}\n\n"
        f"我投递时用的简历：\n{resume_text}\n\n"
        "请分两步输出：\n"
        "1) 差距分析：JD 看重但简历缺的技能/关键词、经历表述短板；\n"
        "2) 修改后简历草稿：可直接替换的技能补充 + 经历重写段落（诚实，不编造）。\n"
        "（可选）再以「招聘经理」视角审查一遍这份草稿，挑刺并给出终稿。"
    )


# ---------- 落盘 ----------
def write_revised(company: str, role: str, content: str) -> str:
    d = ROOT / "data" / "applications" / _archive_slug(company, role)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "revised_resume.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


def main() -> None:
    ap = argparse.ArgumentParser(description="revise.py — 对照岗位修改简历")
    ap.add_argument("--id", type=int, help="指定投递 id")
    ap.add_argument("--mode", choices=["export", "heuristic", "llm"], default="export")
    ap.add_argument("--model", default="gpt-4o-mini", help="llm 模式用的模型")
    args = ap.parse_args()

    conn = init_db()
    targets = _targets(conn, args)
    if not targets:
        print("没有可改的岗位（用 collect 录入带 resume_version 的 rejected/no_response 记录）。")
        conn.close()
        return

    for r in targets:
        company, role = r["company"], r["role"]
        version = r["resume_version"] or ""
        # 未记录 resume_version 时，回退到最新简历（通常是 FR9 上传的原简历）作为基准
        resume_row = get_resume(conn, version) if version else get_latest_resume(conn)
        resume_text = resume_row["text"] if resume_row else "（未记录该版本简历，可先用 ingest_resume.py 上传原简历）"
        jd = r["jd_text"] or ""

        print(f"\n=== {company} — {role}（状态 {r['last_status']}，简历 {version}）===")
        if args.mode == "export":
            print("把下面整段贴给 WorkBuddy：\n")
            print(build_workbuddy_prompt(company, role, jd, resume_text))
            continue
        if args.mode == "heuristic":
            res = heuristic_revise(jd, resume_text)
            out = (
                f"# {company} — {role} 修改草稿（heuristic）\n\n"
                f"> 来源 JD：{jd}\n\n" + res["draft_markdown"]
            )
            p = write_revised(company, role, out)
            print(f"✅ 草稿已写入 {p}")
            continue
        if args.mode == "llm":
            res = llm_revise(company, role, jd, resume_text, args.model)
            out = (
                f"# {company} — {role} 修改后简历（Drafter-Reviewer）\n\n"
                f"## 起草稿\n{res['draft']}\n\n"
                f"## 审查挑刺\n{res['critique']}\n\n"
                f"## 终稿\n{res['final']}\n"
            )
            p = write_revised(company, role, out)
            print(f"✅ 终稿已写入 {p}")
            continue

    conn.close()


if __name__ == "__main__":
    main()
