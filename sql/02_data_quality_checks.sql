-- ============================================================
-- Data Quality Checks
-- Documents the known messiness in the dataset before any
-- analysis is trusted. Findings here justify the cleaning
-- steps applied in python/01_clean_and_load.py.
-- ============================================================

-- Products missing an overall rating
SELECT id, name, g2_rating, capterra_rating, overall_rating
FROM products
WHERE overall_rating IS NULL;

-- Pricing plans with no numeric monthly price (i.e. "Contact Sales" / custom enterprise pricing)
SELECT p.name, pp.plan_name, pp.price_monthly, pp.billing_model
FROM pricing_plans pp
JOIN products p ON p.id = pp.product_id
WHERE pp.price_monthly IS NULL
ORDER BY p.name;

-- % of pricing plans that are custom/"contact sales" pricing
SELECT
  ROUND(100.0 * SUM(CASE WHEN price_monthly IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_custom_pricing
FROM pricing_plans;

-- Duplicate product slugs (should be zero — slug is UNIQUE, this just confirms)
SELECT slug, COUNT(*) FROM products GROUP BY slug HAVING COUNT(*) > 1;

-- Products with zero pricing plans on record
SELECT p.id, p.name
FROM products p
LEFT JOIN pricing_plans pp ON pp.product_id = p.id
WHERE pp.id IS NULL;

-- Products with zero features on record
SELECT p.id, p.name
FROM products p
LEFT JOIN features f ON f.product_id = p.id
WHERE f.id IS NULL;

-- founded_year outliers (before 1990 or after current year, or missing)
SELECT id, name, founded_year
FROM products
WHERE founded_year IS NULL OR founded_year < 1990 OR founded_year > 2026;

-- DEX (decentralized exchange) pricing plans: check whether price_monthly
-- is actually a swap-fee percentage rather than a $/month subscription cost.
SELECT p.name, pp.plan_name, pp.price_monthly, pp.billing_model
FROM pricing_plans pp
JOIN products p ON p.id = pp.product_id
JOIN categories c ON c.id = p.category_id
WHERE c.slug = 'dex' AND pp.price_monthly > 0
ORDER BY pp.price_monthly
LIMIT 10;
-- FINDING: DEX plan names are things like "0.01% Pool Fee" with
-- price_monthly = 0.01 — the source data stored a swap-fee PERCENTAGE in
-- the same numeric field used elsewhere for a USD/month subscription price.
-- DEX products don't have real monthly subscriptions at all (on-chain
-- protocols charge per-swap fees, not SaaS billing). Treat 'dex' entry
-- prices as not comparable to every other category's entry prices, and
-- exclude it from any "cheapest/most expensive category" ranking.
-- (Spot-checked the other crypto categories — crypto-exchanges,
-- defi-tools, crypto-trading-bots, etc. — none show this pattern.)

-- review_count: is it actually populated anywhere?
SELECT MIN(review_count), MAX(review_count), AVG(review_count) FROM products;
-- FINDING: min = max = avg = 0. review_count is unpopulated for all 331
-- products — treat it as a placeholder column, not a real reliability signal.

-- Rating scale check: anything outside a plausible 0-5 range
SELECT id, name, g2_rating, capterra_rating, overall_rating
FROM products
WHERE g2_rating NOT BETWEEN 0 AND 5
   OR capterra_rating NOT BETWEEN 0 AND 5
   OR overall_rating NOT BETWEEN 0 AND 5;

-- "Phantom umbrella" category check: categories.product_count is denormalized
-- and can drift from reality. Compare stated vs actual per category.
SELECT c.slug, c.product_count AS stated_count, COUNT(p.id) AS actual_count
FROM categories c
LEFT JOIN products p ON p.category_id = c.id
GROUP BY c.id
HAVING stated_count <> actual_count;
-- FINDING: 'ai-tools' (category_id=1) is stated as having 104 products but
-- has ZERO products directly tagged with category_id=1. Its stated count
-- exactly equals the sum of all 'ai-*' subcategories plus 'llm' (104 total) —
-- confirm with the query below. It's a rollup/umbrella label the source data
-- never actually assigned to any product, not a real leaf category. Naive
-- category-level analysis should exclude it (or explicitly treat it as a
-- parent grouping), otherwise it looks like an empty category or gets
-- silently dropped from INNER JOIN results while double-counting AI tools
-- if included alongside its subcategories.
SELECT SUM(cnt) AS ai_subcategory_total FROM (
  SELECT COUNT(*) AS cnt FROM products p
  JOIN categories c ON c.id = p.category_id
  WHERE c.slug LIKE 'ai-%' OR c.slug = 'llm'
);
