"""
订单同步与拆单共用：时间范围（北京时间 昨日14:00～今日14:00）、区域映射与拆单工具。
"""
from datetime import datetime, timezone, timedelta

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


def beijing_time_range(days_back: int = 1) -> tuple[str, str]:
    """
    北京时间：昨天 14:00 ～ 今天 14:00，转为 ISO 字符串供 Shopify query 使用。
    days_back: 起始日为今天往前几天，默认 1 表示「昨日 14:00 ～ 今日 14:00」。
    """
    beijing = timezone(timedelta(hours=8))
    now_bj = datetime.now(beijing)
    today = now_bj.date()
    start_date = today - timedelta(days=days_back)
    start_bj = datetime(start_date.year, start_date.month, start_date.day, 14, 0, 0, 0, tzinfo=beijing)
    end_bj = datetime(today.year, today.month, today.day, 14, 0, 0, 0, tzinfo=beijing)
    start_utc = start_bj.astimezone(timezone.utc)
    end_utc = end_bj.astimezone(timezone.utc)
    return start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def group_line_items_by_region(line_items: list[dict]) -> dict[str, list[dict]]:
    """按规格映射到区域，同一区域的商品分在一组；不在映射内的归为「其他」一单。"""
    groups: dict[str, list[dict]] = {}
    for item in line_items:
        spec = (item.get("variant_title") or "").strip()
        region = REGION_BY_SPEC.get(spec, OTHER_REGION)
        if region not in groups:
            groups[region] = []
        groups[region].append(item)
    return groups


def raw_to_customer_json(raw: dict) -> dict:
    """从原始订单 raw 提取客户信息 JSON。"""
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


def items_subtotal(items: list[dict]) -> float:
    """行项目折后小计（优先 discounted_total，否则 price*quantity）。"""
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


def items_discounted_subtotal_by_unit(items: list[dict]) -> float:
    """
    行项目折后小计：按 discountedUnitPriceAfterAllDiscountsSet 单价 × 数量 累加。
    单价取 discounted_unit_price，无则取 price。
    """
    total = 0.0
    for it in items:
        try:
            unit = it.get("discounted_unit_price") or it.get("price") or "0"
            total += float(unit) * int(it.get("quantity") or 0)
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def items_original_subtotal(items: list[dict]) -> float:
    """行项目原价小计（original_total 之和）。"""
    total = 0.0
    for it in items:
        try:
            orig = it.get("original_total")
            if orig is not None and str(orig).strip():
                total += float(orig)
            else:
                total += float(it.get("original_unit_price") or it.get("price") or 0) * int(it.get("quantity") or 0)
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def make_parent_order_no(shopify_order_id: int) -> str:
    """parent_order_no = Order + YYYYMMDD + HHMMSS + 毫秒(3位) + shopify_order_id"""
    now = datetime.now(timezone(timedelta(hours=8)))
    ts = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    return f"Order{ts}_{shopify_order_id}"


def parse_created_at(created_at: str | None) -> datetime | None:
    """解析 Shopify created_at 字符串为 datetime。"""
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return None
