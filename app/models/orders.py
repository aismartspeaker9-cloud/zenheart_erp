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
    amount: dict,
    currency: str,
    payment_status: str | None,
    region: str,
    items_json: list | dict,
    customer_json: dict,
    order_created_at: datetime | None = None,
    order_updated_at: datetime | None = None,
    shipping_fee: float = 0,
    payment_method: str | None = None,
    marketing_json: dict | list | None = None,
    delivery_config: dict | list | None = None,
    extra_info: dict | None = None,
) -> None:
    """
    插入一条拆单后的 order 记录。
    amount: 原始总订单折前/折后、子订单折前/折后、每 SKU 折前/折后
      - order_original_total: 原始总订单折前金额
      - order_discounted_total: 原始总订单折后金额
      - sub_order_original_total: 本子订单折前金额
      - sub_order_discounted_total: 本子订单折后金额
      - items: [{ "sku_id", "original_total", "discounted_total" }]
    shipping_fee 建议取自 shippingLine.discountedPriceSet.presentmentMoney.amount。
    """
    await conn.execute(
        """
        INSERT INTO orders (
            parent_order_no, sub_order_no, shop_id, shopify_order_id,
            amount, currency, payment_status, payment_method, region,
            shipping_fee,
            items_json, customer_json, marketing_json, delivery_config, extra_info,
            order_created_at, order_updated_at
        ) VALUES (
            $1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10,
            $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb,
            $16, $17
        )
        """,
        parent_order_no,
        sub_order_no,
        shop_id,
        shopify_order_id,
        json.dumps(amount, ensure_ascii=False),
        (currency or "TWD")[:3],
        payment_status,
        payment_method,
        region,
        shipping_fee,
        json.dumps(items_json, ensure_ascii=False),
        json.dumps(customer_json, ensure_ascii=False),
        json.dumps(marketing_json, ensure_ascii=False) if marketing_json is not None else None,
        json.dumps(delivery_config, ensure_ascii=False) if delivery_config is not None else None,
        json.dumps(extra_info, ensure_ascii=False) if extra_info is not None else None,
        order_created_at,
        order_updated_at,
    )
