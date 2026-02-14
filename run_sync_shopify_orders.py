"""
脚本1：每 10 秒轮询同步 Shopify 原始订单到 shopify_orders 表。
时间范围：默认最近 1 天（昨日 14:00～今日 14:00 北京时间），可通过 -n 指定天数。

运行：python run_sync_shopify_orders.py [-n 天数，默认 1]
依赖：.env 中配置 DATABASE_URL、Shopify 认证；数据库已执行 app/schemas/tables.sql
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv(Path(__file__).resolve().parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

POLL_INTERVAL_SECONDS = 10


async def run_once(days_back: int = 1):
    from app.core.config import get_settings
    from app.models import get_connection, upsert_shopify_order
    from app.services.shopify_service import ShopifyService
    from app.schemas.shopify import ShopifyOrderSyncItem
    from app.sync_utils import beijing_time_range

    settings = get_settings()
    shop_id = f"{settings.SHOPIFY_STORE_NAME}.myshopify.com"
    created_at_min, created_at_max = beijing_time_range(days_back=days_back)
    logger.info(
        f"[轮询] 时间范围(前 {days_back} 天，北京时间 14:00～今日14:00): {created_at_min} ~ {created_at_max} UTC"
    )

    service = ShopifyService()
    orders = await service.get_orders(
        limit=250,
        status="any",
        created_at_min=created_at_min,
        created_at_max=created_at_max,
    )
    logger.info(f"[轮询] 拉取到 {len(orders)} 条 Shopify 订单")

    if not orders:
        return

    conn = await get_connection()
    try:
        for order in orders:
            if not isinstance(order, ShopifyOrderSyncItem):
                continue
            # 优先使用完整 GraphQL node（全字段），否则回退为 schema 序列化
            raw_data = order.raw_graphql_node or order.model_dump(mode="json")
            shopify_order_id = order.id
            await upsert_shopify_order(conn, shop_id, shopify_order_id, raw_data)
            logger.info(f"  shopify_orders upsert: shopify_order_id={shopify_order_id}")
    finally:
        await conn.close()
    logger.info("[轮询] 本轮同步完成")


async def main(days_back: int = 1):
    logger.info(
        "启动 Shopify 原始订单轮询同步，每 {} 秒执行一次，同步前 {} 天数据",
        POLL_INTERVAL_SECONDS,
        days_back,
    )
    while True:
        try:
            await run_once(days_back=days_back)
        except Exception:
            logger.exception("本轮同步异常")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def parse_args():
    p = argparse.ArgumentParser(description="轮询同步 Shopify 原始订单到 shopify_orders")
    p.add_argument(
        "-n",
        type=int,
        default=1,
        metavar="DAYS",
        help="同步前多少天的数据（昨日14:00～今日14:00 为 1 天），默认 1",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(days_back=args.n))
