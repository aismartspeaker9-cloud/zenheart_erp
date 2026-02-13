"""
shopify_orders 表相关数据库操作。
"""
import json
from typing import Any


async def upsert_shopify_order(
    conn: Any,
    shop_id: str,
    shopify_order_id: int,
    raw_data: dict,
) -> None:
    """
    插入或更新 shopify_orders。
    若 (shop_id, shopify_order_id) 已存在则更新 raw_data 和 updated_at。
    """
    await conn.execute(
        """
        INSERT INTO shopify_orders (shop_id, shopify_order_id, raw_data, updated_at)
        VALUES ($1, $2, $3::jsonb, NOW())
        ON CONFLICT (shop_id, shopify_order_id)
        DO UPDATE SET raw_data = EXCLUDED.raw_data, updated_at = NOW()
        """,
        shop_id,
        shopify_order_id,
        json.dumps(raw_data, ensure_ascii=False),
    )
