"""
Shopify 订单同步测试
"""
import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from loguru import logger
from app.services.shopify_service import ShopifyService


async def test_sync_orders():
    """测试同步订单功能"""
    logger.info("=" * 60)
    logger.info("开始测试 Shopify 订单同步")
    logger.info("=" * 60)
    
    try:
        # 创建服务实例
        service = ShopifyService()
        logger.info(f"Shopify 店铺: {service.settings.SHOPIFY_STORE_NAME}")
        logger.info(f"API 版本: {service.settings.SHOPIFY_API_VERSION}")
        logger.info(f"GraphQL URL: {service.graphql_url}")
        logger.info("-" * 60)
        
        # 同步订单
        result = await service.sync_orders(limit=50, status="any")
        
        logger.info("=" * 60)
        logger.info("同步结果汇总")
        logger.info("=" * 60)
        logger.info(f"总共同步: {result.total_synced} 条订单")
        logger.info(f"成功: {result.success_count} 条")
        logger.info(f"失败: {result.failed_count} 条")
        logger.info("=" * 60)
        
        # 详细打印每个订单
        if result.orders:
            logger.info("\n详细订单信息:")
            for idx, order in enumerate(result.orders, 1):
                logger.info(f"\n{'=' * 60}")
                logger.info(f"订单 {idx}/{len(result.orders)}")
                logger.info(f"{'=' * 60}")
                logger.info(f"订单name(店小秘订单号用): {order.name}")
                logger.info(f"订单号: {order.order_number}")
                logger.info(f"订单ID: {order.id}")
                logger.info(f"客户邮箱: {order.email or '无'}")
                logger.info(f"订单电话: {order.phone or '无'}")
                logger.info(f"总价: {order.total_price} {order.currency}")
                logger.info(f"小计: {order.subtotal_price} {order.currency}")
                logger.info(f"税费: {order.total_tax} {order.currency}")
                logger.info(f"订单总折扣: {order.total_discounts} {order.currency}")
                logger.info(f"支付状态: {order.financial_status or '未知'}")
                logger.info(f"配送状态: {order.fulfillment_status or '未配送'}")
                logger.info(f"创建时间: {order.created_at}")
                logger.info(f"更新时间: {order.updated_at}")
                logger.info(f"买家备注(buyer_note): {order.buyer_note or '(无)'}")
                logger.info(f"客服备注(staff_note): {order.staff_note or '(无)'}")
                if order.note_attributes:
                    logger.info("订单标记(note_attributes):\n" + json.dumps(order.note_attributes, indent=2, ensure_ascii=False))
                else:
                    logger.info("订单标记(note_attributes): (无)")
                
                # 客户信息
                if order.customer:
                    logger.info(f"\n客户信息:")
                    logger.info(f"  姓名: {order.customer.get('first_name', '')} {order.customer.get('last_name', '')}")
                    logger.info(f"  邮箱: {order.customer.get('email', '无')}")
                    logger.info(f"  电话: {order.customer.get('phone', '无')}")
                
                # 金额核对（为何 SKU 总金额与订单总价不一致：折扣/税）
                sum_original = sum(float(item.get("original_total", 0) or 0) for item in order.line_items)
                sum_line_discounted = sum(float(item.get("discounted_total") or 0) for item in order.line_items)
                logger.info(f"\n【金额核对】")
                logger.info(f"  商品原价合计: {sum_original:.2f} {order.currency}")
                logger.info(f"  订单总折扣: {order.total_discounts} {order.currency}")
                logger.info(f"  订单小计(subtotal): {order.subtotal_price} {order.currency}")
                logger.info(f"  订单税费: {order.total_tax} {order.currency}")
                logger.info(f"  订单总价(total): {order.total_price} {order.currency}")
                try:
                    st = float(order.subtotal_price or 0)
                    if abs(sum_line_discounted - st) > 0.02:
                        logger.info(f"  ⚠️ 行项目折后合计({sum_line_discounted:.2f}) 与 订单小计({st}) 不一致，可能含订单级折扣/舍入")
                    else:
                        logger.info(f"  ✓ 行项目折后合计({sum_line_discounted:.2f}) 与 订单小计 一致")
                except (TypeError, ValueError):
                    pass

                # 商品明细（含原价/折后价/折扣）
                logger.info(f"\n商品明细 (共 {len(order.line_items)} 件):")
                for item_idx, item in enumerate(order.line_items, 1):
                    logger.info(f"  [{item_idx}] {item.get('name', '未知商品')}")
                    logger.info(f"      数量: {item.get('quantity', 0)}")
                    logger.info(f"      原价单价: {item.get('original_unit_price', '0')} {order.currency}")
                    logger.info(f"      折后单价(实付): {item.get('price', '0')} {order.currency}")
                    logger.info(f"      行折扣额: {item.get('total_discount', '0')} {order.currency}")
                    logger.info(f"      行原价合计: {item.get('original_total', '0')} {order.currency}")
                    logger.info(f"      行折后合计: {item.get('discounted_total') or '(原价×数量)'} {order.currency}")
                    logger.info(f"      sku_id: {item.get('sku_id')}")
                    if item.get('variant_title'):
                        logger.info(f"      规格: {item.get('variant_title')}")
                
                # 配送地址
                if order.shipping_address:
                    addr = order.shipping_address
                    logger.info(f"\n配送地址(店小秘用):")
                    logger.info(f"  买家姓名: {addr.get('name', '无')}")
                    logger.info(f"  地址1: {addr.get('address1', '')} {addr.get('address2', '')}")
                    logger.info(f"  城市: {addr.get('city', '')}")
                    logger.info(f"  省/州: {addr.get('province', '')}")
                    logger.info(f"  区县: {addr.get('city', '')} (Shopify无单独区县，用city)")
                    logger.info(f"  国家二字码: {addr.get('countryCodeV2', addr.get('country', ''))}")
                    logger.info(f"  邮编: {addr.get('zip', '')}")
                    logger.info(f"  手机: {addr.get('phone', '无')}")
        
        logger.info(f"\n{'=' * 60}")
        logger.info("✅ 测试完成!")
        logger.info(f"{'=' * 60}\n")
        
        return result
        
    except Exception as e:
        logger.exception("❌ 测试失败!")
        raise


async def test_get_orders_with_filters():
    """测试带筛选条件获取订单"""
    logger.info("\n" + "=" * 60)
    logger.info("测试筛选条件获取订单")
    logger.info("=" * 60)
    
    try:
        service = ShopifyService()
        
        # 测试不同的筛选条件
        test_cases = [
            {"limit": 5, "status": "any", "desc": "获取最近5条订单(任意状态)"},
            {"limit": 3, "status": "open", "desc": "获取最近3条未完成订单"},
        ]
        
        for case in test_cases:
            logger.info(f"\n{'-' * 60}")
            logger.info(f"测试场景: {case['desc']}")
            logger.info(f"{'-' * 60}")
            
            orders = await service.get_orders(
                limit=case["limit"],
                status=case["status"]
            )
            
            logger.info(f"获取到 {len(orders)} 条订单")
            for order in orders:
                logger.info(f"  - 订单#{order.order_number}: {order.total_price} {order.currency} ({order.financial_status})")
        
        logger.info(f"\n{'=' * 60}")
        logger.info("✅ 筛选测试完成!")
        logger.info(f"{'=' * 60}\n")
        
    except Exception as e:
        logger.exception("❌ 筛选测试失败!")
        raise


def main():
    """主函数"""
    logger.info("\n🚀 启动 Shopify 订单同步测试\n")
    
    # 运行基础同步测试
    asyncio.run(test_sync_orders())
    
    # 运行筛选测试（可选，取消注释以启用）
    # asyncio.run(test_get_orders_with_filters())


if __name__ == "__main__":
    main()
