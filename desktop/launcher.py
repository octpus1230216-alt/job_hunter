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
import logging

try:
    import tkinter as tk
    _HAS_TK = True
except Exception:
    _HAS_TK = False


# ---- Safe logging (sys.stderr may be None in frozen console=False) ----
_log = logging.getLogger("job_hunter")
_log.setLevel(logging.DEBUG)
if sys.stderr is not None:
    _log.addHandler(logging.StreamHandler(sys.stderr))
else:
    # Fallback: log to a file next to the exe when stderr unavailable
    _log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "launcher.log")
    _log.addHandler(logging.FileHandler(_log_file, mode="w", encoding="utf-8"))


def app_dir():
    """Return the directory where job_hunter.exe lives."""
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def internal_dir():
    """Return PyInstaller's _internal extraction path (where datas live)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return None


def _find_file_recursive(base, filename, max_depth=3):
    """Search for filename under base, handling PyInstaller's dir-wrapping.

    PyInstaller one-folder mode wraps each single-file data entry in a
    directory of the same name: e.g. datas ("app.py", "app.py") creates
    _internal/app_src/app.py/app.py.  Walk up to max_depth levels.
    """
    if os.path.isfile(os.path.join(base, filename)):
        return os.path.join(base, filename)
    # Check the PyInstaller-wrapped pattern: <dirname>/<filename>/<filename>
    wrapped = os.path.join(base, filename, filename)
    if os.path.isfile(wrapped):
        return wrapped
    # Broader search
    for root, dirs, files in os.walk(base):
        depth = root[len(base):].count(os.sep)
        if depth > max_depth:
            continue
        if filename in files:
            found = os.path.join(root, filename)
            _log.debug("walk-found %s at %s", filename, found)
            return found
    return None


def find_app_py():
    """Locate app.py — check exe dir first, then _internal/app_src/."""
    base = app_dir()
    # 1. Next to the exe (unlikely for frozen builds but cheap to check)
    result = _find_file_recursive(base, "app.py")
    if result:
        _log.info("Found app.py at: %s", result)
        return result

    # 2. Inside PyInstaller _MEIPASS extraction dir
    _int = internal_dir()
    if _int:
        app_src = os.path.join(_int, "app_src")
        if os.path.isdir(app_src):
            result = _find_file_recursive(app_src, "app.py")
            if result:
                _log.info("Found app.py at: %s", result)
                return result
        # Fallback: anywhere in _internal
        result = _find_file_recursive(_int, "app.py")
        if result:
            _log.info("Found app.py at: %s (fallback)", result)
            return result

    _log.error("app.py not found")
    return None


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
            _log.info("Created config.yaml from example")
        else:
            # Also check _internal/app_src/ for the example
            _int = internal_dir()
            if _int:
                for search_dir in [os.path.join(_int, "app_src"), _int]:
                    ex2 = os.path.join(search_dir, "config.example.yaml")
                    if os.path.isfile(ex2):
                        shutil.copyfile(ex2, cfg)
                        _log.info("Created config.yaml from %s", ex2)
                        break


def main():
    base = app_dir()
    _log.info("App dir: %s", base)

    ensure_config(base)

    app_py = find_app_py()
    if not app_py:
        show_error("Cannot find app.py.\n\nThe installation may be corrupted.\n\nSee launcher.log for details.")
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
    _log.info("Launching: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=base, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    server_up = wait_for_server(port)
    url = "http://127.0.0.1:{}".format(port)
    if server_up:
        _log.info("Server ready, opening browser: %s", url)
        webbrowser.open(url)
    else:
        _log.warning("Server did not start within timeout")

    if _HAS_TK:
        root = tk.Tk()
        root.title("Job Hunter")
        root.resizable(False, False)
        msg = ("Browser opened:\n{}\n\n"
               "Close this window to quit.".format(url))
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


def show_error(message):
    """Show error dialog — works even without tkinter via MessageBox."""
    shown = False
    if _HAS_TK:
        try:
            root = tk.Tk()
            root.withdraw()
            import tkinter.messagebox
            tkinter.messagebox.showerror("Job Hunter", message)
            root.destroy()
            shown = True
        except Exception:
            pass
    if not shown:
        # Last resort: write to log file
        try:
            log_path = os.path.join(app_dir(), "launcher.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("ERROR: " + message + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
