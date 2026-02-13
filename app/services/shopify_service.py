"""
Shopify 服务层 - 使用 Admin GraphQL API
参考: https://shopify.dev/docs/api/admin-graphql/latest/queries/orders
Token: https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/client-credentials-grant
"""
import re
import time
import httpx
from loguru import logger
from typing import Optional, Any

from app.core.config import get_settings
from app.schemas.shopify import ShopifyOrderResponse, OrderSyncResult

# access_token 缓存：(token, 过期时间戳)，提前 5 分钟刷新
_TOKEN_CACHE: Optional[tuple[str, float]] = None
_TOKEN_BUFFER_SECONDS = 300


# GraphQL 查询：获取订单列表及详情
ORDERS_QUERY = """
query GetOrders($first: Int!, $query: String) {
  orders(first: $first, query: $query, sortKey: PROCESSED_AT, reverse: true) {
    edges {
      cursor
      node {
        id
        name
        createdAt
        updatedAt
        displayFinancialStatus
        displayFulfillmentStatus
        totalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        subtotalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        totalTaxSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        totalDiscountsSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        email
        phone
        note
        customAttributes {
          key
          value
        }
        shippingAddress {
          address1
          address2
          city
          province
          provinceCode
          zip
          country
          countryCodeV2
          name
          firstName
          lastName
          phone
        }
        lineItems(first: 100) {
          edges {
            node {
              name
              quantity
              variant {
                id
                title
              }
              originalUnitPriceSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
              discountedUnitPriceAfterAllDiscountsSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
              originalTotalSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
              discountedTotalSet(withCodeDiscounts: true) {
                shopMoney {
                  amount
                  currencyCode
                }
              }
              totalDiscountSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
            }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


class ShopifyService:
    """Shopify 业务服务（GraphQL）"""

    def __init__(self):
        self.settings = get_settings()
        self.graphql_url = self.settings.shopify_graphql_url
        if not self.settings.use_client_credentials() and not self.settings.SHOPIFY_ACCESS_TOKEN:
            raise ValueError(
                "请在 .env 中配置 SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET（推荐），"
                "或配置 SHOPIFY_ACCESS_TOKEN"
            )

    async def _get_access_token(self) -> str:
        """
        获取 access_token：优先 Client Credentials 动态获取并缓存，否则使用 .env 中的静态 token。
        参考: https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/client-credentials-grant
        """
        if self.settings.use_client_credentials():
            global _TOKEN_CACHE
            now = time.time()
            if _TOKEN_CACHE and _TOKEN_CACHE[1] > now:
                return _TOKEN_CACHE[0]
            url = self.settings.shopify_oauth_token_url
            # 文档要求 application/x-www-form-urlencoded
            data = {
                "grant_type": "client_credentials",
                "client_id": self.settings.SHOPIFY_CLIENT_ID,
                "client_secret": self.settings.SHOPIFY_CLIENT_SECRET,
            }
            logger.info("使用 Client Credentials 获取 access_token")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data=data,
                )
                response.raise_for_status()
                body = response.json()
            token = body.get("access_token")
            if not token:
                raise RuntimeError(f"未获取到 access_token: {body}")
            expires_in = int(body.get("expires_in", 86399))  # 默认 24 小时
            _TOKEN_CACHE = (token, now + expires_in - _TOKEN_BUFFER_SECONDS)
            logger.info(f"access_token 获取成功，有效期约 {expires_in} 秒")
            return token
        if self.settings.SHOPIFY_ACCESS_TOKEN:
            return self.settings.SHOPIFY_ACCESS_TOKEN
        raise ValueError("未配置 Shopify 认证信息")

    async def _graphql_request(self, query: str, variables: Optional[dict] = None) -> dict:
        """
        发起 Shopify GraphQL 请求
        POST https://{store}.myshopify.com/admin/api/{version}/graphql.json
        """
        access_token = await self._get_access_token()
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        logger.info(f"请求 Shopify GraphQL: POST {self.graphql_url}")
        logger.debug(f"variables: {variables}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.graphql_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data and data["errors"]:
                    logger.error(f"GraphQL 错误: {data['errors']}")
                    raise RuntimeError(f"GraphQL errors: {data['errors']}")

                logger.info("Shopify GraphQL 请求成功")
                logger.debug(f"响应: {data}")
                return data.get("data", {})

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Shopify GraphQL 请求失败: {e.response.status_code} - {e.response.text}"
                )
                raise
            except Exception as e:
                logger.exception(f"Shopify GraphQL 请求异常: {str(e)}")
                raise

    @staticmethod
    def _parse_order_id(gid: str) -> int:
        """从 GID 解析数字 ID，如 gid://shopify/Order/126216516 -> 126216516"""
        if not gid:
            return 0
        match = re.search(r"/(\d+)$", gid)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_order_number(name: str) -> int:
        """从 name 解析订单号，如 #1001 -> 1001"""
        if not name:
            return 0
        match = re.search(r"#?(\d+)", name)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_variant_id(gid: str | None) -> int | None:
        """从 Variant GID 解析数字 ID，如 gid://shopify/ProductVariant/40123456 -> 40123456"""
        if not gid:
            return None
        match = re.search(r"/(\d+)$", gid)
        return int(match.group(1)) if match else None

    def _graphql_node_to_order(self, node: dict) -> ShopifyOrderResponse:
        """将 GraphQL orders.edges[].node 转为 ShopifyOrderResponse"""
        shop_money = node.get("totalPriceSet", {}).get("shopMoney") or {}
        subtotal_money = node.get("subtotalPriceSet", {}).get("shopMoney") or {}
        tax_money = node.get("totalTaxSet", {}).get("shopMoney") or {}
        discount_money = node.get("totalDiscountsSet", {}).get("shopMoney") or {}
        currency = shop_money.get("currencyCode", "")

        # 行项目：GraphQL 是 lineItems.edges[].node（含原价、折后价、折扣，便于与订单总价核对）
        line_items: list[dict[str, Any]] = []
        for edge in node.get("lineItems", {}).get("edges", []):
            li = edge.get("node", {})
            orig_unit = (li.get("originalUnitPriceSet") or {}).get("shopMoney") or {}
            disc_unit = (li.get("discountedUnitPriceAfterAllDiscountsSet") or {}).get("shopMoney") or {}
            orig_total = (li.get("originalTotalSet") or {}).get("shopMoney") or {}
            disc_total = (li.get("discountedTotalSet") or {}).get("shopMoney") or {}
            line_disc = (li.get("totalDiscountSet") or {}).get("shopMoney") or {}
            # 实付单价：有折后价用折后价，否则用原价；sku_id 用 variant id（sku 常为空时仍可唯一标识规格）
            unit_amount = disc_unit.get("amount") or orig_unit.get("amount", "0")
            variant_node = li.get("variant") or {}
            sku_id = self._parse_variant_id(variant_node.get("id"))
            line_items.append({
                "name": li.get("name"),
                "quantity": li.get("quantity", 0),
                "sku_id": sku_id,
                "variant_title": variant_node.get("title"),
                "price": unit_amount,
                "original_unit_price": orig_unit.get("amount", "0"),
                "discounted_unit_price": disc_unit.get("amount"),
                "original_total": orig_total.get("amount", "0"),
                "discounted_total": disc_total.get("amount"),
                "total_discount": line_disc.get("amount", "0"),
            })

        # customAttributes: GraphQL 返回 [{key, value}]
        custom_attrs = node.get("customAttributes") or []
        note_attributes = [{"key": a.get("key"), "value": a.get("value")} for a in custom_attrs]
        order_note = node.get("note")
        # 客服备注：从 customAttributes 约定 key 取（常见 key: staff_note, 客服备注, internal_note）
        staff_note = None
        for a in custom_attrs:
            k = (a.get("key") or "").strip().lower()
            if k in ("staff_note", "客服备注", "internal_note", "staffnote"):
                staff_note = a.get("value")
                break
        if not staff_note and order_note:
            staff_note = None  # 买家备注与客服备注分离时，仅 note 作为买家备注

        return ShopifyOrderResponse(
            id=self._parse_order_id(node.get("id", "")),
            name=node.get("name") or "",
            order_number=self._parse_order_number(node.get("name", "")),
            email=node.get("email"),
            phone=node.get("phone"),
            created_at=node.get("createdAt", ""),
            updated_at=node.get("updatedAt", ""),
            total_price=shop_money.get("amount", "0"),
            subtotal_price=subtotal_money.get("amount", "0"),
            total_tax=tax_money.get("amount", "0"),
            total_discounts=discount_money.get("amount", "0"),
            currency=currency,
            financial_status=node.get("displayFinancialStatus"),
            fulfillment_status=node.get("displayFulfillmentStatus"),
            customer=None,
            note=order_note,
            buyer_note=order_note,
            staff_note=staff_note,
            note_attributes=note_attributes,
            line_items=line_items,
            shipping_address=node.get("shippingAddress"),
            billing_address=None,
        )

    async def get_orders(
        self,
        limit: int = 50,
        status: str = "any",
        created_at_min: Optional[str] = None,
        created_at_max: Optional[str] = None,
    ) -> list[ShopifyOrderResponse]:
        """
        获取订单列表（GraphQL）
        status: any | open | closed | cancelled
        """
        logger.info(f"开始获取 Shopify 订单 (GraphQL), limit={limit}, status={status}")

        # GraphQL 筛选：query 语法见 https://shopify.dev/docs/api/admin-graphql/latest/queries/orders
        query_filter: Optional[str] = None
        if status and status != "any":
            query_filter = f"status:{status}"

        if created_at_min:
            q = f"created_at:>={created_at_min}"
            query_filter = f"{query_filter} {q}" if query_filter else q
        if created_at_max:
            q = f"created_at:<={created_at_max}"
            query_filter = f"{query_filter} {q}" if query_filter else q

        variables: dict[str, Any] = {
            "first": min(limit, 250),
        }
        if query_filter:
            variables["query"] = query_filter

        data = await self._graphql_request(ORDERS_QUERY, variables)
        edges = (data.get("orders") or {}).get("edges") or []
        nodes = [e.get("node") for e in edges if e.get("node")]

        logger.info(f"成功获取 {len(nodes)} 条订单")

        orders = [self._graphql_node_to_order(n) for n in nodes]

        for idx, order in enumerate(orders, 1):
            logger.info(f"--- 订单 {idx} ---")
            logger.info(f"订单号: {order.order_number}")
            logger.info(f"订单ID: {order.id}")
            logger.info(f"邮箱: {order.email}")
            logger.info(f"总价: {order.total_price} {order.currency}")
            logger.info(f"支付状态: {order.financial_status}")
            logger.info(f"配送状态: {order.fulfillment_status}")
            logger.info(f"创建时间: {order.created_at}")
            logger.info(f"订单备注(note): {order.note or '(无)'}")
            if order.note_attributes:
                logger.info(f"订单标记(note_attributes): {order.note_attributes}")
            logger.info(f"商品数量: {len(order.line_items)}")
            for item_idx, item in enumerate(order.line_items, 1):
                logger.info(
                    f"  商品{item_idx}: {item.get('name')} x {item.get('quantity')} - {item.get('price')} {order.currency}"
                )
            logger.info("-" * 50)

        return orders

    async def sync_orders(
        self,
        limit: int = 50,
        status: str = "any",
    ) -> OrderSyncResult:
        """同步订单"""
        logger.info("开始同步 Shopify 订单 (GraphQL)...")

        try:
            orders = await self.get_orders(limit=limit, status=status)
            result = OrderSyncResult(
                total_synced=len(orders),
                success_count=len(orders),
                failed_count=0,
                orders=orders,
            )
            logger.info(f"订单同步完成! 共同步 {result.total_synced} 条订单")
            return result
        except Exception as e:
            logger.exception(f"订单同步失败: {str(e)}")
            raise
