"""
拆单结果导出为 CSV（店小秘等导入用）。
"""
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# CSV 表头（与需求字段一致）
EXPORT_HEADERS = [
    "订单号",
    "店铺账号",
    "SKU",
    "属性",
    "数量",
    "单价",
    "币种",
    "发货仓库",
    "买家姓名",
    "地址1",
    "城市",
    "省/州",
    "区县",
    "国家二字码",
    "邮编",
    "手机",
    "Email",
    "买家备注",
    "下单时间",
    "客服备注",
]

BEIJING_TZ = timezone(timedelta(hours=8))


def _format_order_created_at(dt: datetime | None) -> str:
    """将 order_created_at 转为北京时间字符串。"""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _order_row_to_csv_rows(
    order: dict,
    shop_account: str,
) -> list[list[str]]:
    """
    将一条 orders 表记录展开为多行 CSV（每行一个商品）。
    order 需含: sub_order_no, items_json, customer_json, extra_info, order_created_at。
    """
    extra = order.get("extra_info") or {}
    if isinstance(extra, str):
        import json
        try:
            extra = json.loads(extra) if extra else {}
        except Exception:
            extra = {}
    customer = order.get("customer_json") or {}
    if isinstance(customer, str):
        import json
        try:
            customer = json.loads(customer) if customer else {}
        except Exception:
            customer = {}
    items = order.get("items_json") or []
    if isinstance(items, str):
        import json
        try:
            items = json.loads(items) if items else []
        except Exception:
            items = []

    shopify_name = extra.get("shopify_order_name") or ""
    sub_order_no = order.get("sub_order_no") or ""
    order_no = f"{shopify_name}-{sub_order_no}" if shopify_name else sub_order_no

    addr1 = (customer.get("address1") or "")
    addr2 = (customer.get("address2") or "")
    address1 = (addr1 + " " + addr2).strip() if addr2 else addr1

    order_created_str = _format_order_created_at(order.get("order_created_at"))
    buyer_note = extra.get("note") or ""
    staff_note = extra.get("staff_note") or ""

    rows: list[list[str]] = []
    for it in items:
        unit_price = it.get("discounted_unit_price") or it.get("price") or "0"
        rows.append([
            order_no,
            shop_account,
            str(it.get("sku_id") or ""),
            str(it.get("variant_title") or ""),
            str(it.get("quantity") or ""),
            str(unit_price),
            "TWD",
            "默认仓库",
            str(customer.get("name") or ""),
            address1,
            str(customer.get("city") or ""),
            "台湾",
            str(customer.get("city") or ""),
            "tw",
            str(customer.get("zip") or ""),
            str(customer.get("phone") or ""),
            str(customer.get("email") or ""),
            buyer_note,
            order_created_str,
            staff_note,
        ])
    return rows


def export_orders_to_csv(
    orders: list[dict],
    output_path: str | Path,
    shop_account: str = "默认店铺",
) -> int:
    """
    将订单列表导出为 CSV 文件。
    orders: get_orders_for_export 返回的列表。
    output_path: 输出文件路径。
    shop_account: 店铺账号列填充值。
    返回写入的 CSV 行数（含表头）。
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(EXPORT_HEADERS)
        total_rows += 1
        for order in orders:
            for row in _order_row_to_csv_rows(order, shop_account):
                writer.writerow(row)
                total_rows += 1
    return total_rows
