"""
shopify_orders 表相关数据库操作。
"""
import json
from datetime import datetime
from typing import Any


def _parse_iso_ts(s: str | None):
    """将 Shopify ISO 时间串转为 datetime（asyncpg 需要 datetime 类型）。"""
    if not s:
        return None
    try:
        # '2026-02-14T01:13:02Z' -> 替换 Z 为 +00:00 以便 fromisoformat
        normalized = s.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def _order_created_at_from_raw(raw_data: dict) -> datetime | None:
    """从 raw_data 取 Shopify 订单创建时间并转为 datetime。"""
    s = raw_data.get("createdAt") or raw_data.get("created_at")
    return _parse_iso_ts(s)


def _order_updated_at_from_raw(raw_data: dict) -> datetime | None:
    """从 raw_data 取 Shopify 订单更新时间并转为 datetime。"""
    s = raw_data.get("updatedAt") or raw_data.get("updated_at")
    return _parse_iso_ts(s)


async def get_shopify_orders_by_created_at_range(
    conn: Any,
    shop_id: str,
    created_at_min: str,
    created_at_max: str,
) -> list[dict]:
    """
    按 shopify_orders.order_created_at 时间范围查询（分单用）。
    仅返回 order_created_at 在 [created_at_min, created_at_max] 内的记录。
    created_at_min / created_at_max 为 ISO 字符串，会转为 datetime 再传库。
    返回 list of {"shop_id", "shopify_order_id", "raw_data"}，raw_data 为 dict。
    """
    ts_min = _parse_iso_ts(created_at_min)
    ts_max = _parse_iso_ts(created_at_max)
    if ts_min is None or ts_max is None:
        return []
    rows = await conn.fetch(
        """
        SELECT shop_id, shopify_order_id, raw_data
        FROM shopify_orders
        WHERE shop_id = $1
          AND order_created_at IS NOT NULL
          AND order_created_at >= $2
          AND order_created_at <= $3
        ORDER BY order_created_at
        """,
        shop_id,
        ts_min,
        ts_max,
    )
    return [
        {"shop_id": r["shop_id"], "shopify_order_id": r["shopify_order_id"], "raw_data": r["raw_data"]}
        for r in rows
    ]


async def get_shopify_order_by_id(
    conn: Any,
    shop_id: str,
    shopify_order_id: int,
) -> dict | None:
    """
    按 shop_id + shopify_order_id 查询单条订单。
    返回 {"shop_id", "shopify_order_id", "raw_data"} 或 None。
    """
    row = await conn.fetchrow(
        """
        SELECT shop_id, shopify_order_id, raw_data
        FROM shopify_orders
        WHERE shop_id = $1 AND shopify_order_id = $2
        """,
        shop_id,
        shopify_order_id,
    )
    if row is None:
        return None
    return {"shop_id": row["shop_id"], "shopify_order_id": row["shopify_order_id"], "raw_data": row["raw_data"]}


async def upsert_shopify_order(
    conn: Any,
    shop_id: str,
    shopify_order_id: int,
    raw_data: dict,
) -> None:
    """
    插入或更新 shopify_orders。
    若 (shop_id, shopify_order_id) 已存在则更新 raw_data、order_created_at、order_updated_at 和 updated_at。
    order_created_at / order_updated_at 从 raw_data 的 createdAt/updatedAt（或 created_at/updated_at）解析。
    """
    order_created_at = _order_created_at_from_raw(raw_data)
    order_updated_at = _order_updated_at_from_raw(raw_data)
    await conn.execute(
        """
        INSERT INTO shopify_orders (shop_id, shopify_order_id, raw_data, order_created_at, order_updated_at, updated_at)
        VALUES ($1, $2, $3::jsonb, $4, $5, NOW())
        ON CONFLICT (shop_id, shopify_order_id)
        DO UPDATE SET
          raw_data = EXCLUDED.raw_data,
          order_created_at = EXCLUDED.order_created_at,
          order_updated_at = EXCLUDED.order_updated_at,
          updated_at = NOW()
        """,
        shop_id,
        shopify_order_id,
        json.dumps(raw_data, ensure_ascii=False),
        order_created_at,
        order_updated_at,
    )
