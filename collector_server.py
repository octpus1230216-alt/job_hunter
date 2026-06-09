"""
本地职位采集接收器 — 接收浏览器脚本发来的国内平台职位数据
启动方式: python collector_server.py
访问: http://localhost:8765
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# 数据存储目录
DATA_DIR = Path(__file__).parent / "data" / "domestic_jobs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 当前会话收集的职位（内存）
collected_jobs = []


@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "total_collected": len(collected_jobs),
        "last_job": collected_jobs[-1] if collected_jobs else None,
    })


@app.route("/debug", methods=["POST"])
def debug_raw():
    """调试端点：接收并记录原始 API 数据（不加入职位列表）"""
    try:
        data = request.get_json(force=True)
        url = data.get("url", "")[:120]
        json_data = data.get("data", {})

        # 只记录包含职位相关字段的请求
        str_data = str(json_data)[:200]
        print(f"🔍 [DEBUG] {url}")
        print(f"   {str_data}")

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/collect", methods=["POST"])
def collect_job():
    """接收浏览器脚本发来的职位数据"""
    try:
        data = request.get_json(force=True)

        if not data or not data.get("title"):
            return jsonify({"status": "error", "message": "缺少必要字段"}), 400

        job = {
            "company": data.get("company", ""),
            "title": data.get("title", ""),
            "location": data.get("location", ""),
            "description": data.get("description", ""),
            "salary": data.get("salary", ""),
            "job_url": data.get("job_url", ""),
            "source_platform": data.get("source_platform", "boss"),
            "collected_at": datetime.now().isoformat(),
        }

        # 去重
        existing_urls = {j.get("job_url", "") for j in collected_jobs}
        if job["job_url"] and job["job_url"] in existing_urls:
            return jsonify({"status": "duplicate", "message": "已存在"})

        collected_jobs.append(job)

        # 每次收集后保存
        _save_jobs()

        print(f"✅ 收到: {job['company']} - {job['title']}")
        return jsonify({"status": "ok", "total": len(collected_jobs)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/jobs", methods=["GET"])
def get_jobs():
    """获取所有已收集的职位"""
    return jsonify({
        "total": len(collected_jobs),
        "jobs": collected_jobs,
    })


@app.route("/clear", methods=["POST"])
def clear_jobs():
    """清空收集的职位"""
    collected_jobs.clear()
    _save_jobs()
    return jsonify({"status": "ok", "message": "已清空"})


@app.route("/export", methods=["GET"])
def export_jobs():
    """导出职位为JSON文件"""
    filename = f"domestic_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(collected_jobs, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "ok", "file": str(filepath), "total": len(collected_jobs)})


def _save_jobs():
    """持久化保存"""
    filepath = DATA_DIR / "current_session.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(collected_jobs, f, ensure_ascii=False, indent=2)


def _load_jobs():
    """加载上次保存的数据"""
    filepath = DATA_DIR / "current_session.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            collected_jobs.extend(data)
        print(f"📂 加载了 {len(data)} 个历史职位")


def main():
    port = 8765

    # 加载历史数据
    _load_jobs()

    print("=" * 50)
    print("  🔌 本地职位采集接收器已启动")
    print(f"  📡 监听地址: http://localhost:{port}")
    print(f"  📂 数据目录: {DATA_DIR}")
    print(f"  📊 已有职位: {len(collected_jobs)} 个")
    print()
    print("  使用方法:")
    print("  1. 安装 Tampermonkey 浏览器插件")
    print("  2. 导入 browser_script/ 目录下的用户脚本")
    print("  3. 正常浏览 Boss直聘/猎聘，脚本自动收集")
    print()
    print("  ⚠️  关闭此窗口会停止收集")
    print("=" * 50)

    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
