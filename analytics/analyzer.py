"""analyzer.py — 复盘分析（核心四件套第 4 项）。

输出：
  1) 基础统计：状态 / 平台 / 级别 / 行业 占比看板
  2) fit×outcome 交叉：高亮「高 fit + 不合适/已读不回」—— 这才是最该深挖的信号
  3) JD 差距分析：对 rejected/no_response 岗位，拉 JD + 当时简历版本，产差距清单
     - 双通道：默认打印「贴给 WorkBuddy」提示词（免 key）；--mode llm 直连（需 key）

原则（借两库）：诚实不虚构；已读不回=弱信号，不据此大改简历。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from modules.store import (
    DEFAULT_DB, STRONG_SIGNAL, WEAK_SIGNAL, init_db, get_all, get_by_status,
    get_resume, count_by, fit_outcome_cross, resume_ab,
)

ROOT = Path(__file__).resolve().parent


def _print_stats(conn) -> str:
    lines = ["## 一、基础统计", "",
             "> 本看板仅统计真实投递结果（已排除 `prospect` 待分析岗位）。", ""]
    for col, label in [("last_status", "结果状态"), ("platform", "平台"),
                       ("role_type", "级别"), ("sector", "行业")]:
        lines.append(f"### 按{label}")
        for k, n in count_by(conn, col):
            lines.append(f"- {k or '(空)'}: {n}")
        lines.append("")
    return "\n".join(lines)


def _print_cross(conn) -> str:
    lines = ["## 二、fit × outcome 交叉分析", ""]
    lines.append("| fit 分档 | 状态 | 数量 | 信号 |")
    lines.append("|---|---|---|---|")
    for r in fit_outcome_cross(conn):
        band, status, n = r["fit_band"], r["last_status"], r["n"]
        if status in STRONG_SIGNAL and band.startswith(("Strong", "Good")):
            signal = "⚠️ 高匹配却被拒：简历没讲清匹配点"
        elif status in WEAK_SIGNAL and band.startswith(("Strong", "Good")):
            signal = "⚠️ 高匹配却沉默：可能是时机/海投量，别急着大改"
        elif status in STRONG_SIGNAL:
            signal = "低匹配被拒：意料之中"
        else:
            signal = ""
        lines.append(f"| {band} | {status} | {n} | {signal} |")
    lines.append("")
    return "\n".join(lines)


def _print_ab(conn) -> str:
    rows = resume_ab(conn)
    if not rows:
        return "## 四、简历版本 A/B 回复率\n\n（暂无记录 resume_version 的投递，无法对比）"
    lines = ["## 四、简历版本 A/B 回复率", "",
             "> 回复率 = 进入面试及以上(正反馈)的岗位数 / 该版本总投递数。",
             "> 用来判断「改简历有没有用」。", "",
             "| 简历版本 | 投递数 | 正反馈 | 回复率 |", "|---|---|---|---|"]
    rates = {}
    for r in rows:
        n = r["n"]; pos = r["positive"] or 0
        rate = round(pos / n * 100) if n else 0
        rates[r["resume_version"]] = rate
        lines.append(f"| {r['resume_version']} | {n} | {pos} | {rate}% |")
    lines.append("")
    # 对比相邻版本
    versions = list(rates.keys())
    if len(versions) >= 2:
        old_v, new_v = versions[0], versions[-1]
        delta = rates[new_v] - rates[old_v]
        verdict = ("📈 新版回复率更高，改法有效" if delta > 0
                   else "📉 新版回复率更低，需复盘改法" if delta < 0
                   else "➖ 两版回复率持平")
        lines.append(f"**{old_v} → {new_v}：回复率 {rates[old_v]}% → {rates[new_v]}%（{delta:+}pp）{verdict}**")
    return "\n".join(lines)


GAP_PROMPT = """下面是我被拒/已读不回的岗位 JD，以及我投递时用的简历版本正文。
请做「差距分析」并给「可落地的简历修改建议」（诚实不虚构，缺的能力就明说，不要编造）：

对每个岗位输出：
1. 岗位与我的简历匹配度判断
2. 缺失的技能/关键词（JD 有、简历没有的）
3. 经历表述上的短板（JD 看重、简历没讲清的）
4. 可直接替换的简历段落建议（技能补充 / 经历重写 / 关键词植入）

注意：已读不回是弱信号，不要据此大改简历；重点看明确「不合适」的岗位。"""


def _gap_section(conn, mode: str) -> str:
    rejected = get_by_status(conn, list(STRONG_SIGNAL | WEAK_SIGNAL))
    if not rejected:
        return "## 三、JD 差距分析\n\n（暂无 rejected/no_response 记录）"
    if mode == "llm":
        return "## 三、JD 差距分析\n\n（--mode llm 需在 analyzer 内接入 LLM；本版用 --export-prompt 走 WorkBuddy 通道）"
    # 默认：导出提示词贴 WorkBuddy
    lines = ["## 三、JD 差距分析（贴给 WorkBuddy）", "",
             "把下面整段（含各岗位 JD 与对应简历）贴给 WorkBuddy：", "",
             "```", GAP_PROMPT, ""]
    for r in rejected:
        version = r["resume_version"] or ""
        resume_row = get_resume(conn, version) if version else None
        resume_text = resume_row["text"] if resume_row else "（未记录该版本简历，可手动补充）"
        lines.append(f"### 岗位：{r['company']} — {r['role']}（状态：{r['last_status']}，fit_overall={r['fit_overall']}）")
        lines.append(f"JD：\n{r['jd_text'] or '(无)'}")
        lines.append(f"用的简历版本：{version}")
        lines.append(f"简历正文：\n{resume_text}")
        lines.append("")
    lines.append("```")
    return "\n".join(lines)


def build_report(conn, mode: str) -> str:
    return "\n\n".join([
        "# 求职复盘分析报告",
        _print_stats(conn),
        _print_cross(conn),
        _gap_section(conn, mode),
        _print_ab(conn),
        "---\n*诚实不虚构；已读不回=弱信号，不据此大改简历。*",
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description="analyzer.py — 复盘分析")
    ap.add_argument("--mode", choices=["export", "llm"], default="export",
                    help="export=打印贴给 WorkBuddy 的提示词（免 key，默认）；llm=直连（预留）")
    ap.add_argument("--out", default="", help="把报告写入该 md 文件")
    args = ap.parse_args()

    conn = init_db()
    report = build_report(conn, args.mode)
    conn.close()
    print(report)
    if args.out:
        p = ROOT / args.out
        p.write_text(report, encoding="utf-8")
        print(f"\n✅ 报告已写入 {p}")


if __name__ == "__main__":
    main()
