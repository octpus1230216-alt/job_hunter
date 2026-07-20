"""可选访问鉴权（成熟产品的边界防护）。

启用方式（二选一）：
- 环境变量：  export JOBHUNTER_PASSWORD=你的密码
- Streamlit secrets： 在 .streamlit/secrets.toml 写  password = "你的密码"

未设置密码时完全开放（默认，适合本地单机使用）。
密码以 SHA-256 比对，不落盘、不入日志。
"""

import hashlib
import os

import streamlit as st


def _get_password() -> str:
    pw = os.getenv("JOBHUNTER_PASSWORD", "") or ""
    if pw:
        return pw
    try:
        pw = st.secrets.get("password", "") if hasattr(st, "secrets") else ""
    except Exception:
        pw = ""
    return pw or ""


def require_auth() -> None:
    """在页面顶部调用。若启用了密码且未通过验证，则 st.stop() 阻断渲染。"""
    pw = _get_password()
    if not pw:
        return
    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    if st.session_state.auth_ok:
        return

    st.title("🔒 访问验证")
    st.caption("本应用已启用访问密码（来自 JOBHUNTER_PASSWORD 或 Streamlit secrets）。")
    pwd = st.text_input("请输入访问密码", type="password")
    if st.button("进入"):
        if hashlib.sha256(pwd.encode("utf-8")).hexdigest() == \
                hashlib.sha256(pw.encode("utf-8")).hexdigest():
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()
