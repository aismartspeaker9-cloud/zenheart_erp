"""
数据库相关操作统一放在 models 目录。
"""
from app.models.connection import get_connection
from app.models.shopify_orders import (
    upsert_shopify_order,
    get_shopify_orders_by_created_at_range,
    get_shopify_order_by_id,
)
from app.models.orders import (
    delete_orders_by_shopify_order,
    get_orders_for_export,
    insert_order,
)

__all__ = [
    "get_connection",
    "upsert_shopify_order",
    "get_shopify_orders_by_created_at_range",
    "get_shopify_order_by_id",
    "delete_orders_by_shopify_order",
    "get_orders_for_export",
    "insert_order",
]
