"""
岗位推荐 CLI —— 供 GitHub Actions 每日定时调用（意见 D-8，决策 C：云端定时跑）。

本地也可手动运行：python recommender_run.py
无 LLM / 无 jobspy / 无网络时也能生成（退化为世界名企种子 + 行业多样性）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.recommender import generate


def main():
    llm = None
    try:
        from modules.llm import LLMClient
        llm = LLMClient()
    except Exception:
        llm = None

    # CI 环境没有个人简历，退化为纯世界名企 + 行业多样选择；
    # 若本地有 data/profile/resume_parsed.json，则用它做相关性加权。
    resume = None
    prefs = {}
    try:
        prof = Path(__file__).parent / "data" / "profile" / "resume_parsed.json"
        if prof.exists():
            import json
            resume = json.loads(prof.read_text(encoding="utf-8"))
        cfg = Path(__file__).parent / "config.yaml"
        if cfg.exists():
            import yaml
            _c = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            prefs = _c.get("preferences", {})
    except Exception:
        pass

    result = generate(resume=resume, prefs=prefs, llm_client=llm)
    print(f"[recommender] generated {result['count']} recommendations")


if __name__ == "__main__":
    main()
