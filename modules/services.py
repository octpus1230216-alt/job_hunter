"""
服务层门面（意见 H：移动端预留）。

把「简历/决策/生成/追踪/推荐/个人信息存储」收敛为一组稳定函数，
页面只依赖本模块，不直接 import 各底层模块。这样将来要抽成独立
后端服务 / 移动端 API 时，只要在本层后面替换实现即可，页面零改动。

这是轻量门面：本期仍在同一进程内调用本地模块，但边界已清晰，
是移动端 / 云端化的第一步。
"""

from typing import Optional


def get_llm():
    """返回缓存的 LLM 客户端（无则 None）。"""
    try:
        from modules.llm import LLMClient
        return LLMClient()
    except Exception:
        return None


def load_resume() -> Optional[dict]:
    """从用户选择的个人信息目录加载已解析简历。"""
    try:
        from modules.profile_store import get_profile_store
        return get_profile_store().load_parsed()
    except Exception:
        return None


def decide_single(resume: dict, job: dict, prefs: dict = None) -> dict:
    """单岗位 AI 决策通道。"""
    from modules.matcher import JobMatcher
    return JobMatcher(get_llm()).decide_single(resume, job, prefs or {})


def decide_batch(resume: dict, jobs: list, prefs: dict = None, progress_callback=None) -> list:
    """批量 AI 决策通道。"""
    from modules.matcher import JobMatcher
    return JobMatcher(get_llm()).decide_batch(
        resume, jobs, prefs or {}, progress_callback=progress_callback)


def generate_for_job(resume: dict, job: dict, bilingual: bool = True,
                      generate_cover_letter: bool = True) -> dict:
    """为单个岗位生成定制简历 +（可选）求职信 + 速查卡。"""
    from modules.style_analyzer import StyleAnalyzer
    from modules.generator import ResumeGenerator
    llm = get_llm()
    analyzer = StyleAnalyzer(llm)
    generator = ResumeGenerator(llm, analyzer)
    return generator.generate_all(
        resume, job, bilingual=bilingual, generate_cover_letter=generate_cover_letter)


def add_application(company: str, title: str, **kwargs) -> dict:
    """写入一条投递记录（回灌校准库）。"""
    from modules.tracker import ApplicationTracker
    return ApplicationTracker().add(company, title, **kwargs)


def recommend_daily(resume: dict = None, prefs: dict = None, llm=None) -> dict:
    """生成每日岗位推荐。"""
    from modules.recommender import generate
    return generate(resume=resume, prefs=prefs or {}, llm_client=llm)


def get_profile_store():
    """返回个人信息存储实例（本地 / 云端预留）。"""
    from modules.profile_store import get_profile_store as _g
    return _g()
