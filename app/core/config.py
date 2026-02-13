"""
配置管理模块
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    """应用配置"""
    
    # 环境
    ENV: str = "dev"
    
    # 应用配置
    APP_NAME: str = "ZenHeart ERP"
    DEBUG: bool = True
    
    # 数据库配置（可选，测试时不需要）
    DATABASE_URL: Optional[str] = None
    
    # Shopify 配置
    SHOPIFY_STORE_NAME: str
    SHOPIFY_API_VERSION: str = "2026-01"
    # 方式一：Client Credentials 动态获取 token（推荐，.env 填这两项）
    SHOPIFY_CLIENT_ID: Optional[str] = None
    SHOPIFY_CLIENT_SECRET: Optional[str] = None
    # 方式二：直接使用静态 access token（与方式一二选一）
    SHOPIFY_ACCESS_TOKEN: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    @property
    def shopify_api_url(self) -> str:
        """Shopify API 基础 URL（REST，保留兼容）"""
        return f"https://{self.SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{self.SHOPIFY_API_VERSION}"

    @property
    def shopify_graphql_url(self) -> str:
        """Shopify Admin GraphQL API URL"""
        return f"https://{self.SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{self.SHOPIFY_API_VERSION}/graphql.json"

    @property
    def shopify_oauth_token_url(self) -> str:
        """OAuth access_token 端点（Client Credentials 用）"""
        return f"https://{self.SHOPIFY_STORE_NAME}.myshopify.com/admin/oauth/access_token"

    def use_client_credentials(self) -> bool:
        """是否使用 client_id + client_secret 动态获取 token"""
        return bool(self.SHOPIFY_CLIENT_ID and self.SHOPIFY_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
