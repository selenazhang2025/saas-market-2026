-- ============================================================
-- Schema Overview
-- Quick orientation queries: table sizes and structure.
-- Run: sqlite3 data/raw/comparedge.db < sql/01_schema_overview.sql
-- ============================================================

-- Row counts per table
SELECT 'categories' AS table_name, COUNT(*) AS row_count FROM categories
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'pricing_plans', COUNT(*) FROM pricing_plans
UNION ALL
SELECT 'features', COUNT(*) FROM features
UNION ALL
SELECT 'price_history', COUNT(*) FROM price_history;

-- Categories and how many products fall in each
SELECT slug, name, product_count
FROM categories
ORDER BY product_count DESC;

-- Sanity check: does product_count on categories match actual COUNT(*)?
SELECT c.slug, c.product_count AS stated_count, COUNT(p.id) AS actual_count
FROM categories c
LEFT JOIN products p ON p.category_id = c.id
GROUP BY c.id
HAVING stated_count <> actual_count;
