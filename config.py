# -*- coding: utf-8 -*-
"""应用配置。

支持从项目根目录的 .env 文件读取配置（KEY=VALUE 形式，不依赖第三方库）。
环境变量优先级高于 .env 文件。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """极简 .env 加载器：只处理 KEY=VALUE，忽略注释与空行。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # 数据库默认放在 instance/ 下，避免误提交
    DATABASE = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "meetings.db"))

    # DeepSeek（OpenAI 兼容接口）
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT", "60"))
    AI_MAX_TRANSCRIPT_CHARS = int(os.environ.get("AI_MAX_TRANSCRIPT_CHARS", "60000"))

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 单次请求最大 2 MB
    JSON_AS_ASCII = False
