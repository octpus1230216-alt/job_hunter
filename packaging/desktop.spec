# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the job_hunter desktop build (one-folder).

The whole application (app.py, pages/, modules/, analytics/, config.example.yaml,
.streamlit/) is bundled as *data* next to the frozen launcher and loaded at
runtime from sys.path. This avoids PyInstaller trying to resolve the optional
heavy native imports (jobspy / playwright / tls_client / ollama), which are
lazy-loaded inside functions and simply unavailable in the desktop build.
"""
import os
from PyInstaller.utils.hooks import collect_all

# Robustly locate repo root by walking UP from the spec file itself
# until we find app.py. Works regardless of CWD / checkout depth.
_spec_file = os.path.abspath(SPECPATH)
_walk = os.path.dirname(_spec_file)
APP_ROOT = None
while _walk and _walk != os.path.dirname(_walk):
    if os.path.isfile(os.path.join(_walk, "app.py")):
        APP_ROOT = _walk
        break
    _walk = os.path.dirname(_walk)
if APP_ROOT is None:
    APP_ROOT = os.getcwd()  # last resort

block_cipher = None

# ---- data files bundled alongside the frozen launcher ----
# All app sources go under "app_src/" inside _internal to avoid
# PyInstaller creating spurious directories for single-file entries.
datas = []
_APP_SRC = "app_src"
entries = [
    ("app.py", "app.py"),
    ("pages", "pages"),
    ("modules", "modules"),
    ("analytics", "analytics"),
    ("recommender_run.py", "recommender_run.py"),
    ("README.md", "README.md"),
    ("requirements.txt", "requirements.txt"),
    (".streamlit", ".streamlit"),
]
for src_name, dst_name in entries:
    src = os.path.join(APP_ROOT, src_name)
    if os.path.isdir(src):
        datas.append((src, os.path.join(_APP_SRC, dst_name)))
    elif os.path.isfile(src):
        datas.append((src, os.path.join(_APP_SRC, dst_name)))

# config.yaml is gitignored (may contain a real key); ship the key-free example instead.
example_cfg = os.path.join(APP_ROOT, "config.example.yaml")
if os.path.isfile(example_cfg):
    datas.append((example_cfg, os.path.join(_APP_SRC, "config.yaml")))

# ---- Streamlit's static frontend assets MUST be bundled ----
try:
    st_datas, st_bins, st_hidden = collect_all("streamlit")
    datas += st_datas
    binaries = st_bins
    hiddenimports = list(st_hidden)
except Exception:
    binaries = []
    hiddenimports = []

hiddenimports += [
    "streamlit",
    "streamlit.web.cli",
    "streamlit.web.bootstrap",
    "streamlit.runtime",
    "streamlit.runtime.caching",
    "streamlit.runtime.scriptrunner",
    "streamlit.runtime.state",
    "streamlit.elements",
    "streamlit.components",
    "streamlit.delta_generator",
    "streamlit.session_state",
    "streamlit.config",
    "streamlit.util",
    "altair",
    "pyarrow",
    "pandas",
    "numpy",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "PIL",
    "PIL.Image",
    "tenacity",
    "toml",
    "validators",
    "protobuf",
    "yaml",
    "jinja2",
    "markdownify",
    "regex",
    "requests",
    "httpx",
    "bs4",
    "lxml",
    "rich",
    "openai",
    "docx",
    "PyPDF2",
]

a = Analysis(
    [os.path.join(APP_ROOT, "desktop", "launcher.py")],
    pathex=[APP_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "jobspy",
        "playwright",
        "tls_client",
        "ollama",
        "greenlet",
        "unittest",
        "test",
        "tests",
        "doctest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="job_hunter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="job_hunter",
)
