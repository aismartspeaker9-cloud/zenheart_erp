"""
脚本2：从 shopify_orders 表读取原始订单，按区域拆单写入 orders。
默认读取最近 1 天（昨日14:00～今日14:00 北京时间）；可 -n 指定天数，或 --order-id 只拆指定 Shopify 订单。

运行：python run_split_orders.py [-n 天数] [--order-id ID] [-o CSV路径] [--shop-account 店铺账号]
依赖：.env 中配置 DATABASE_URL；脚本1 已同步过原始订单到 shopify_orders；数据库已执行 app/schemas/tables.sql
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv(Path(__file__).resolve().parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.export_csv import export_orders_to_csv
from app.sync_utils import (
    OTHER_REGION,
    beijing_time_range,
    group_line_items_by_region,
    raw_to_customer_json,
    items_subtotal,
    items_original_subtotal,
    items_discounted_subtotal_by_unit,
    make_parent_order_no,
    parse_created_at,
)


async def run_split_orders(
    days_back: int = 1,
    order_id: int | None = None,
    output_path: str | None = None,
    shop_account: str = "默认店铺",
):
    from app.core.config import get_settings
    from app.models import (
        get_connection,
        get_shopify_orders_by_created_at_range,
        get_shopify_order_by_id,
        get_orders_for_export,
        delete_orders_by_shopify_order,
        insert_order,
    )
    from app.services.shopify_service import ShopifyService

    settings = get_settings()
    shop_id = f"{settings.SHOPIFY_STORE_NAME}.myshopify.com"
    conn = await get_connection()
    try:
        if order_id is not None:
            row = await get_shopify_order_by_id(conn, shop_id, order_id)
            rows = [row] if row else []
            logger.info(f"指定 order_id={order_id}，查询到 {'1' if rows else '0'} 条订单")
        else:
            created_at_min, created_at_max = beijing_time_range(days_back=days_back)
            logger.info(
                f"时间范围(前 {days_back} 天，北京时间 14:00～今日14:00): {created_at_min} ~ {created_at_max} UTC"
            )
            rows = await get_shopify_orders_by_created_at_range(
                conn, shop_id, created_at_min, created_at_max
            )
            logger.info(f"从 shopify_orders 读取到 {len(rows)} 条订单")

        if not rows:
            logger.info("无订单，结束")
            return

        created_at_min, created_at_max = None, None
        if order_id is None:
            created_at_min, created_at_max = beijing_time_range(days_back=days_back)

        service = ShopifyService()
        for row in rows:
            raw_data = row["raw_data"]
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(f"  shopify_order_id={row['shopify_order_id']} raw_data 非合法 JSON，跳过")
                    continue
            shopify_order_id = row["shopify_order_id"]
            try:
                order = service._graphql_node_to_order(raw_data)
            except Exception as e:
                logger.warning(f"  shopify_order_id={shopify_order_id} 解析 raw_data 失败: {e}，跳过")
                continue

            await delete_orders_by_shopify_order(conn, shop_id, shopify_order_id)
            groups = group_line_items_by_region(order.line_items)
            if not groups:
                groups = {OTHER_REGION: []}
            parent_order_no = make_parent_order_no(shopify_order_id)
            customer_json = raw_to_customer_json(raw_data)
            order_created_at = parse_created_at(order.created_at)
            order_updated_at = parse_created_at(order.updated_at)
            currency = (order.currency or "TWD")[:3]
            payment_status = order.financial_status

            # 运费：折前取 original_amount，折后取 discounted_presentment_amount
            try:
                first_line = (order.shipping_lines or [{}])[0]
                shipping_original_total = float(first_line.get("original_amount") or 0)
                shipping_fee_total = float(
                    first_line.get("discounted_presentment_amount")
                    or first_line.get("discounted_amount")
                    or order.total_shipping_price
                    or 0
                )
            except (TypeError, ValueError, IndexError):
                shipping_original_total = 0.0
                shipping_fee_total = 0.0
            # 原始总订单：折前 = 全部行原价小计 + 运费原价，折后 = 订单 total_price
            order_original_total = round(
                items_original_subtotal(order.line_items) + shipping_original_total, 2
            )
            order_discounted_total = order.total_price or "0"

            marketing_json = {}
            if order.source_name:
                marketing_json["source_name"] = order.source_name
            if order.sales_channel:
                marketing_json["sales_channel"] = order.sales_channel
            if order.channel_information:
                marketing_json["channel_information"] = order.channel_information
                if order.channel_information.get("channelDefinition"):
                    marketing_json["channel_definition"] = order.channel_information["channelDefinition"]
            marketing_json = marketing_json if marketing_json else None
            payment_method_str = ", ".join(order.payment_gateway_names) if order.payment_gateway_names else None
            delivery_config = order.shipping_lines if order.shipping_lines else None
            extra_info = {
                "shopify_order_name": order.name,
                "staff_note": order.staff_note,
            }
            if order.note:
                extra_info["note"] = order.note
            if order.note_attributes:
                extra_info["note_attributes"] = order.note_attributes

            for i, (region, items) in enumerate(
                sorted(groups.items(), key=lambda x: (x[0] == OTHER_REGION, x[0])), 1
            ):
                sub_order_no = f"{parent_order_no}-{i}"
                original_subtotal = items_original_subtotal(items)
                # 子订单折后 = discountedUnitPriceAfterAllDiscountsSet × 数量 的累加 + 运费
                discounted_subtotal = items_discounted_subtotal_by_unit(items)
                specs = [str(item.get("variant_title") or "(无规格)") for item in items]
                shipping_fee = shipping_fee_total if i == 1 else 0.0
                shipping_orig = shipping_original_total if i == 1 else 0.0
                sub_order_original_total = round(original_subtotal + shipping_orig, 2)
                sub_order_discounted_total = round(discounted_subtotal + shipping_fee, 2)
                amount = {
                    "order_original_total": str(order_original_total),
                    "order_discounted_total": str(order_discounted_total),
                    "sub_order_original_total": str(sub_order_original_total),
                    "sub_order_discounted_total": str(sub_order_discounted_total),
                    "items": [
                        {
                            "sku_id": it.get("sku_id"),
                            "original_total": it.get("original_total") or "0",
                            "discounted_total": str(
                                round(
                                    float(it.get("discounted_unit_price") or it.get("price") or 0)
                                    * int(it.get("quantity") or 0),
                                    2,
                                )
                            ),
                        }
                        for it in items
                    ],
                }
                await insert_order(
                    conn,
                    parent_order_no=parent_order_no,
                    sub_order_no=sub_order_no,
                    shop_id=shop_id,
                    shopify_order_id=shopify_order_id,
                    amount=amount,
                    currency=currency,
                    payment_status=payment_status,
                    payment_method=payment_method_str,
                    region=region,
                    items_json=items,
                    customer_json=customer_json,
                    order_created_at=order_created_at,
                    order_updated_at=order_updated_at,
                    shipping_fee=shipping_fee,
                    shipping_address=order.shipping_address,
                    marketing_json=marketing_json,
                    delivery_config=delivery_config,
                    extra_info=extra_info if extra_info else None,
                )
                logger.info(
                    f"    orders 拆单: sub_order_no={sub_order_no} region={region} items={len(items)} 规格={specs}"
                )

        if output_path:
            ts_min = parse_created_at(created_at_min) if created_at_min else None
            ts_max = parse_created_at(created_at_max) if created_at_max else None
            export_orders = await get_orders_for_export(
                conn,
                shop_id,
                order_created_at_min=ts_min,
                order_created_at_max=ts_max,
                shopify_order_id=order_id,
            )
            if export_orders:
                n = export_orders_to_csv(export_orders, output_path, shop_account=shop_account)
                logger.info("导出 CSV: {} 共 {} 行", output_path, n)
            else:
                logger.warning("无订单可导出，未生成 CSV")
    finally:
        await conn.close()

    logger.info("拆单完成")


def parse_args():
    p = argparse.ArgumentParser(description="从 shopify_orders 按区域拆单写入 orders")
    p.add_argument(
        "-n",
        type=int,
        default=1,
        metavar="DAYS",
        help="拆前多少天的数据（昨日14:00～今日14:00 为 1 天），默认 1；与 --order-id 二选一",
    )
    p.add_argument(
        "--order-id",
        type=int,
        default=None,
        metavar="ID",
        help="只拆指定的 Shopify 订单 ID（不传则按时间范围 -n 拆单）",
    )
    p.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="拆单完成后导出 CSV 到该路径",
    )
    p.add_argument(
        "--shop-account",
        type=str,
        default="默认店铺",
        metavar="NAME",
        help="导出 CSV 中「店铺账号」列填充值，默认：默认店铺",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run_split_orders(
            days_back=args.n,
            order_id=args.order_id,
            output_path=args.output,
            shop_account=args.shop_account,
        )
    )
