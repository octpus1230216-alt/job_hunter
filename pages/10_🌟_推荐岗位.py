"""
推荐岗位页面（意见 D-8）——侧边栏常驻。

- 展示每日 15 条推荐（来自 data/recommendations/latest.json，由 GitHub Actions 每日 8:00 生成并提交）
- 提供「刷新」按钮：云端不可达时本地用 LLM 现跑（需已上传简历 + 配置 API）
- 历史存档可查
- 每条可「加入岗位池」（进海投）或「去精投」（进精投页并预填 JD）
数字分已内部化，本页只给推荐理由，不展示匹配分。
"""

import streamlit as st
from pathlib import Path
from datetime import datetime

from modules.auth import require_auth
require_auth()

st.title("🌟 推荐岗位（每日 15 条）")
st.caption("每天 08:00 自动刷新一批世界知名企业的在招方向；也可手动刷新。选中后去「海投」批量决策，或去「精投」深挖单家。")


def _go_jingtou(job: dict):
    st.session_state.jingtou_job = {
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "location": job.get("region", ""),
        "description": f"{job.get('company','')} — {job.get('title','')}\n行业：{job.get('industry','')}\n职位描述见官网：{job.get('url','')}",
        "job_url": job.get("url", ""),
        "source_platform": "推荐岗位",
    }
    st.session_state.jingtou_decision = None
    st.session_state.jingtou_gaps = None
    st.switch_page("pages/02_🎯_精投.py")


def _add_to_pool(job: dict):
    pool = list(st.session_state.get("all_jobs", []) or [])
    key = f"{job.get('company','')}|{job.get('title','')}"
    if any(f"{j.get('company','')}|{j.get('title','')}" == key for j in pool):
        st.toast("已在岗位池中")
        return
    pool.append({
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "location": job.get("region", ""),
        "description": f"行业：{job.get('industry','')}\n官网：{job.get('url','')}",
        "job_url": job.get("url", ""),
        "source_platform": "推荐岗位",
    })
    st.session_state.all_jobs = pool
    st.toast(f"已加入岗位池：{job.get('company')}")


def _render_items(items: list, key_prefix: str = ""):
    for job in items:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{job.get('company','?')}** — {job.get('title','?')}")
                meta = []
                if job.get("industry"):
                    meta.append(f"行业 {job.get('industry')}")
                if job.get("region"):
                    meta.append(f"地区 {job.get('region')}")
                if job.get("posted"):
                    meta.append(f"发布 {job.get('posted')}")
                if meta:
                    st.caption(" · ".join(meta))
                st.markdown(f"💡 {job.get('why', '')}")
            with c2:
                if job.get("url"):
                    st.link_button("官网投递", job.get("url"))
                st.button("去精投", key=f"rec_jt_{key_prefix}{job.get('company')}_{job.get('title')}",
                          on_click=_go_jingtou, args=(job,))
                st.button("加入岗位池", key=f"rec_pool_{key_prefix}{job.get('company')}_{job.get('title')}",
                          on_click=_add_to_pool, args=(job,))


# ============================================================
# 刷新 / 立即生成
# ============================================================
c_refresh, c_info = st.columns([1, 3])
with c_refresh:
    if st.button("🔄 刷新", use_container_width=True, type="primary"):
        llm = st.session_state.get("llm_client")
        resume = st.session_state.get("resume_parsed")
        if llm and resume:
            with st.status("本地生成今日推荐…", expanded=True) as s:
                from modules.recommender import generate
                prefs = st.session_state.get("config", {}).get("preferences", {})
                generate(resume=resume, prefs=prefs, llm_client=llm)
                s.update(label="已生成", state="complete")
            st.rerun()
        else:
            st.warning("本地刷新需要：已上传简历 + 配置 API。\n否则请等每日 08:00 云端自动更新。")
with c_info:
    st.caption("云端每天 08:00（北京时间）自动生成并提交 latest.json；本地无网时显示最近一次结果。")

data = None
try:
    from modules.recommender import load_latest, load_history
    data = load_latest()
    history = load_history()
except Exception:
    history = []

if not data or not data.get("items"):
    st.info("还没有推荐数据。点击「刷新」本地生成，或等每日 08:00 云端自动生成。")
    st.stop()

st.success(f"今日推荐 {data['count']} 条（生成时间：{data.get('generated_at','?')}）"
          + (f" ｜ 地区过滤：{', '.join(data.get('region_filter') or [])}" if data.get("region_filter") else ""))

_render_items(data["items"])

# ============================================================
# 历史存档
# ============================================================
if history:
    with st.expander("📚 历史推荐存档"):
        for h in history[:14]:
            if st.button(f"查看 {h['date']}", key=f"hist_{h['date']}"):
                try:
                    import json
                    past = json.loads(Path(h["path"]).read_text(encoding="utf-8"))
                    st.markdown(f"#### {h['date']}（{past.get('count', '?')} 条）")
                    _render_items(past.get("items", []))
                except Exception:
                    st.error("读取历史失败")
