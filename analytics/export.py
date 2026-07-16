"""export.py — 简历导出 LaTeX + ATS 校验（借 MadsLorentzen verify_pdf.py 思路）。

  python export.py --version v2 --out data/resume_v2.tex     # 生成 LaTeX 简历
  python export.py --version v2 --compile                    # 尝试编译成 PDF（需 lualatex/pdflatex）
  python export.py --ats --version v2 --jd 3                 # ATS 关键词覆盖率（纯 Python，免 poppler）

说明：LaTeX 模板极简、避免花哨宏包，确保文本层干净（ATS 友好）。
无 lualatex 时只产出 .tex 并打印安装提示，不报错中断。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from modules.store import DEFAULT_DB, init_db, get_resume, get_by_id

ROOT = Path(__file__).resolve().parent


# ---------- 关键词抽取（纯 Python） ----------
def _tokens(text: str) -> set:
    text = re.sub(r"[\s，。、；：,.;:!！?？()（）\[\]【】\"'\"'/\\|]+", " ", text.lower())
    return {chunk for chunk in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text) if len(chunk) >= 2}


def _escape_tex(text: str) -> str:
    """转义 LaTeX 特殊字符，避免编译失败 / 文本层乱码。"""
    repl = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = []
    for ch in text:
        out.append(repl.get(ch, ch))
    return "".join(out)


LATEX_TEMPLATE = r"""\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=2cm]{{geometry}}
\usepackage[UTF8]{{ctex}}   % 中文支持（本机无 ctex 时删此行，改用 XeLaTeX/LuaLaTeX + 字体）
\setlength{{\parindent}}{{0pt}}
\begin{{document}}

\section*{{{title}}}

{body}

\end{{document}}
"""


def resume_to_latex(version: str, text: str) -> str:
    # 把简历纯文本按空行分段，逐段转 paragraph；简单但文本层干净
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    body = "\n\n".join(_escape_tex(p) for p in paras)
    return LATEX_TEMPLATE.format(title=_escape_tex(f"简历 {version}"), body=body)


def ats_coverage(jd_text: str, resume_text: str) -> dict:
    """纯 Python 关键词覆盖率：JD 关键词在简历里出现的比例 + 缺失清单。"""
    jd = _tokens(jd_text or "")
    rs = _tokens(resume_text or "")
    if not jd:
        return {"coverage": 0.0, "missing": [], "total": 0}
    hit = jd & rs
    missing = sorted(jd - rs)
    coverage = round(len(hit) / len(jd) * 100, 1)
    return {"coverage": coverage, "missing": missing, "total": len(jd)}


def main() -> None:
    ap = argparse.ArgumentParser(description="export.py — LaTeX 导出 + ATS 校验")
    ap.add_argument("--version", default="", help="简历版本号（如 v2）")
    ap.add_argument("--out", default="", help=".tex 输出路径")
    ap.add_argument("--compile", action="store_true", help="尝试编译成 PDF（需 lualatex/pdflatex）")
    ap.add_argument("--ats", action="store_true", help="做 ATS 关键词覆盖率检查")
    ap.add_argument("--jd", type=int, default=0, help="ATS 检查用的岗位 id（JD 文本来源）")
    args = ap.parse_args()

    conn = init_db()
    if not args.version:
        print("请指定 --version（如 v2）。")
        conn.close()
        return
    row = get_resume(conn, args.version)
    if not row:
        print(f"未找到简历版本 {args.version}")
        conn.close()
        return
    resume_text = row["text"] or ""

    # ATS 检查（纯 Python，免 poppler）
    if args.ats:
        jd_row = get_by_id(conn, args.jd) if args.jd else None
        jd_text = jd_row["jd_text"] if jd_row else ""
        if not jd_text:
            print("未提供有效 --jd，无法算覆盖率（或用 collect 录入带 jd_text 的岗位）。")
        else:
            res = ats_coverage(jd_text, resume_text)
            print(f"ATS 关键词覆盖率（简历 {args.version} vs 岗位 {args.jd}）：{res['coverage']}% "
                  f"（{len(res['missing'])}/{res['total']} 关键词缺失）")
            if res["missing"]:
                print("缺失关键词：" + "、".join(res["missing"][:20]))
            # 若有已编译 PDF，尝试 pdftotext 抽文本层
            pdf = ROOT / f"data/resume_{args.version}.pdf"
            if pdf.exists() and shutil.which("pdftotext"):
                out = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True)
                txt = out.stdout
                cid = txt.count("cid") + txt.count("(cid")
                print(f"PDF 文本层抽取成功，字符数 {len(txt)}，乱码标记(cid) {cid}"
                      f"{' ⚠️ 有乱码' if cid else ' ✅ 干净'}")
            else:
                print("（未编译 PDF 或无 pdftotext，跳过文本层检查；关键词覆盖率已足够判断 ATS 覆盖）")
        conn.close()
        return

    # 生成 LaTeX
    tex = resume_to_latex(args.version, resume_text)
    out = Path(args.out) if args.out else ROOT / f"data/resume_{args.version}.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tex, encoding="utf-8")
    print(f"✅ LaTeX 已写入 {out}")

    if args.compile:
        engine = shutil.which("lualatex") or shutil.which("pdflatex") or shutil.which("xelatex")
        if not engine:
            print("⚠️ 未检测到 lualatex/pdflatex/xelatex，跳过编译。安装 TinyTeX 后可编译 PDF。")
        else:
            r = subprocess.run([engine, "-interaction=nonstopmode", "-output-directory",
                                str(out.parent), str(out)], capture_output=True, text=True)
            pdf = out.with_suffix(".pdf")
            if pdf.exists():
                print(f"✅ PDF 已生成 {pdf}")
            else:
                print("⚠️ 编译未产出 PDF，可能缺 ctex 宏包或字体。原始 .tex 已保留。")
                print(r.stdout[-800:] if r.stdout else "")
    else:
        print("（未加 --compile，仅生成 .tex。要 PDF 加 --compile）")
    conn.close()


if __name__ == "__main__":
    main()
