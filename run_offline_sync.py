"""
离线任务：同步昨日14点～今日14点（北京时间）的 Shopify 订单，并按规格拆单写入 orders。

运行：python run_offline_sync.py
依赖：.env 中配置 DATABASE_URL、Shopify 认证；数据库已执行 app/schemas/tables.sql
"""
import asyncio
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv(Path(__file__).resolve().parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 规格(variant_title) -> 区域 映射
REGION_BY_SPEC: dict[str, str] = {
    "天壇天公廟": "台南",
    "艋舺龍山寺": "台北",
    "慈鳳宮": "屏東",
    "聖帝廟": "屏東",
    "屏東孔廟": "屏東",
    "佛光山": "高雄",
}
OTHER_REGION = "其他"


def _beijing_time_range() -> tuple[str, str]:
    """北京时间：昨天 14:00 ～ 今天 14:00，转为 ISO 字符串供 Shopify query 使用"""
    beijing = timezone(timedelta(hours=8))
    now_bj = datetime.now(beijing)
    today = now_bj.date()
    yesterday = today - timedelta(days=1)
    start_bj = datetime(yesterday.year, yesterday.month, yesterday.day, 14, 0, 0, 0, tzinfo=beijing)
    end_bj = datetime(today.year, today.month, today.day, 14, 0, 0, 0, tzinfo=beijing)
    start_utc = start_bj.astimezone(timezone.utc)
    end_utc = end_bj.astimezone(timezone.utc)
    # Shopify created_at 格式
    return start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _group_line_items_by_region(line_items: list[dict]) -> dict[str, list[dict]]:
    """按规格映射到区域，同一区域的商品分在一组；不在映射内的归为「其他」一单。"""
    groups: dict[str, list[dict]] = {}
    for item in line_items:
        spec = (item.get("variant_title") or "").strip()
        region = REGION_BY_SPEC.get(spec, OTHER_REGION)
        if region not in groups:
            groups[region] = []
        groups[region].append(item)
    return groups


def _raw_to_customer_json(raw: dict) -> dict:
    addr = raw.get("shipping_address") or {}
    return {
        "name": addr.get("name"),
        "email": raw.get("email"),
        "phone": addr.get("phone") or raw.get("phone"),
        "address1": addr.get("address1"),
        "address2": addr.get("address2"),
        "city": addr.get("city"),
        "province": addr.get("province"),
        "zip": addr.get("zip"),
        "country": addr.get("country"),
        "countryCodeV2": addr.get("countryCodeV2"),
    }


def _items_subtotal(items: list[dict]) -> float:
    """行项目折后小计（优先 discounted_total，否则 price*quantity）"""
    total = 0.0
    for it in items:
        try:
            disc = it.get("discounted_total")
            if disc is not None and str(disc).strip():
                total += float(disc)
            else:
                total += float(it.get("price") or 0) * int(it.get("quantity") or 0)
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def _parse_created_at(created_at: str | None):
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return None


async def run_offline_sync():
    from app.core.config import get_settings
    from app.models import get_connection, upsert_shopify_order, delete_orders_by_shopify_order, insert_order
    from app.services.shopify_service import ShopifyService
    from app.schemas.shopify import ShopifyOrderResponse

    settings = get_settings()
    shop_id = f"{settings.SHOPIFY_STORE_NAME}.myshopify.com"
    created_at_min, created_at_max = _beijing_time_range()
    logger.info(f"时间范围(北京时间 昨日14:00～今日14:00): {created_at_min} ~ {created_at_max} UTC")

    # 1) 拉取 Shopify 订单
    service = ShopifyService()
    orders = await service.get_orders(
        limit=250,
        status="any",
        created_at_min=created_at_min,
        created_at_max=created_at_max,
    )
    logger.info(f"拉取到 {len(orders)} 条 Shopify 订单")

    if not orders:
        logger.info("无订单，结束")
        return

    conn = await get_connection()
    try:
        for order in orders:
            if not isinstance(order, ShopifyOrderResponse):
                continue
            raw_data = order.model_dump(mode="json")
            shopify_order_id = order.id

            # 2) Upsert shopify_orders（重复则更新）
            await upsert_shopify_order(conn, shop_id, shopify_order_id, raw_data)
            logger.info(f"  shopify_orders upsert: shopify_order_id={shopify_order_id}")

            # 3) 拆单：先删该 Shopify 订单对应的所有子单，再按区域插入
            await delete_orders_by_shopify_order(conn, shop_id, shopify_order_id)
            groups = _group_line_items_by_region(order.line_items)
            if not groups:
                groups = {OTHER_REGION: []}
            parent_order_no = str(uuid.uuid1())
            customer_json = _raw_to_customer_json(raw_data)
            order_created_at = _parse_created_at(order.created_at)
            currency = (order.currency or "TWD")[:3]
            payment_status = order.financial_status

            for i, (region, items) in enumerate(sorted(groups.items(), key=lambda x: (x[0] == OTHER_REGION, x[0])), 1):
                sub_order_no = f"{parent_order_no}-{i}"
                subtotal_amount = _items_subtotal(items)
                await insert_order(
                    conn,
                    parent_order_no=parent_order_no,
                    sub_order_no=sub_order_no,
                    shop_id=shop_id,
                    shopify_order_id=shopify_order_id,
                    total_amount=subtotal_amount,
                    subtotal_amount=subtotal_amount,
                    currency=currency,
                    payment_status=payment_status,
                    region=region,
                    items_json=items,
                    customer_json=customer_json,
                    order_created_at=order_created_at,
                )
                logger.info(f"    orders 拆单: sub_order_no={sub_order_no} region={region} items={len(items)}")
    finally:
        await conn.close()

    logger.info("离线同步+拆单完成")


if __name__ == "__main__":
    asyncio.run(run_offline_sync())
