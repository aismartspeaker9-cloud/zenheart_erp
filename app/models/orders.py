"""
orders 表相关数据库操作。
"""
import json
from datetime import datetime
from typing import Any


async def get_orders_for_export(
    conn: Any,
    shop_id: str,
    *,
    order_created_at_min: datetime | None = None,
    order_created_at_max: datetime | None = None,
    shopify_order_id: int | None = None,
) -> list[dict]:
    """
    查询订单用于导出 CSV。
    按 order_created_at 时间范围或按 shopify_order_id 筛选。
    返回 list of 订单行（含 items_json, customer_json, extra_info, order_created_at 等）。
    """
    if shopify_order_id is not None:
        rows = await conn.fetch(
            """
            SELECT id, parent_order_no, sub_order_no, shop_id, shopify_order_id,
                   items_json, customer_json, extra_info, order_created_at
            FROM orders
            WHERE shop_id = $1 AND shopify_order_id = $2
            ORDER BY sub_order_no
            """,
            shop_id,
            shopify_order_id,
        )
    else:
        if order_created_at_min is None or order_created_at_max is None:
            return []
        rows = await conn.fetch(
            """
            SELECT id, parent_order_no, sub_order_no, shop_id, shopify_order_id,
                   items_json, customer_json, extra_info, order_created_at
            FROM orders
            WHERE shop_id = $1
              AND order_created_at >= $2 AND order_created_at <= $3
            ORDER BY order_created_at, sub_order_no
            """,
            shop_id,
            order_created_at_min,
            order_created_at_max,
        )
    return [dict(r) for r in rows]


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
    shipping_address: dict | None = None,
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
            shipping_fee, shipping_address,
            items_json, customer_json, marketing_json, delivery_config, extra_info,
            order_created_at, order_updated_at
        ) VALUES (
            $1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11::jsonb,
            $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb,
            $17, $18
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
        json.dumps(shipping_address, ensure_ascii=False) if shipping_address is not None else None,
        json.dumps(items_json, ensure_ascii=False),
        json.dumps(customer_json, ensure_ascii=False),
        json.dumps(marketing_json, ensure_ascii=False) if marketing_json is not None else None,
        json.dumps(delivery_config, ensure_ascii=False) if delivery_config is not None else None,
        json.dumps(extra_info, ensure_ascii=False) if extra_info is not None else None,
        order_created_at,
        order_updated_at,
    )
