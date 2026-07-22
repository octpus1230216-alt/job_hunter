"""
岗位推荐引擎（意见 D-8）——每日 15 条候选岗位。

选取原则（意见原文）：
- 世界知名企业
- 最新挂出（可选：jobspy 抓取，失败则跳过）
- 与简历部分相关
- 行业不限
- 地区可选（读取 config.preferences.locations）

输出：data/recommendations/latest.json（供 app「推荐岗位」页拉取）
      + 历史存档 data/recommendations/YYYY-MM-DD.json

设计：对运行环境零硬依赖。
- jobspy 缺失 / 网络不通 → 跳过「最新挂出」，只用世界名企种子。
- LLM 缺失 → 用简历关键词与偏好的重叠做相关性打分。
云端（GitHub Actions）每日 8:00(北京) 跑 recommender_run.py 生成本地 latest.json 并提交。
"""

import json
import random
from pathlib import Path
from datetime import datetime, date


SEED_PATH = Path(__file__).parent / "seed_companies.json"
RECOMMEND_DIR = Path(__file__).parent.parent / "data" / "recommendations"
DEFAULT_COUNT = 15


def _load_seed() -> list:
    if SEED_PATH.exists():
        try:
            return json.loads(SEED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _region_match(company_regions: list, wanted: list) -> bool:
    """wanted 为空（未设地区/仅 Remote）视为不限地区。"""
    if not wanted:
        return True
    wanted_norm = [w.strip().lower() for w in wanted]
    if "远程" in wanted_norm or "remote" in wanted_norm:
        return True
    comp_norm = [r.lower() for r in (company_regions or [])]
    return any(w in comp_norm for w in wanted_norm)


def _relevance_score(company: dict, resume: dict, prefs: dict) -> float:
    """0~1 的相关性。无 LLM 时用关键词重叠近似。"""
    signals = []
    # 行业命中偏好
    inds = [i.lower() for i in prefs.get("industries", [])]
    if company.get("industry", "").lower() in inds:
        signals.append(0.4)
    # 简历技能/经历命中公司行业或角色
    resume_text = json.dumps(resume, ensure_ascii=False).lower()
    if company.get("industry", "").lower() in resume_text:
        signals.append(0.2)
    for role in company.get("roles", []):
        if role.lower() in resume_text:
            signals.append(0.25)
            break
    # 目标职位命中
    for tr in prefs.get("target_roles", []):
        if tr.lower() in resume_text:
            signals.append(0.15)
            break
    return min(1.0, sum(signals))


def _fetch_latest_jobs(limit: int = 5) -> list:
    """可选：用 jobspy 拉「最新挂出」。失败/缺失则返回空。"""
    try:
        from jobspy import scrape_jobs  # type: ignore
    except Exception:
        return []
    try:
        # 仅作补充信号：抓少量近期岗位，提取公司名用于相关性加权
        jobs = scrape_jobs(
            site_name=["linkedin", "indeed"],
            search_term="software engineer",
            results_wanted=limit,
            country_indeed="USA",
            hours_old=72,
        )
        out = []
        for _, row in jobs.iterrows():
            out.append({
                "company": str(row.get("company", "")).strip(),
                "title": str(row.get("title", "")).strip(),
                "region": str(row.get("location", "")).strip()[:40],
                "posted": str(row.get("date_posted", ""))[:10],
                "url": str(row.get("job_url", "")).strip(),
                "source": "latest",
            })
        return out
    except Exception:
        return []


def _llm_relevance(items: list, resume: dict, llm_client) -> list:
    """可选：用 LLM 给候选公司打「与你相关度」并写理由。失败则保留原 reason。"""
    if llm_client is None or not items:
        return items
    try:
        comps = "；".join(f"{i['company']}({i.get('industry','')})" for i in items[:15])
        prompt = (
            "你是求职推荐助手。候选人简历摘要如下，请对下列公司判断与你是否相关，"
            "并给一句话推荐理由。只输出 JSON 数组，每项 {\"company\":\"原样\","
            "\"related\":true/false,\"why\":\"一句话理由\"}。\n\n"
            f"简历摘要：{json.dumps(resume, ensure_ascii=False)[:1500]}\n\n公司：{comps}"
        )
        resp = llm_client.chat_json(
            "你是严谨的求职推荐助手，只基于真实信息。", prompt)
        if isinstance(resp, list):
            by_c = {x.get("company"): x for x in resp if x.get("company")}
            for it in items:
                m = by_c.get(it["company"])
                if m:
                    it["related_llm"] = bool(m.get("related"))
                    if m.get("why"):
                        it["why"] = m["why"]
    except Exception:
        pass
    return items


def generate(count: int = DEFAULT_COUNT, resume: dict = None,
             prefs: dict = None, llm_client=None, seed: int = None) -> dict:
    """
    生成每日推荐。返回结构化 dict。
    resume/prefs 用于相关性加权与地区过滤；缺失时退化为纯世界名企随机选。
    """
    prefs = prefs or {}
    seed = seed if seed is not None else date.today().toordinal()
    rng = random.Random(seed)

    seed_companies = _load_seed()
    pool = []
    for c in seed_companies:
        if not _region_match(c.get("regions", []), prefs.get("locations", [])):
            continue
        rel = _relevance_score(c, resume or {}, prefs) if resume else 0.0
        role = (c.get("roles") or ["相关岗位"])[0]
        item = {
            "company": c["company"],
            "title": role,
            "industry": c.get("industry", ""),
            "region": (c.get("regions") or [""])[0],
            "url": c.get("careers", ""),
            "posted": "",
            "source": "world-known",
            "related_score": round(rel, 2),
            "why": _default_why(c, rel),
        }
        pool.append(item)

    # 可选：最新挂出（作为补充，标记 source=latest）
    latest = _fetch_latest_jobs(limit=5)
    seen = {p["company"].lower() for p in pool}
    for lj in latest:
        if lj["company"] and lj["company"].lower() not in seen:
            pool.append({
                "company": lj["company"],
                "title": lj.get("title") or "相关岗位",
                "industry": "",
                "region": lj.get("region", ""),
                "url": lj.get("url", ""),
                "posted": lj.get("posted", ""),
                "source": "latest",
                "related_score": 0.3,
                "why": "近期有在招岗位，可抢先投递",
            })
            seen.add(lj["company"].lower())

    # 排序：相关度高的优先，再随机打散保证每天有变化与行业多样
    pool.sort(key=lambda x: x["related_score"], reverse=True)
    top = pool[: max(count * 2, 20)]
    rng.shuffle(top)

    # 保证行业多样性：每个行业最多取 3 条
    chosen = []
    industry_cnt = {}
    for it in top:
        ind = it.get("industry") or "其他"
        if industry_cnt.get(ind, 0) >= 3:
            continue
        chosen.append(it)
        industry_cnt[ind] = industry_cnt.get(ind, 0) + 1
        if len(chosen) >= count:
            break
    # 不足则补齐
    if len(chosen) < count:
        for it in top:
            if it not in chosen:
                chosen.append(it)
            if len(chosen) >= count:
                break

    chosen = _llm_relevance(chosen, resume or {}, llm_client) if llm_client else chosen

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(chosen),
        "region_filter": prefs.get("locations", []),
        "items": chosen,
    }
    _persist(result)
    return result


def _default_why(company: dict, rel: float) -> str:
    if rel >= 0.4:
        return f"与你的背景/技能相关（{company.get('industry','')}行业头部）"
    if rel > 0:
        return f"{company.get('industry','')}行业知名企业，可拓展方向"
    return f"世界知名企业（{company.get('industry','')}），值得保持关注"


def _persist(result: dict) -> None:
    RECOMMEND_DIR.mkdir(parents=True, exist_ok=True)
    latest = RECOMMEND_DIR / "latest.json"
    latest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = RECOMMEND_DIR / f"{date.today().isoformat()}.json"
    archive.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def load_latest() -> dict | None:
    latest = RECOMMEND_DIR / "latest.json"
    if latest.exists():
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def load_history() -> list[dict]:
    """返回历史存档列表（按日期降序，不含 latest）。"""
    if not RECOMMEND_DIR.exists():
        return []
    out = []
    for p in sorted(RECOMMEND_DIR.glob("20*.json"), reverse=True):
        try:
            out.append({"date": p.stem, "path": str(p)})
        except Exception:
            pass
    return out
