"""
个人信息存储抽象（意见 G-6）——首次运行选择存放位置，之后免重复上传。

- LocalProfileStore：存在本地目录（默认 data/profile/），开箱即用。
- CloudProfileStore：预留云端同步接口（本期不实现后端，仅留契约），
  将来接对象存储/OSS/S3 时实现同名方法即可，页面无需改动。

页面统一通过 get_profile_store() 获取实例，不关心底层是本地还是云。
"""

import json
from pathlib import Path
from typing import Protocol, runtime_checkable


DEFAULT_PROFILE_DIR = Path(__file__).parent.parent / "data" / "profile"
PROFILE_CONFIG_PATH = Path(__file__).parent.parent / "data" / "profile_config.json"


@runtime_checkable
class ProfileStore(Protocol):
    """个人信息存储契约。本地与云端实现都满足此接口。"""

    root: Path

    def list_resumes(self) -> list[Path]:
        """返回已保存的简历文件列表。"""
        ...

    def save_resume(self, filename: str, data: bytes) -> Path:
        """保存简历原始文件，返回路径。"""
        ...

    def load_parsed(self) -> dict | None:
        """读取已解析的结构化简历（resume_parsed.json）。"""
        ...

    def save_parsed(self, parsed: dict) -> Path:
        """写入解析后的结构化简历。"""
        ...


class LocalProfileStore:
    """本地目录实现。"""

    def __init__(self, root: Path = None):
        self.root = Path(root) if root else DEFAULT_PROFILE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def list_resumes(self) -> list[Path]:
        return sorted(self.root.glob("resume.*")) + sorted(self.root.glob("*.pdf")) \
            + sorted(self.root.glob("*.docx")) + sorted(self.root.glob("*.txt"))

    def save_resume(self, filename: str, data: bytes) -> Path:
        path = self.root / filename
        with open(path, "wb") as f:
            f.write(data)
        return path

    def load_parsed(self) -> dict | None:
        cache = self.root / "resume_parsed.json"
        if cache.exists():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def save_parsed(self, parsed: dict) -> Path:
        cache = self.root / "resume_parsed.json"
        cache.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        return cache


class CloudProfileStore:
    """
    云端存储接口预留（意见 G-6 决策 B：本地 + 预留云同步接口）。

    本期不接具体后端。实现时替换 __init__ 里的客户端，并保持方法签名一致，
    页面调用 get_profile_store() 无需改动即可切换到云端。
    """

    def __init__(self, root: Path = None, endpoint: str = "", token: str = ""):
        # 本地兜底目录：云端不可用时仍能工作
        self.root = Path(root) if root else DEFAULT_PROFILE_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.endpoint = endpoint
        self.token = token
        # TODO(云端): 初始化对象存储客户端（如 boto3 / oss2），读取 endpoint+token

    def list_resumes(self) -> list[Path]:
        # TODO(云端): 列出云端对象；此处回退本地
        return LocalProfileStore(self.root).list_resumes()

    def save_resume(self, filename: str, data: bytes) -> Path:
        path = LocalProfileStore(self.root).save_resume(filename, data)
        # TODO(云端): 同时上传到云端对象存储
        return path

    def load_parsed(self) -> dict | None:
        return LocalProfileStore(self.root).load_parsed()

    def save_parsed(self, parsed: dict) -> Path:
        return LocalProfileStore(self.root).save_parsed(parsed)


def save_profile_config(root: str, backend: str = "local") -> None:
    """把用户选择持久化到 data/profile_config.json。"""
    PROFILE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_CONFIG_PATH.write_text(
        json.dumps({"backend": backend, "root": str(root)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_profile_config() -> dict | None:
    if PROFILE_CONFIG_PATH.exists():
        try:
            return json.loads(PROFILE_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def get_profile_store() -> ProfileStore:
    """
    返回当前配置的个人存储实例。
    首次运行未配置时回退到默认本地目录（页面会弹窗引导用户选择）。
    """
    cfg = load_profile_config()
    if cfg and cfg.get("root"):
        root = Path(cfg["root"])
        if cfg.get("backend") == "cloud":
            return CloudProfileStore(root)
        return LocalProfileStore(root)
    return LocalProfileStore(DEFAULT_PROFILE_DIR)
