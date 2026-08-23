-- ============================================================
-- Business Questions
-- Each query answers a specific market/pricing-strategy question
-- about the 331 SaaS products in the dataset.
-- ============================================================

-- Q1: Which categories are the most expensive vs cheapest to enter,
-- based on each product's cheapest paid (non-zero) plan?
-- CAVEAT: excludes 'dex' — its pricing_plans.price_monthly stores swap-fee
-- percentages, not USD/month subscription prices, so it isn't comparable
-- to the rest of the market (see sql/02_data_quality_checks.sql).
WITH cheapest_paid_plan AS (
  SELECT product_id, MIN(price_monthly) AS entry_price
  FROM pricing_plans
  WHERE price_monthly > 0
  GROUP BY product_id
)
SELECT c.name AS category,
       COUNT(DISTINCT p.id) AS product_count,
       ROUND(AVG(cpp.entry_price), 2) AS avg_entry_price,
       ROUND(MIN(cpp.entry_price), 2) AS min_entry_price,
       ROUND(MAX(cpp.entry_price), 2) AS max_entry_price
FROM products p
JOIN categories c ON c.id = p.category_id
JOIN cheapest_paid_plan cpp ON cpp.product_id = p.id
WHERE c.slug <> 'dex'
GROUP BY c.id
ORDER BY avg_entry_price DESC;

-- Q2: What share of products in each category offer a free plan?
SELECT c.name AS category,
       COUNT(DISTINCT p.id) AS product_count,
       SUM(CASE WHEN p.has_free_tier THEN 1 ELSE 0 END) AS free_tier_count,
       ROUND(100.0 * SUM(CASE WHEN p.has_free_tier THEN 1 ELSE 0 END) / COUNT(DISTINCT p.id), 1) AS free_tier_pct
FROM products p
JOIN categories c ON c.id = p.category_id
GROUP BY c.id
ORDER BY free_tier_pct DESC;

-- Q3: How common is each billing model, and how does average price differ by model?
SELECT billing_model,
       COUNT(*) AS plan_count,
       ROUND(AVG(price_monthly), 2) AS avg_price_monthly
FROM pricing_plans
WHERE price_monthly IS NOT NULL
GROUP BY billing_model
ORDER BY plan_count DESC;

-- Q4: Top 10 highest-rated products overall.
-- NOTE: review_count is unpopulated (always 0) in this dataset, so it's
-- selected for visibility only, not used as a reliability signal.
SELECT p.name, c.name AS category, p.overall_rating, p.g2_rating, p.capterra_rating, p.review_count
FROM products p
JOIN categories c ON c.id = p.category_id
WHERE p.overall_rating IS NOT NULL
ORDER BY p.overall_rating DESC, p.review_count DESC
LIMIT 10;

-- Q5: Best-rated product in each category ("category leader" board).
SELECT c.name AS category, p.name AS top_product, p.overall_rating
FROM products p
JOIN categories c ON c.id = p.category_id
WHERE p.overall_rating = (
  SELECT MAX(p2.overall_rating) FROM products p2 WHERE p2.category_id = p.category_id
)
ORDER BY p.overall_rating DESC;

-- Q6: Does having more features correlate with a higher entry price?
-- (feature_count per product vs cheapest paid plan price)
WITH feature_counts AS (
  SELECT product_id, COUNT(*) AS feature_count
  FROM features
  WHERE LOWER(feature_value) = 'true'
  GROUP BY product_id
),
cheapest_paid_plan AS (
  SELECT product_id, MIN(price_monthly) AS entry_price
  FROM pricing_plans
  WHERE price_monthly > 0
  GROUP BY product_id
)
SELECT p.name, fc.feature_count, cpp.entry_price
FROM products p
JOIN feature_counts fc ON fc.product_id = p.id
JOIN cheapest_paid_plan cpp ON cpp.product_id = p.id
ORDER BY fc.feature_count DESC;

-- Q7: "Best value" leaderboard — free-tier products ranked by rating,
-- restricted to categories with at least 5 products for a fair comparison.
SELECT p.name, c.name AS category, p.overall_rating, p.review_count
FROM products p
JOIN categories c ON c.id = p.category_id
WHERE p.has_free_tier = 1
  AND p.overall_rating IS NOT NULL
  AND c.product_count >= 5
ORDER BY p.overall_rating DESC, p.review_count DESC
LIMIT 15;

-- Q8: Prevalence of "contact sales" custom pricing (no listed number) by category —
-- a proxy for how enterprise-oriented a category's go-to-market is.
SELECT c.name AS category,
       COUNT(pp.id) AS total_plans,
       SUM(CASE WHEN pp.price_monthly IS NULL THEN 1 ELSE 0 END) AS custom_price_plans,
       ROUND(100.0 * SUM(CASE WHEN pp.price_monthly IS NULL THEN 1 ELSE 0 END) / COUNT(pp.id), 1) AS custom_price_pct
FROM pricing_plans pp
JOIN products p ON p.id = pp.product_id
JOIN categories c ON c.id = p.category_id
GROUP BY c.id
HAVING total_plans >= 5
ORDER BY custom_price_pct DESC;

-- Q9: Does company age relate to rating or pricing? (founded_year decade bucket)
WITH cheapest_paid_plan AS (
  SELECT product_id, MIN(price_monthly) AS entry_price
  FROM pricing_plans
  WHERE price_monthly > 0
  GROUP BY product_id
)
SELECT
  (founded_year / 5) * 5 AS founded_period_start,
  COUNT(*) AS product_count,
  ROUND(AVG(p.overall_rating), 2) AS avg_rating,
  ROUND(AVG(cpp.entry_price), 2) AS avg_entry_price
FROM products p
LEFT JOIN cheapest_paid_plan cpp ON cpp.product_id = p.id
WHERE p.founded_year IS NOT NULL
GROUP BY founded_period_start
ORDER BY founded_period_start;

-- Q10: Which feature categories (ai, security, integration, etc.) are most
-- associated with higher-priced products? Average entry price of products
-- that have at least one feature flagged true in that category.
WITH cheapest_paid_plan AS (
  SELECT product_id, MIN(price_monthly) AS entry_price
  FROM pricing_plans
  WHERE price_monthly > 0
  GROUP BY product_id
)
SELECT f.category AS feature_category,
       COUNT(DISTINCT f.product_id) AS product_count,
       ROUND(AVG(cpp.entry_price), 2) AS avg_entry_price_of_adopters
FROM features f
JOIN cheapest_paid_plan cpp ON cpp.product_id = f.product_id
WHERE LOWER(f.feature_value) = 'true'
GROUP BY f.category
ORDER BY avg_entry_price_of_adopters DESC;

-- Q11: Most common individual features across the whole market (top 15).
SELECT feature_name, category, COUNT(*) AS product_count
FROM features
WHERE LOWER(feature_value) = 'true'
GROUP BY feature_name, category
ORDER BY product_count DESC
LIMIT 15;

-- Q12: "Value score" ranking — overall_rating per dollar of entry price,
-- surfaces well-rated tools that are cheap to get into (capped to paid tools
-- to avoid dividing by zero).
-- NOTE: products.review_count is 0 for every row in this dataset (an
-- unpopulated column, not real data), so it can't be used as a reliability
-- filter here the way a live G2/Capterra dataset would allow.
WITH cheapest_paid_plan AS (
  SELECT product_id, MIN(price_monthly) AS entry_price
  FROM pricing_plans
  WHERE price_monthly > 0
  GROUP BY product_id
)
SELECT p.name, c.name AS category, p.overall_rating, cpp.entry_price,
       ROUND(p.overall_rating / cpp.entry_price, 3) AS value_score
FROM products p
JOIN categories c ON c.id = p.category_id
JOIN cheapest_paid_plan cpp ON cpp.product_id = p.id
WHERE p.overall_rating IS NOT NULL
ORDER BY value_score DESC
LIMIT 15;
