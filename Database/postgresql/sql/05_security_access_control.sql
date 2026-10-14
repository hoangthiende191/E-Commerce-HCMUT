-- Create roles (if they do not already exist)
CREATE ROLE hm_product_sales_analyst NOLOGIN;
CREATE ROLE hm_customer_analyst NOLOGIN;

-- Remove previous permissions
REVOKE ALL ON ALL TABLES IN SCHEMA star_schema
FROM PUBLIC, hm_product_sales_analyst, hm_customer_analyst;

-- Allow both roles to access the schema
GRANT USAGE ON SCHEMA star_schema
TO hm_product_sales_analyst, hm_customer_analyst;


-- ========================================
-- 1. PRODUCT SALES ANALYST
-- ========================================

GRANT SELECT (
    transaction_id,
    article_id,
    date_key,
    sales_channel_id,
    price,
    quantity,
    sales_revenue
)
ON star_schema.FACT_SALES 
TO hm_product_sales_analyst;

GRANT SELECT ON
    star_schema.dim_article,
    star_schema.dim_date,
    star_schema.dim_sales_channel
TO hm_product_sales_analyst;


-- ========================================
-- 2. CUSTOMER ANALYST
-- ========================================

GRANT SELECT ON ALL TABLES IN SCHEMA star_schema
TO hm_customer_analyst;
