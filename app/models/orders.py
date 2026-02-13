"""
orders 表相关数据库操作。
"""
import json
from datetime import datetime
from typing import Any


async def delete_orders_by_shopify_order(
    conn: Any,
    shop_id: str,
    shopify_order_id: int,
) -> None:
    """删除指定 Shopify 订单对应的所有拆单记录。"""
    await conn.execute(
        "DELETE FROM orders WHERE shop_id = $1 AND shopify_order_id = $2",
        shop_id,
        shopify_order_id,
    )


async def insert_order(
    conn: Any,
    *,
    parent_order_no: str,
    sub_order_no: str,
    shop_id: str,
    shopify_order_id: int,
    total_amount: float,
    subtotal_amount: float,
    currency: str,
    payment_status: str | None,
    region: str,
    items_json: list | dict,
    customer_json: dict,
    order_created_at: datetime | None = None,
    discount_amount: float = 0,
) -> None:
    """插入一条拆单后的 order 记录。"""
    await conn.execute(
        """
        INSERT INTO orders (
            parent_order_no, sub_order_no, shop_id, shopify_order_id,
            total_amount, subtotal_amount, discount_amount, currency,
            payment_status, region, items_json, customer_json,
            order_created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13
        )
        """,
        parent_order_no,
        sub_order_no,
        shop_id,
        shopify_order_id,
        total_amount,
        subtotal_amount,
        discount_amount,
        (currency or "TWD")[:3],
        payment_status,
        region,
        json.dumps(items_json, ensure_ascii=False),
        json.dumps(customer_json, ensure_ascii=False),
        order_created_at,
    )
