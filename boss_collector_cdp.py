"""
Boss直聘 CDP 网络拦截采集器 v3.1 — 二终端架构
Chrome控制 + 数据接收 + 指令桥接 三合一（端口 9999）

使用方式:
1. 终端1: python boss_collector_cdp.py
   → Chrome 自动弹出，登录 Boss直聘，正常浏览即可
   → 同时启动数据接收服务器（端口 9999）
2. 终端2: streamlit run app.py
   → 在「发现职位」→「国内平台」页面点击搜索按钮，Chrome 自动导航
"""

import json
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import hashlib

from playwright.async_api import async_playwright

# ============================================================
# 配置
# ============================================================
DATA_DIR = Path(__file__).parent / "data" / "domestic_jobs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Playwright 持久化用户数据目录（登录状态会保留）
USER_DATA_DIR = Path(__file__).parent.parent / ".chrome_profile" / "boss"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# 统一端口（数据接收 + 指令桥接）
UNIFIED_PORT = 9999

# Boss直聘 API 端点特征
BOSS_API_PATTERNS = [
    "/search/joblist",
    "/job/detail",
    "/recommend/job",
    "/geek/job",
    "wapi/zpgeek",
    "wapi/zpboss",
    "zhipin.com/wapi",
]

stats = {"intercepted": 0, "extracted": 0, "sent": 0, "duplicates": 0, "detail_patches": 0}
seen_urls = set()

# 会话职位缓存: {job_key: job_dict}
jobs_cache = {}

# 内存职位存储（合并自 collector_server）
collected_jobs = []

# 全局引用（由指令服务器使用）
_global_context = None
_global_pages = []


# ============================================================
# 反检测注入脚本
# Boss直聘 CDP 时间差检测：console.table(largeArray) 耗时 → 判定自动化
# ============================================================
STEALTH_SCRIPT = """
// Boss直聘 CDP 时间差反检测 — document-start 阶段执行
(() => {
    'use strict';

    const nativeConsoleTable = console.table;
    console.table = function() {};

    const navStart = (typeof performance !== 'undefined' && performance.timing)
        ? performance.timing.navigationStart
        : Date.now();
    const nativePerformanceNow = performance.now;
    performance.now = function() { return Date.now() - navStart; };

    const hookedFns = new Map();
    hookedFns.set(console.table, 'table');
    hookedFns.set(performance.now, 'now');
    hookedFns.set(Function.prototype.toString, 'toString');

    const _origToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (hookedFns.has(this)) return 'function ' + hookedFns.get(this) + '() { [native code] }';
        if (this === Function.prototype.toString) return 'function toString() { [native code] }';
        return _origToString.call(this);
    };

    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [1, 2, 3, 4, 5];
            arr.item = (i) => arr[i];
            arr.namedItem = () => null;
            arr.refresh = () => {};
            Object.setPrototypeOf(arr, PluginArray.prototype);
            return arr;
        }
    });
    window.chrome = {
        runtime: { connect: () => {}, sendMessage: () => {} },
        loadTimes: () => {}, csi: () => {}
    };
    hookedFns.set(window.chrome.runtime.connect, 'connect');
    hookedFns.set(window.chrome.runtime.sendMessage, 'sendMessage');

    try {
        const contentWindowDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        const nativeGetter = contentWindowDesc.get;
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const iframeWin = nativeGetter.call(this);
                if (!iframeWin) return iframeWin;
                return new Proxy(iframeWin, {
                    get: function(target, prop) {
                        if (prop === 'console') {
                            const c = Reflect.get(target, prop, target);
                            c.table = console.table; return c;
                        }
                        return Reflect.get(target, prop, target);
                    }
                });
            }
        });
    } catch(e) {}
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    if (navigator.connection) Object.defineProperty(navigator.connection, 'rtt', { get: () => 100 });
})();
"""


# ============================================================
# 辅助函数
# ============================================================
def is_boss_api(url: str) -> bool:
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in BOSS_API_PATTERNS)


def is_job_response(url: str) -> bool:
    return is_boss_api(url) and "json" in url.lower() and "html" not in url.lower()


def is_list_response(url: str) -> bool:
    """判断是否是列表页 API"""
    return is_job_response(url) and ("joblist" in url.lower() or "search" in url.lower())


def is_detail_response(url: str) -> bool:
    """判断是否是详情页 API"""
    return is_job_response(url) and (
        "detail" in url.lower() or "job/" in url.lower()
    ) and "joblist" not in url.lower()


def _extract_job_id_from_url(url: str) -> str:
    """从 URL 中提取 jobId"""
    parsed = urlparse(url)
    params = {}
    for part in parsed.query.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v
    return params.get("jobId", params.get("encryptJobId", params.get("id", "")))


def extract_jobs_from_list(body: dict) -> list:
    """从列表 API 响应中提取职位（基础信息）"""
    jobs = []
    if not isinstance(body, dict):
        return jobs
    zp_data = body.get("zpData", body.get("zpdata", None))
    if zp_data is None:
        zp_data = body.get("data", body.get("result", body))
    if zp_data is None:
        return jobs
    if isinstance(zp_data, dict):
        job_list = (
            zp_data.get("jobList") or zp_data.get("list")
            or zp_data.get("jobCardList") or zp_data.get("result") or []
        )
        if isinstance(job_list, list):
            for item in job_list:
                job = _parse_job_item(item)
                if job and job.get("title"):
                    job["status"] = "basic"
                    jobs.append(job)
    return jobs


def extract_detail_from_response(body: dict) -> dict:
    """从详情 API 响应中提取详细描述"""
    if not isinstance(body, dict):
        return {}
    zp_data = body.get("zpData", body.get("zpdata", None))
    if zp_data is None:
        zp_data = body.get("data", body.get("result", body))
    if zp_data is None:
        return {}
    job_info = zp_data.get("jobInfo") or zp_data.get("jobDetail") or zp_data
    if not isinstance(job_info, dict):
        return {}
    return {
        "description": job_info.get("jobDesc") or job_info.get("description") or "",
        "requirements": job_info.get("jobRequire") or job_info.get("requirement") or "",
        "company_info": job_info.get("companyInfo") or job_info.get("companyDesc") or "",
    }


def _parse_job_item(item: dict) -> dict:
    if not isinstance(item, dict):
        return {}
    company = (
        item.get("brandName") or item.get("brandComName")
        or item.get("companyName") or item.get("company_name")
        or item.get("compName") or ""
    )
    title = item.get("jobName") or item.get("title") or item.get("jobTitle") or ""
    salary = item.get("salaryDesc") or item.get("salary") or item.get("providesalary") or ""
    location = (
        item.get("cityName") or item.get("city") or item.get("location")
        or item.get("workAddress") or ""
    )
    description = item.get("jobDesc") or item.get("description") or item.get("detail") or ""
    job_id = (
        item.get("encryptJobId") or item.get("jobId")
        or item.get("encryptId") or item.get("id") or ""
    )
    job_url = f"https://www.zhipin.com/job_detail/{job_id}.html" if job_id else ""
    if not title:
        return {}
    return {
        "company": str(company),
        "title": str(title),
        "salary": str(salary),
        "location": str(location),
        "description": str(description)[:2000] if description else "",
        "job_url": job_url,
        "job_id": str(job_id),
        "source_platform": "boss_cdp",
    }


def make_job_key(job: dict) -> str:
    raw = f"{job.get('company','')}|{job.get('title','')}|{job.get('job_url','')}"
    return hashlib.md5(raw.encode()).hexdigest()


def load_seen_keys():
    key_file = DATA_DIR / "cdp_sent_keys.txt"
    if key_file.exists():
        with open(key_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    seen_urls.add(line)


def save_seen_key(key: str):
    key_file = DATA_DIR / "cdp_sent_keys.txt"
    with open(key_file, "a", encoding="utf-8") as f:
        f.write(key + "\n")


def save_session_cache():
    """将会话缓存写入文件"""
    cache_file = DATA_DIR / "cdp_session.json"
    serializable = {}
    for k, v in jobs_cache.items():
        serializable[k] = v
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "total": len(serializable),
            "complete_count": sum(1 for j in serializable.values() if j.get("status") == "complete"),
            "jobs": serializable,
        }, f, ensure_ascii=False, indent=2)


async def store_job(job: dict) -> bool:
    """存储职位到本地内存（替代 collector_server）"""
    # 去重
    existing_urls = {j.get("job_url", "") for j in collected_jobs}
    if job.get("job_url") and job.get("job_url") in existing_urls:
        return False
    collected_jobs.append(job)
    _save_collected_jobs()
    return True


def _save_collected_jobs():
    """持久化保存 collected_jobs"""
    filepath = DATA_DIR / "current_session.json"
    serializable = []
    for j in collected_jobs:
        serializable.append(j)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


async def update_job_detail(job_url: str, detail: dict):
    """按 job_url 匹配并更新详情"""
    for job in collected_jobs:
        if job.get("job_url") == job_url and job.get("status") != "complete":
            job["description"] = detail.get("description", job.get("description", ""))
            job["requirements"] = detail.get("requirements", "")
            job["company_info"] = detail.get("company_info", "")
            job["status"] = "complete"
            job["detail_collected_at"] = datetime.now().isoformat()
            _save_collected_jobs()
            return True
    return False


def find_cache_key_by_url(job_url: str) -> str | None:
    """在缓存中查找匹配 job_url 的 key"""
    for k, v in jobs_cache.items():
        if v.get("job_url") == job_url:
            return k
    return None


# ============================================================
# HTTP 统一服务器（数据接收 + 指令桥接 + 状态查询，端口 9999）
# ============================================================
class UnifiedHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默日志

    def _json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    # ======== GET 端点 ========
    def do_GET(self):
        if self.path == "/" or self.path == "/status":
            # 综合状态
            complete = sum(1 for j in collected_jobs if j.get("status") == "complete")
            basic = len(collected_jobs) - complete
            self._json_response({
                "status": "running",
                "pages": len(_global_pages),
                "jobs_cached": len(jobs_cache),
                "jobs_collected": len(collected_jobs),
                "jobs_complete": complete,
                "basic": basic,
                "complete": complete,
                "total": len(collected_jobs),
                "stats": stats,
            })
        elif self.path == "/jobs":
            # 获取所有已收集职位
            self._json_response({
                "total": len(collected_jobs),
                "jobs": collected_jobs,
            })
        elif self.path == "/export":
            # 导出为 JSON 文件
            filename = f"domestic_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = DATA_DIR / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(collected_jobs, f, ensure_ascii=False, indent=2)
            self._json_response({"status": "ok", "file": str(filepath), "total": len(collected_jobs)})
        else:
            self.send_response(404)
            self.end_headers()

    # ======== POST 端点 ========
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except Exception:
            body = {}

        if self.path == "/navigate":
            # 导航指令
            url = body.get("url", "")
            if url and _global_pages:
                asyncio.run_coroutine_threadsafe(
                    _navigate_page(_global_pages[0], url), asyncio.get_event_loop()
                )
                print(f"\n📡 [指令] 导航: {url[:80]}")
                self._json_response({"ok": True, "msg": f"导航: {url[:80]}"})
            else:
                self._json_response({"ok": False, "error": "缺少 url 或页面未就绪"}, 400)

        elif self.path == "/clear":
            collected_jobs.clear()
            _save_collected_jobs()
            print("🗑️  已清空所有职位")
            self._json_response({"status": "ok", "message": "已清空"})

        elif self.path == "/collect":
            # 兼容旧接口：手动提交职位
            if body and body.get("title"):
                job = {
                    "company": body.get("company", ""),
                    "title": body.get("title", ""),
                    "location": body.get("location", ""),
                    "description": body.get("description", ""),
                    "salary": body.get("salary", ""),
                    "job_url": body.get("job_url", ""),
                    "job_id": body.get("job_id", ""),
                    "source_platform": body.get("source_platform", "manual"),
                    "status": body.get("status", "basic"),
                    "collected_at": datetime.now().isoformat(),
                    "detail_collected_at": None,
                }
                existing_urls = {j.get("job_url", "") for j in collected_jobs}
                if job["job_url"] and job["job_url"] in existing_urls:
                    self._json_response({"status": "duplicate"})
                else:
                    collected_jobs.append(job)
                    _save_collected_jobs()
                    self._json_response({"status": "ok", "total": len(collected_jobs)})
            else:
                self._json_response({"status": "error", "message": "缺少必要字段"}, 400)

        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
async def _navigate_page(page, url: str):
    """导航页面到指定 URL"""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        print(f"  ✅ 已导航到: {url[:80]}")
    except Exception as e:
        print(f"  ⚠️ 导航失败: {e}")


def start_unified_server():
    """启动 HTTP 统一服务器（后台线程）"""
    server = HTTPServer(("127.0.0.1", UNIFIED_PORT), UnifiedHandler)
    print(f"  📡 统一服务端口: http://localhost:{UNIFIED_PORT}")
    print(f"     数据接收 + 指令桥接 + 状态查询 — 三合一")
    server.serve_forever()


# ============================================================
# 主逻辑
# ============================================================
async def main():
    global _global_context, _global_pages

    print("=" * 60)
    print("  🔍 Boss直聘 CDP 网络拦截采集器 v3.1 — 二终端")
    print("=" * 60)
    print(f"  💾 用户数据: {USER_DATA_DIR}")
    print(f"  📡 统一端口: http://localhost:{UNIFIED_PORT} (数据+指令+状态)")
    print()

    load_seen_keys()
    print(f"📂 已加载 {len(seen_urls)} 条去重记录")

    # 启动统一服务器
    threading.Thread(target=start_unified_server, daemon=True).start()

    async with async_playwright() as p:
        print("\n🚀 正在启动 Chrome（已注入反检测补丁）...")

        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-infobars",
                    "--window-size=1366,768",
                ],
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            _global_context = context
            print("✅ Chrome 已启动（反检测已激活）")
        except Exception as e:
            print(f"❌ Chrome 启动失败: {e}")
            print("\n💡 可能需要先关闭其他 Chrome 窗口，然后重试")
            return

        # 为每个新页面注入反检测脚本
        context.on("page", lambda page: page.add_init_script(STEALTH_SCRIPT))
        for page in context.pages:
            await page.add_init_script(STEALTH_SCRIPT)

        # 获取主页面
        page = context.pages[0] if context.pages else await context.new_page()
        _global_pages = [page]

        if "zhipin.com" not in (page.url or ""):
            print("🌐 正在打开 Boss直聘...")
            await page.goto("https://www.zhipin.com/web/geek/job", wait_until="domcontentloaded")
        print("📄 Boss直聘页面已加载")

        # ===========================================
        # 网络响应拦截
        # ===========================================
        async def handle_response(response):
            global stats, seen_urls, jobs_cache
            url = response.url
            if not is_job_response(url):
                return
            stats["intercepted"] += 1

            try:
                body = await response.json()
            except Exception:
                return

            # ---- 列表页：提取基础职位 ----
            if is_list_response(url):
                jobs = extract_jobs_from_list(body)
                if jobs:
                    new_count = 0
                    for job in jobs:
                        job_key = make_job_key(job)
                        if job_key in seen_urls:
                            stats["duplicates"] += 1
                            continue
                        seen_urls.add(job_key)
                        save_seen_key(job_key)

                        jobs_cache[job_key] = job
                        stats["extracted"] += 1
                        new_count += 1

                        await store_job(job)
                        if stats["extracted"] % 5 == 1 or new_count <= 3:
                            print(f"  🟡 {job.get('company','')[:20]} — {job.get('title','')[:30]} | {job.get('salary','N/A')}  [基本信息]")

                    if new_count > 3:
                        print(f"  ... 共 {new_count} 个新职位（点击查看详情以获取JD）")
                    save_session_cache()
                    stats["sent"] += new_count
                    print(f"\n🔍 [{stats['intercepted']}] 列表API — 新增 {new_count} 个基础职位")

            # ---- 详情页：补全 JD ----
            elif is_detail_response(url):
                detail = extract_detail_from_response(body)
                desc = detail.get("description", "")
                if not desc or len(desc) < 20:
                    return  # 没有有效 JD

                # 尝试从 URL 中提取 jobId 来匹配
                job_id = _extract_job_id_from_url(url)

                # 在缓存中查找匹配的职位并补全
                patched = False
                patched_job = None
                for key, job in jobs_cache.items():
                    if job.get("status") == "complete":
                        continue
                    if job_id and job.get("job_id") == job_id:
                        job["description"] = desc
                        job["requirements"] = detail.get("requirements", "")
                        job["company_info"] = detail.get("company_info", "")
                        job["status"] = "complete"
                        job["detail_collected_at"] = datetime.now().isoformat()
                        patched = True
                        patched_job = job
                    elif not job_id:
                        job_url = job.get("job_url", "")
                        url_tail = urlparse(url).path
                        if job_url and url_tail in job_url:
                            job["description"] = desc
                            job["status"] = "complete"
                            job["detail_collected_at"] = datetime.now().isoformat()
                            patched = True
                            patched_job = job

                if patched:
                    stats["detail_patches"] += 1
                    if patched_job:
                        await update_job_detail(patched_job.get("job_url", ""), {
                            "description": patched_job.get("description", ""),
                            "requirements": patched_job.get("requirements", ""),
                            "company_info": patched_job.get("company_info", ""),
                        })
                        print(f"  📝 已补全JD: {patched_job.get('company','')[:20]} — {patched_job.get('title','')[:30]}")
                    save_session_cache()

        page.on("response", handle_response)
        context.on("page", lambda p: p.on("response", handle_response))

        print()
        print("=" * 60)
        print("  🟢 监听中...")
        print("  在 Chrome 窗口中正常浏览 Boss直聘 即可")
        print("  - 首次使用需扫码登录")
        print("  - 搜索职位 → 自动收集（基本信息）")
        print("  - 点击详情 → 自动补全 JD（完整信息）")
        print()
        print("  🎯 Streamlit 集成:")
        print(f"  - 统一端口: http://localhost:{UNIFIED_PORT}")
        print(f"  - /status — 状态查询")
        print(f"  - /jobs   — 获取职位列表")
        print(f"  - /navigate — 搜索导航指令")
        print("  按 Ctrl+C 停止")
        print("=" * 60)
        print()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        await context.close()

    print()
    print("=" * 60)
    print(f"  📊 采集统计")
    print(f"  API 拦截: {stats['intercepted']} 次")
    print(f"  职位提取: {stats['extracted']} 个（基础）")
    print(f"  详情补全: {stats['detail_patches']} 个")
    print(f"  发送成功: {stats['sent']} 个")
    print(f"  去重跳过: {stats['duplicates']} 个")
    print(f"  缓存总计: {len(jobs_cache)} 个")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
