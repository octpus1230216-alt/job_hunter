"""ingest_resume.py — 上传并解析原简历（FR9）。

把你的原简历（.doc/.docx/.pdf/.txt/.md/.tex）解析为纯文本，存入 resumes 表作为基准版本，
供 score --profile / revise 对照 JD 指出不足、生成改稿。

双通道降级：当系统没有对应解析器（如未装 poppler / libreoffice）时，打印
「贴给 WorkBuddy 提取文本」的提示词，由用户回填 .txt 后重新上传，保持免 key 可跑。

用法：
  python ingest_resume.py upload <原简历.pdf/.docx/.txt> [--version orig] [--db <path>]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from modules.store import DEFAULT_DB, add_resume, init_db

ROOT = Path(__file__).resolve().parent

TEXT_EXTS = {".txt", ".md", ".tex"}
SUPPORTED = sorted(TEXT_EXTS | {".pdf", ".doc", ".docx"})


class ResumeParseError(Exception):
    """解析失败时抛出，便于上层降级为双通道提示词。"""


def _today() -> str:
    return date.today().isoformat()


def parse_resume(path: Path) -> str:
    """按扩展名分发解析器，返回纯文本；无法解析抛 ResumeParseError。"""
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    if ext == ".pdf":
        return _parse_pdf(path)
    if ext in (".doc", ".docx"):
        return _parse_doc(path)
    raise ResumeParseError(
        f"不支持的扩展名 {ext}（支持：{', '.join(SUPPORTED)}）。"
        "可先把简历另存为 .txt/.md，或贴给 WorkBuddy 提取文本后存为 .txt 再上传。"
    )


def _parse_pdf(path: Path) -> str:
    if not shutil.which("pdftotext"):
        raise ResumeParseError(
            "未检测到 pdftotext（poppler）。请安装 poppler 后重试，"
            "或把简历贴给 WorkBuddy 提取为文本后存成 .txt 再上传。"
        )
    out = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True)
    if out.returncode != 0:
        raise ResumeParseError(f"pdftotext 执行失败：{out.stderr.strip()}")
    text = out.stdout.strip()
    if not text:
        raise ResumeParseError(
            "PDF 文本层为空（疑似扫描件/图片型 PDF）。请走双通道：把 PDF 截图发给 WorkBuddy 做 OCR 提取文本，"
            "存为 .txt 后重新上传。"
        )
    return text


def _parse_doc(path: Path) -> str:
    # 优先 macOS 自带 textutil
    if shutil.which("textutil"):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            out_file = Path(tmp.name)
        try:
            res = subprocess.run(
                ["textutil", "-convert", "txt", "-output", str(out_file), str(path)],
                capture_output=True, text=True,
            )
            if res.returncode == 0 and out_file.exists():
                text = out_file.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return text
                raise ResumeParseError("textutil 提取结果为空，请检查文件是否损坏。")
            raise ResumeParseError(f"textutil 转换失败：{res.stderr.strip()}")
        finally:
            out_file.unlink(missing_ok=True)
    # 其次 LibreOffice（跨平台）
    if shutil.which("libreoffice"):
        with tempfile.TemporaryDirectory() as td:
            res = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "txt:Text", "--outdir", td, str(path)],
                capture_output=True, text=True,
            )
            files = list(Path(td).glob("*.txt"))
            if files:
                return files[0].read_text(encoding="utf-8", errors="replace").strip()
            raise ResumeParseError(f"libreoffice 转换失败：{res.stderr.strip()}")
    raise ResumeParseError(
        "未检测到 textutil(macOS) 或 libreoffice，无法解析 doc/docx。"
        "请安装其一，或把简历贴给 WorkBuddy 提取为文本后存成 .txt 再上传。"
    )


def print_export_prompt(path: Path) -> None:
    print(
        "\n--- 双通道降级：把简历文本交给 WorkBuddy 提取 ---\n"
        "把你的简历（或截图）发给 WorkBuddy，请它『提取为纯文本简历』，\n"
        "把结果保存为 resume.txt，然后重新运行：\n"
        f"    python ingest_resume.py upload resume.txt --version orig\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="ingest_resume.py — 上传并解析原简历（FR9）")
    sub = ap.add_subparsers(dest="cmd")
    p_up = sub.add_parser("upload", help="上传原简历文件并解析为文本")
    p_up.add_argument("file", help="原简历文件路径（.doc/.docx/.pdf/.txt/.md/.tex）")
    p_up.add_argument("--version", default="orig", help="存入的简历版本号（默认 orig）")
    p_up.add_argument("--db", default="", help="SQLite 路径（默认 data/job_search.db）")
    args = ap.parse_args()

    if args.cmd != "upload":
        ap.print_help()
        return

    path = Path(args.file)
    if not path.exists():
        print(f"❌ 文件不存在：{path}")
        sys.exit(1)

    conn = init_db(Path(args.db) if args.db else DEFAULT_DB)
    try:
        text = parse_resume(path)
    except ResumeParseError as e:
        print(f"⚠️ 无法自动解析：{e}")
        print_export_prompt(path)
        conn.close()
        sys.exit(2)

    add_resume(
        conn, args.version, text, _today(),
        change_log=f"上传原简历（{path.name}）",
        source_file=str(path), source_format=path.suffix.lower().lstrip("."),
    )
    conn.close()
    print(f"✅ 已上传原简历为版本 `{args.version}`（{len(text)} 字，来源 {path.name}）")
    print("下一步：")
    print("  · 评分：python score.py --all              （默认取最新简历作 profile）")
    print("  · 改简历/指出不足：python revise.py --id <岗位id>  （对照该岗位 JD 与原简历）")
    print(f"  · 导出：python export.py --version {args.version}")


if __name__ == "__main__":
    main()
