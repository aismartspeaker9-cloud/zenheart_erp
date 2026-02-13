"""
基础 Schema 模块
"""
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """统一响应格式"""
    success: bool = True
    code: int = 200
    data: Optional[T] = None
    message: str = "操作成功"
    
    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    """分页元数据"""
    total: int
    page: int
    page_size: int
    total_pages: int
    
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应格式"""
    success: bool = True
    code: int = 200
    data: list[T] = []
    meta: PaginationMeta
    message: str = "操作成功"
    
    model_config = ConfigDict(from_attributes=True)
