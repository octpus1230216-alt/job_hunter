"""Desktop launcher for job_hunter (frozen by PyInstaller, one-folder).

Responsibilities:
  - ensure a default config.yaml exists (copied from config.example.yaml)
  - start a local Streamlit server on a free port (headless)
  - open the default browser to the app
  - show a tiny tkinter window so the user can quit cleanly
"""
import os
import sys
import time
import socket
import shutil
import subprocess
import webbrowser
import threading

try:
    import tkinter as tk
    _HAS_TK = True
except Exception:
    _HAS_TK = False


def app_dir():
    # Frozen one-folder: this exe sits next to app.py
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_server(port, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def ensure_config(base):
    cfg = os.path.join(base, "config.yaml")
    if not os.path.exists(cfg):
        example = os.path.join(base, "config.example.yaml")
        if os.path.exists(example):
            shutil.copyfile(example, cfg)


def main():
    base = app_dir()
    ensure_config(base)

    app_py = os.path.join(base, "app.py")
    if not os.path.exists(app_py):
        sys.stderr.write("Cannot find app.py next to launcher\n")
        return 1

    port = find_free_port()
    env = os.environ.copy()
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["STREAMLIT_SERVER_ENABLE_CORS"] = "false"

    cmd = [
        sys.executable, "-m", "streamlit", "run", app_py,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    proc = subprocess.Popen(cmd, cwd=base, env=env)

    server_up = wait_for_server(port)
    url = "http://127.0.0.1:{}".format(port)
    if server_up:
        webbrowser.open(url)

    if _HAS_TK:
        root = tk.Tk()
        root.title("半自动找工作工具")
        root.resizable(False, False)
        msg = "已在浏览器打开：\n{}\n\n关闭此窗口即退出程序。".format(url)
        tk.Label(root, text=msg, padx=20, pady=20, justify="left").pack()

        def on_close():
            try:
                proc.terminate()
            except Exception:
                pass
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

        def monitor():
            proc.wait()
            try:
                root.destroy()
            except Exception:
                pass

        threading.Thread(target=monitor, daemon=True).start()
        root.mainloop()
    else:
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
