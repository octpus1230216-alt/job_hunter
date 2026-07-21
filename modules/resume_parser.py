"""
简历解析模块 - 支持 PDF、DOCX 格式
提取简历的结构化信息：技能、经验、项目、学历
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Optional

class ResumeParser:
    """简历解析器 - 提取结构化信息"""

    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_cache = data_dir / "resume_parsed.json"

    def parse(self, file_path: str, llm_client=None) -> dict:
        """
        解析简历文件
        1. 先用 PyPDF2/python-docx 提取纯文本
        2. 再用 LLM 结构化
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"简历文件不存在: {file_path}")

        # 检查缓存（基于文件内容哈希）
        file_hash = self._hash_file(str(file_path))
        cached = self._load_cache()
        if cached and cached.get("file_hash") == file_hash:
            return cached.get("data", {})

        # 第一步：提取文本
        raw_text = self._extract_text(str(file_path))

        # 第二步：LLM 结构化（如果提供）
        if llm_client:
            try:
                structured = self._structure_with_llm(raw_text, llm_client)
            except Exception as e:
                # AI 结构化失败时不让整页崩，回退到纯文本
                structured = {
                    "raw_text": raw_text,
                    "llm_error": f"AI 结构化失败，已回退纯文本: {e}",
                }
        else:
            structured = {"raw_text": raw_text}

        # 保存缓存
        self._save_cache(file_hash, structured)

        return structured

    def _extract_text(self, file_path: str) -> str:
        """从文件提取纯文本"""
        ext = Path(file_path).suffix.lower()

        if ext == ".pdf":
            return self._extract_pdf(file_path)
        elif ext in (".docx", ".doc"):
            return self._extract_docx(file_path)
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            raise ValueError(f"不支持的简历格式: {ext}")

    def _extract_pdf(self, file_path: str) -> str:
        """从 PDF 提取文本"""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n\n".join(text_parts)
        except Exception as e:
            raise RuntimeError(f"PDF 解析失败: {e}")

    def _extract_docx(self, file_path: str) -> str:
        """从 DOCX 提取文本"""
        try:
            from docx import Document
            doc = Document(file_path)
            text_parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)
            return "\n".join(text_parts)
        except Exception as e:
            raise RuntimeError(f"DOCX 解析失败: {e}")

    def _structure_with_llm(self, raw_text: str, llm_client) -> dict:
        """使用 LLM 结构化简历内容"""
        system_prompt = """你是一位简历解析专家。从以下简历文本中提取结构化信息。

规则：
1. 不要编造任何信息，只提取文本中明确提到的内容
2. 如果某项信息不存在，用空数组 [] 或不填
3. 技能列表要具体（如"Python"而非"编程"）
4. 工作经验中的要点要量化（如果有数字的话）

返回 JSON 格式，必须严格按照以下结构：
{
  "name": "姓名",
  "email": "邮箱",
  "phone": "电话",
  "location": "所在城市",
  "linkedin": "LinkedIn URL（如有）",
  "github": "GitHub URL（如有）",
  "summary": "个人总结/求职目标（原文）",
  "skills": {
    "languages": ["编程语言"],
    "frameworks": ["框架和库"],
    "tools": ["工具和平台"],
    "soft_skills": ["软技能"],
    "languages_spoken": ["语言能力"]
  },
  "experience": [
    {
      "company": "公司名",
      "title": "职位",
      "start_date": "开始时间",
      "end_date": "结束时间（或 '至今'）",
      "location": "工作地点",
      "bullets": ["工作内容和成果（逐条）"]
    }
  ],
  "projects": [
    {
      "name": "项目名",
      "description": "项目描述",
      "tech_stack": ["使用的技术"],
      "highlights": ["项目亮点/成果"]
    }
  ],
  "education": [
    {
      "school": "学校",
      "degree": "学位",
      "major": "专业",
      "start_date": "开始时间",
      "end_date": "结束时间"
    }
  ],
  "certifications": ["证书列表"],
  "total_years_experience": "总工作年限（估计）"
}"""

        return llm_client.chat_json(system_prompt, raw_text)

    def _hash_file(self, file_path: str) -> str:
        """计算文件 SHA256"""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _load_cache(self) -> Optional[dict]:
        """加载缓存"""
        if self.parsed_cache.exists():
            with open(self.parsed_cache, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_cache(self, file_hash: str, data: dict):
        """保存缓存"""
        cache = {"file_hash": file_hash, "data": data}
        with open(self.parsed_cache, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
