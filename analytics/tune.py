"""tune.py — 基于真实结果标签，校准竞争力因子并诊断七维匹配度的预测力。

零依赖（仅 stdlib + 本库 modules.store）。
用法：
  python analytics/tune.py            # 读默认 DB，输出校准建议与诊断
  python analytics/tune.py --db PATH  # 指定 DB 路径

核心结论（来自 287 条带标签样本的实验，见 analytics/README）：
- 七维 fit_overall 几乎不预测真实结果（AUC≈0.49），不可直接当命中率；
- realistic_prob（fit × 竞争力因子）AUC≈0.61，预测力主要来自竞争力层级；
- LLM 决策通道（直接预测过筛概率）AUC≈0.64，为最佳通道。
因此调参重点 = 校准竞争力因子 + 用决策通道做预测头，而非纠结七维权重。
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from modules.store import (
    DEFAULT_DB, COMPETITION_FACTOR, init_db,
    competition_breakdown, suggest_competition_factor, get_all,
)

# 正反馈（进入面试或更好）视为"过筛成功"
POSITIVE = {"interview", "offer", "hired", "offer_declined", "screened"}


def _is_positive(status: str) -> int:
    return 1 if status in POSITIVE else 0


def _pearson(xs, ys):
    """皮尔逊相关系数（零依赖）。"""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return float("nan")
    return cov / (sx * sy)


def main() -> None:
    ap = argparse.ArgumentParser(description="tune.py — 竞争力因子校准 + 匹配度诊断")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 库路径")
    args = ap.parse_args()
    conn = init_db(Path(args.db))

    print("=== 1) 竞争力因子校准（建议值基于 measured positive/n + Beta 收缩） ===")
    suggested = suggest_competition_factor(conn)
    print(f"{'档位':<16}{'当前因子':>10}{'建议因子':>10}{'n':>6}{'positive':>9}{'实测过筛率':>12}")
    rows = competition_breakdown(conn)
    seen = set()
    for r in rows:
        tier = r["competition_level"]; n = r["n"]; pos = r["positive"]
        seen.add(tier)
        cur = COMPETITION_FACTOR.get(tier, "-")
        sug = suggested.get(tier, "-")
        rate = f"{pos / n * 100:.1f}%" if n else "-"
        print(f"{tier:<16}{str(cur):>10}{str(sug):>10}{n:>6}{pos:>9}{rate:>12}")
    # 数据中未出现的档位：沿用当前因子
    for tier in COMPETITION_FACTOR:
        if tier not in seen:
            print(f"{tier:<16}{COMPETITION_FACTOR[tier]:>10}{suggested.get(tier, '-'):>10}{0:>6}{0:>9}{'-':>12}")

    print("\n建议替换 store.py 的 COMPETITION_FACTOR 为：")
    print("COMPETITION_FACTOR = {")
    for tier in COMPETITION_FACTOR:
        v = suggested.get(tier, COMPETITION_FACTOR[tier])
        print(f'    "{tier}": {v},')
    print("}")

    print("\n=== 2) 七维匹配度预测力诊断（fit_overall vs 真实过筛） ===")
    apps = get_all(conn)
    scored = [a for a in apps
              if a["fit_overall"] is not None and a["last_status"] not in ("prospect",)]
    if scored:
        xs = [a["fit_overall"] for a in scored]
        ys = [_is_positive(a["last_status"]) for a in scored]
        n_pos = sum(ys)
        r = _pearson(xs, ys)
        pos_fit = statistics.mean([a["fit_overall"] for a, y in zip(scored, ys) if y])
        neg_fit = statistics.mean([a["fit_overall"] for a, y in zip(scored, ys) if not y])
        print(f"样本={len(scored)} 正={n_pos} 负={len(scored) - n_pos}")
        print(f"fit_overall 与 过筛 的相关系数 r = {r:.3f}（接近0说明匹配度不预测结果）")
        print(f"正样本均 fit={pos_fit:.1f}  负样本均 fit={neg_fit:.1f}（差异小=区分度弱）")
        print("结论：fit_overall 不宜直接当命中率；真实预测应交给竞争力因子校准 + 决策通道。")
    else:
        print("暂无已评分且有结果的记录，无法诊断（先用 score.py 评分并回填 last_status）。")

    conn.close()


if __name__ == "__main__":
    main()
