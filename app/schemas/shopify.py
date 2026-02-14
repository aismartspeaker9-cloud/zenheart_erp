"""
Shopify 相关 Schema

店小秘同步字段对照（以下字段均需具备）:
  订单号: name + OMS订单ID + SUB ID（本结构提供 name）
  店铺账号: 固定「写手工订单」
  SKU: line_items[].sku_id（Shopify variant 数字 ID，用于唯一标识/映射店小秘 SKU id）
  属性: line_items[].variant_title（SKU 属性维度）
  数量: line_items[].quantity
  单价: line_items[].price（实付单价）
  币种: 固定 "TWD" 或 currency
  发货仓库: 固定默认仓库
  买家姓名: shipping_address.name
  地址1: shipping_address.address1 (+ address2)
  城市: shipping_address.city
  省/州: 固定「台湾」或 shipping_address.province
  区县: shipping_address.city（Shopify 无单独区县，可用 city）
  国家二字码: shipping_address.countryCodeV2 或 "tw"
  邮编: shipping_address.zip
  手机: shipping_address.phone 或 phone（订单电话）
  Email: email
  买家备注: buyer_note（即 Shopify note）
  下单时间: created_at（转北京时间在同步层）
  客服备注: staff_note（从 note_attributes 约定 key 或留空）
"""
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class ShopifyOrderResponse(BaseModel):
    """Shopify 原始订单（仅承载 GraphQL node，供存储 raw_data）"""
    raw_graphql_node: dict[str, Any]
    id: Optional[int] = None  # 从 node 解析出的订单 ID，便于写入 shopify_orders

    model_config = ConfigDict(from_attributes=True)


class ShopifyOrderSyncItem(BaseModel):
    """单条订单同步项（含店小秘/拆单所需全部字段，用于 OrderSyncResult.orders）"""
    id: int
    name: str  # 订单 display name，如 #1001
    order_number: int
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: str
    updated_at: str
    total_price: str
    subtotal_price: str
    total_tax: str
    total_discounts: str = "0"
    currency: str
    financial_status: Optional[str] = None
    fulfillment_status: Optional[str] = None
    customer: Optional[dict[str, Any]] = None
    note: Optional[str] = None
    buyer_note: Optional[str] = None
    staff_note: Optional[str] = None
    note_attributes: list[dict[str, Any]] = []
    line_items: list[dict[str, Any]] = []
    shipping_address: Optional[dict[str, Any]] = None
    billing_address: Optional[dict[str, Any]] = None
    source_name: Optional[str] = None
    sales_channel: Optional[str] = None
    channel_information: Optional[dict[str, Any]] = None
    total_shipping_price: Optional[str] = None
    payment_gateway_names: list[str] = []
    shipping_lines: list[dict[str, Any]] = []
    raw_graphql_node: Optional[dict[str, Any]] = None  # 供写入 shopify_orders.raw_data

    model_config = ConfigDict(from_attributes=True)


class OrderSyncResult(BaseModel):
    """订单同步结果"""
    total_synced: int
    success_count: int
    failed_count: int
    orders: list[ShopifyOrderSyncItem]

    model_config = ConfigDict(from_attributes=True)
