"""
数据库连接（asyncpg），供离线任务及后续 DB 操作使用。
"""
import os
from typing import Any

from app.core.config import get_settings


async def get_connection() -> Any:
    """
    获取 asyncpg 连接。
    使用前需确保 DATABASE_URL 已配置（.env 或环境变量）。
    """
    import asyncpg

    settings = get_settings()
    url = settings.DATABASE_URL
    if not url:
        raise RuntimeError("未设置 DATABASE_URL")
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return await asyncpg.connect(url)
