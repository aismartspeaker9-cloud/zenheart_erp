CREATE TABLE shopify_orders (
    id SERIAL PRIMARY KEY,              -- 数据库自增 ID
    shop_id TEXT NOT NULL,              -- 店铺唯一标识 (例如 'my-shop-77.myshopify.com')
    shopify_order_id BIGINT NOT NULL,   -- Shopify 侧的订单 ID
    raw_data JSONB NOT NULL,            -- 原始 JSON 订单数据
    order_created_at TIMESTAMP WITH TIME ZONE,   -- Shopify 订单创建时间 (createdAt)
    order_updated_at TIMESTAMP WITH TIME ZONE,   -- Shopify 订单更新时间 (updatedAt)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 联合唯一约束：同一个店铺下，订单 ID 不能重复
    UNIQUE(shop_id, shopify_order_id)
);

-- 给 shop_id 加上索引，因为你以后查询肯定会带上这个条件
CREATE INDEX idx_shopify_orders_shop_id ON shopify_orders(shop_id);

-- 已有库升级：添加 Shopify 订单创建/更新时间（若表已存在且无这两列可执行）
-- ALTER TABLE shopify_orders ADD COLUMN IF NOT EXISTS order_created_at TIMESTAMP WITH TIME ZONE;
-- ALTER TABLE shopify_orders ADD COLUMN IF NOT EXISTS order_updated_at TIMESTAMP WITH TIME ZONE;


CREATE TABLE orders (
    id SERIAL PRIMARY KEY,              -- 内部自增 ID
    parent_order_no TEXT,               -- OMS 主订单号 (用于归集拆单)
    sub_order_no TEXT NOT NULL UNIQUE,  -- 订单 Sub ID (拆单后的唯一编号 parent_order-x)
    
    -- 关联外部
    shop_id TEXT NOT NULL,
    shopify_order_id BIGINT NOT NULL,   -- 关联原始同步表
    
    -- 金额信息
    amount JSONB,                       -- 原始总订单折前/折后、子订单折前/折后、每 SKU 折前/折后，见下
    -- amount: { "order_original_total", "order_discounted_total", "sub_order_original_total", "sub_order_discounted_total", "items": [{ "sku_id", "original_total", "discounted_total" }] }
    shipping_fee DECIMAL(15, 2),        -- 运费，取自 shippingLine.discountedPriceSet.presentmentMoney.amount
    shipping_address JSONB,             -- 收货地址完整信息（如 name, address1, city, province, zip, countryCodeV2, phone）
    currency CHAR(3),                   -- 币种
    payment_status TEXT,                -- 支付状态
    payment_method TEXT,                -- 支付方式
    region TEXT,                        -- 区域

    -- 三大核心 JSONB 块
    items_json JSONB NOT NULL,          -- 商品信息数组 [{sku, name, price, qty, blessing...}]
    customer_json JSONB NOT NULL,       -- 客户信息 {name, email, phone, line, address...}
    marketing_json JSONB,               -- 营销信息 {source_url, landing_page, tags, source_name...}
    
    -- 履约与拓展
    delivery_config JSONB,             -- 运送的配置信息
    extra_info JSONB,                   -- 影片视频、其他备注
    
    -- 时间
    order_created_at TIMESTAMP WITH TIME ZONE, -- 订单在 Shopify 的创建时间
    order_updated_at TIMESTAMP WITH TIME ZONE, -- 订单在 Shopify 的更新时间
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), -- 记录入库时间
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引：优化最常用的查询场景
CREATE INDEX idx_orders_sub_no ON orders(sub_order_no);
CREATE INDEX idx_orders_shop_order ON orders(shop_id, shopify_order_id);

-- 已有 orders 表升级（若表已存在）：合并金额列为 amount JSONB，并加 order_updated_at、shipping_address
-- ALTER TABLE orders ADD COLUMN IF NOT EXISTS amount JSONB;
-- ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_updated_at TIMESTAMP WITH TIME ZONE;
-- ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_address JSONB;
-- 迁移数据后删除旧列: ALTER TABLE orders DROP COLUMN IF EXISTS total_amount, DROP COLUMN IF EXISTS subtotal_amount, DROP COLUMN IF EXISTS discount_amount;


CREATE TABLE order_fulfillments (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    tracking_number TEXT,               -- 物流单号
    logistics_company TEXT,             -- 物流公司 (如 FedEx, DHL)
    shipping_method TEXT,               -- 物流方式
    status TEXT,                        -- 状态 (pending, shipped, delivered)
    shipped_at TIMESTAMP WITH TIME ZONE,
    extra_details JSONB                 -- 备用拓展
);

CREATE INDEX idx_fulfillment_order_id ON order_fulfillments(order_id);  -- 2. 业务查询索引：用于根据物流单号快速定位订单（客服查单最常用）
CREATE INDEX idx_fulfillment_tracking_number ON order_fulfillments(tracking_number);  -- 3. 状态过滤索引：用于后台扫描“待发货”或“已收货”的单据
CREATE INDEX idx_fulfillment_status ON order_fulfillments(status);