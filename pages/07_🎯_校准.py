"""
校准页面 — 基于真实投递结果校准竞争力因子 + 诊断匹配度预测力。

对应命令行 analytics/tune.py 的可视化版本：
- 用各档位实测 positive/n + Beta 收缩，给出 COMPETITION_FACTOR 建议值
- 支持「一键写回」到 data/competition_overrides.json（运行时优先于 store.py 默认值）
- 诊断七维 fit_overall 与真实过筛的相关性（实验显示接近 0）

注意：本页读取 analytics 的 SQLite(applications) 数据。网页「📈 投递追踪」用的是另一套
JSON 存储（modules.tracker），两者现已打通——追踪页每次状态更新会**自动回灌 SQLite**，
「✨ 生成简历」页生成后也会写入追踪。因此真实投递结果会自动流入本页校准。
若历史数据未同步，可在追踪页点「🔄 回灌校准库」一键补齐。
"""

import streamlit as st
import pandas as pd
import statistics

from modules.store import (
    DEFAULT_DB, COMPETITION_FACTOR, init_db, competition_breakdown,
    suggest_competition_factor, load_competition_overrides, save_competition_overrides,
    get_all,
)

from modules.auth import require_auth
require_auth()

st.title("🎯 校准（竞争力因子 + 匹配度诊断）")
st.caption("基于真实投递结果标签校准「竞争力因子」，并诊断七维匹配度的预测力。对应 analytics/tune.py。")

conn = init_db(DEFAULT_DB)

# ============================================================
# 1) 竞争力因子校准
# ============================================================
st.subheader("1) 竞争力因子校准")
st.markdown(
    "不同公司竞争强度不同，同一匹配度在顶级厂的真实过筛率更低。"
    "`COMPETITION_FACTOR` 把这一折扣固化进公式。下列用「实测 positive/n + Beta 收缩」给出建议值，"
    "可一键写回（运行时优先于 store.py 默认值）。"
)

rows_bd = competition_breakdown(conn)
suggested = suggest_competition_factor(conn)
overrides = load_competition_overrides()
seen = set()
tbl = []
for r in rows_bd:
    tier = r["competition_level"]
    n = r["n"]
    pos = r["positive"]
    seen.add(tier)
    cur = COMPETITION_FACTOR.get(tier, "-")
    sug = suggested.get(tier, cur)
    eff = overrides.get(tier, sug)
    rate = f"{pos / n * 100:.1f}%" if n else "-"
    tbl.append({
        "档位": tier, "样本数n": n, "过筛数": pos, "实测过筛率": rate,
        "当前因子": cur, "建议因子": sug, "运行时生效值": eff,
    })
for tier in COMPETITION_FACTOR:
    if tier not in seen:
        tbl.append({
            "档位": tier, "样本数n": 0, "过筛数": 0, "实测过筛率": "-",
            "当前因子": COMPETITION_FACTOR[tier],
            "建议因子": suggested.get(tier, COMPETITION_FACTOR[tier]),
            "运行时生效值": overrides.get(tier, suggested.get(tier, COMPETITION_FACTOR[tier])),
        })

st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)

c1, c2 = st.columns(2)
with c1:
    if st.button("💾 一键写回建议因子", use_container_width=True,
                 help="将建议因子写入 data/competition_overrides.json，运行时优先于 store.py 默认值"):
        save_competition_overrides(
            {tier: suggested.get(tier, COMPETITION_FACTOR[tier]) for tier in COMPETITION_FACTOR}
        )
        st.success("已写回！运行时将使用覆盖值。如需还原，删除 data/competition_overrides.json 即可。")
        st.rerun()
with c2:
    if overrides:
        if st.button("↩️ 清除覆盖（恢复默认）", use_container_width=True):
            save_competition_overrides({})
            st.success("已清除覆盖，恢复 store.py 默认值。")
            st.rerun()

# ============================================================
# 2) 匹配度预测力诊断
# ============================================================
st.subheader("2) 七维匹配度预测力诊断")
POSITIVE = {"interview", "offer", "hired", "offer_declined", "screened"}
apps = get_all(conn)
scored = [a for a in apps if a["fit_overall"] is not None and a["last_status"] not in ("prospect",)]

if scored:
    xs = [a["fit_overall"] for a in scored]
    ys = [1 if a["last_status"] in POSITIVE else 0 for a in scored]
    n_pos = sum(ys)
    if len(xs) >= 2:
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sx = sum((x - mx) ** 2 for x in xs) ** 0.5
        sy = sum((y - my) ** 2 for y in ys) ** 0.5
        r = cov / (sx * sy) if sx and sy else float("nan")
    else:
        r = float("nan")
    pos_fit = statistics.mean([a["fit_overall"] for a, yy in zip(scored, ys) if yy]) if n_pos else 0
    neg_n = len(scored) - n_pos
    neg_fit = statistics.mean([a["fit_overall"] for a, yy in zip(scored, ys) if not yy]) if neg_n else 0

    st.markdown(f"- 样本 **{len(scored)}**（正={n_pos} 负={neg_n}）")
    st.markdown(f"- fit_overall 与过筛 的相关系数 **r = {r:.3f}**（接近 0 → 匹配度不预测结果）")
    st.markdown(f"- 正样本均 fit=**{pos_fit:.1f}** ｜ 负样本均 fit=**{neg_fit:.1f}**")
    st.info(
        "结论：fit_overall 不宜直接当命中率；真实预测应交给竞争力因子校准 + 决策通道"
        "（网页「📊 审核挑选」可一键运行，实验 AUC≈0.64）。"
    )
else:
    st.info(
        "暂无已评分且有结果的记录，无法诊断。"
        "请先用 score.py 评分并回填 last_status，或在网页投递后把结果回流到 SQLite。"
    )

conn.close()
