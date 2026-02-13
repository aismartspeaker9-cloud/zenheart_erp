# ZenHeart ERP - Shopify 订单同步系统

基于 FastAPI 的企业级 ERP 系统，支持 Shopify 订单同步。

## 技术栈

- **框架**: FastAPI
- **数据验证**: Pydantic v2
- **HTTP 客户端**: httpx (异步)
- **日志**: loguru
- **数据库**: PostgreSQL + SQLAlchemy 2.0 (异步)

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 Shopify 访问令牌

编辑 `.env` 文件，填入你的实际 Shopify 访问令牌：

```env
SHOPIFY_STORE_NAME=3cw00h-tp
SHOPIFY_API_VERSION=2024-01
SHOPIFY_ACCESS_TOKEN=你的实际访问令牌
```

### 3. 运行测试

直接运行测试脚本即可同步订单并查看结果：

```bash
python run_test.py
```

或者直接运行测试文件：

```bash
python tests/test_shopify_sync.py
```

## 📊 输出示例

运行测试后，你会看到详细的订单信息：

```
============================================================
开始测试 Shopify 订单同步
============================================================
Shopify 店铺: 3cw00h-tp
API 版本: 2024-01
------------------------------------------------------------
成功获取 10 条订单

============================================================
订单 1/10
============================================================
订单号: 1001
订单ID: 5678901234
客户邮箱: customer@example.com
总价: 99.99 USD
小计: 89.99 USD
税费: 10.00 USD
支付状态: paid
配送状态: fulfilled
创建时间: 2024-02-10T10:30:00Z
更新时间: 2024-02-11T15:20:00Z

客户信息:
  姓名: John Doe
  邮箱: customer@example.com
  电话: +1234567890

商品明细 (共 2 件):
  [1] Product Name 1
      数量: 1
      单价: 49.99 USD
      SKU: SKU-001
  [2] Product Name 2
      数量: 1
      单价: 39.99 USD
      SKU: SKU-002

配送地址:
  收件人: John Doe
  电话: +1234567890
  地址: 123 Main St
  城市: New York NY
  邮编: 10001
  国家: United States
```

## 项目结构

```
zenheart_erp/
├── app/
│   ├── core/
│   │   └── config.py           # 配置管理
│   ├── services/
│   │   └── shopify_service.py  # Shopify 业务逻辑
│   └── schemas/
│       └── shopify.py          # Shopify 数据模型
├── tests/
│   └── test_shopify_sync.py    # 同步测试
├── run_test.py                 # 快速测试脚本
├── requirements.txt
└── .env                        # 环境配置
```

## 核心功能

### ShopifyService 类

位于 `app/services/shopify_service.py`

主要方法：

1. **`get_orders()`** - 获取订单列表
   ```python
   orders = await service.get_orders(
       limit=50,          # 获取数量
       status="any",      # 订单状态: any/open/closed/cancelled
   )
   ```

2. **`sync_orders()`** - 同步订单
   ```python
   result = await service.sync_orders(
       limit=50,
       status="any"
   )
   ```

## 参数说明

- **limit**: 获取订单数量 (1-250)
- **status**: 订单状态
  - `any`: 所有订单
  - `open`: 未完成订单
  - `closed`: 已完成订单
  - `cancelled`: 已取消订单

## 测试功能

测试文件提供了两个测试函数：

1. **`test_sync_orders()`** - 基础同步测试，打印详细订单信息
2. **`test_get_orders_with_filters()`** - 测试不同筛选条件

在 `run_test.py` 中可以选择运行哪些测试。

## 获取 Shopify Access Token

1. 登录 Shopify Admin: https://admin.shopify.com/store/3cw00h-tp
2. 进入 Settings → Apps and sales channels
3. 选择你的 App
4. 在 API credentials 中找到 Admin API access token

## 开发规范

本项目严格遵循 `.cursorrules` 中定义的企业级开发规范：
- ✅ 所有 IO 操作使用异步 (`async/await`)
- ✅ HTTP 请求使用 `httpx.AsyncClient`
- ✅ 使用 `loguru` 进行日志记录（禁止 `print()`）
- ✅ 使用 `pydantic-settings` 管理配置
- ✅ 严格的分层架构（Service、Schema）

## 故障排查

### 1. 401 Unauthorized

检查 `.env` 中的 `SHOPIFY_ACCESS_TOKEN` 是否正确。

### 2. 找不到模块

确保在项目根目录运行测试：
```bash
cd /Users/xuxiaorong/zenheart_erp
python run_test.py
```

### 3. 网络超时

检查网络连接，或增加超时时间（在 `shopify_service.py` 中修改 `timeout` 参数）。
