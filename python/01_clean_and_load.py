"""
Clean and consolidate the ComparEdge SaaS dataset (SQLite) into flat,
analysis-ready tables for the EDA and Excel dashboard steps.

Data quality issues handled here (see sql/02_data_quality_checks.sql for
the SQL-side detection of these same issues):
  1. `features.feature_value` has inconsistent casing ('True' vs 'true').
  2. `categories` row 'ai-tools' is a phantom umbrella label — its
     denormalized product_count (104) is never actually assigned to any
     product; the real AI products live in the ai-* subcategories + llm.
     We drop this row from the working category list and flag it in a
     data-quality note instead of silently double-counting or dropping data.
  3. `products.overall_rating` is NULL for 11 products (mostly hardware
     crypto wallets that don't carry G2/Capterra reviews) — kept as NULL,
     not imputed, since a fabricated rating would be misleading.
  4. `pricing_plans.price_monthly` is NULL for ~97 plans ("Contact Sales" /
     custom enterprise pricing) — kept as NULL, and a separate boolean flag
     captures "this product has at least one custom-priced plan".
  5. A few `categories.name` values are auto-titlecased acronyms ("Crm",
     "Dex", "Vpn", "Defi Tools") — corrected to CRM, DEX, VPN, DeFi Tools.
  6. `pricing_plans.price_monthly` for the 'dex' category stores swap-fee
     PERCENTAGES (e.g. "0.01% Pool Fee" -> 0.01), not USD/month subscription
     prices — DEX protocols don't have SaaS-style billing. A
     `price_comparable` flag marks these products so cross-category price
     analysis can exclude them instead of silently treating 0.01 as "$0.01/mo".

Run: python3 python/01_clean_and_load.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "raw" / "comparedge.db"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PHANTOM_CATEGORY_SLUG = "ai-tools"


def load_raw_tables(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    tables = ["categories", "products", "pricing_plans", "features", "price_history"]
    return {t: pd.read_sql_query(f"SELECT * FROM {t}", conn) for t in tables}


CATEGORY_NAME_FIXES = {
    "Crm": "CRM",
    "Dex": "DEX",
    "Vpn": "VPN",
    "Defi Tools": "DeFi Tools",
}


def clean_categories(categories: pd.DataFrame) -> pd.DataFrame:
    clean = categories[categories["slug"] != PHANTOM_CATEGORY_SLUG].copy()
    clean["name"] = clean["name"].replace(CATEGORY_NAME_FIXES)
    return clean.rename(
        columns={"id": "category_id", "name": "category_name", "slug": "category_slug"}
    )


def clean_features(features: pd.DataFrame) -> pd.DataFrame:
    clean = features.copy()
    clean["feature_value"] = clean["feature_value"].str.lower()
    clean["is_true"] = clean["feature_value"] == "true"
    return clean


def build_feature_summary(features_clean: pd.DataFrame) -> pd.DataFrame:
    true_features = features_clean[features_clean["is_true"]]
    per_product = (
        true_features.groupby("product_id")
        .agg(feature_count=("feature_name", "count"))
        .reset_index()
    )
    return per_product


def build_pricing_summary(pricing_plans: pd.DataFrame) -> pd.DataFrame:
    plans = pricing_plans.copy()
    plans["is_custom_price"] = plans["price_monthly"].isna()

    paid_plans = plans[plans["price_monthly"] > 0]
    entry_price = (
        paid_plans.groupby("product_id")["price_monthly"]
        .min()
        .rename("entry_price")
        .reset_index()
    )

    per_product = (
        plans.groupby("product_id")
        .agg(
            plan_count=("id", "count"),
            has_custom_pricing=("is_custom_price", "any"),
            max_price_monthly=("price_monthly", "max"),
        )
        .reset_index()
    )
    per_product = per_product.merge(entry_price, on="product_id", how="left")
    return per_product


def build_products_clean(
    products: pd.DataFrame,
    categories_clean: pd.DataFrame,
    pricing_summary: pd.DataFrame,
    feature_summary: pd.DataFrame,
) -> pd.DataFrame:
    df = products.merge(
        categories_clean[["category_id", "category_name", "category_slug"]],
        on="category_id",
        how="left",
    )
    df = df.rename(columns={"id": "product_id"})
    df = df.merge(pricing_summary, on="product_id", how="left")
    df = df.merge(feature_summary, on="product_id", how="left")
    df["feature_count"] = df["feature_count"].fillna(0).astype(int)
    df["has_custom_pricing"] = df["has_custom_pricing"].fillna(False)
    df["has_free_tier"] = df["has_free_tier"].astype(bool)
    df["has_free_trial"] = df["has_free_trial"].astype(bool)
    df["price_comparable"] = df["category_slug"] != "dex"

    keep_cols = [
        "product_id", "name", "category_slug", "category_name",
        "overall_rating", "g2_rating", "capterra_rating", "review_count",
        "founded_year", "hq_location", "has_free_tier", "has_free_trial",
        "has_custom_pricing", "price_comparable", "entry_price", "max_price_monthly",
        "plan_count", "feature_count", "website_url", "comparedge_url",
    ]
    return df[keep_cols].sort_values("name").reset_index(drop=True)


def build_category_summary(products_clean: pd.DataFrame) -> pd.DataFrame:
    grouped = products_clean.groupby(["category_slug", "category_name"], dropna=True)
    summary = grouped.agg(
        product_count=("product_id", "count"),
        avg_rating=("overall_rating", "mean"),
        free_tier_count=("has_free_tier", "sum"),
        avg_feature_count=("feature_count", "mean"),
    ).reset_index()

    # entry price stats computed only from price-comparable products
    # (excludes 'dex', whose price_monthly is a swap-fee %, not USD/month —
    # see data quality note #6 at the top of this file)
    price_stats = (
        products_clean[products_clean["price_comparable"]]
        .groupby("category_slug")["entry_price"]
        .agg(avg_entry_price="mean", median_entry_price="median")
        .reset_index()
    )
    summary = summary.merge(price_stats, on="category_slug", how="left")
    summary["free_tier_pct"] = (
        100 * summary["free_tier_count"] / summary["product_count"]
    ).round(1)
    for col in ["avg_rating", "avg_entry_price", "median_entry_price", "avg_feature_count"]:
        summary[col] = summary[col].round(2)
    return summary.sort_values("product_count", ascending=False).reset_index(drop=True)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    raw = load_raw_tables(conn)
    conn.close()

    categories_clean = clean_categories(raw["categories"])
    features_clean = clean_features(raw["features"])
    feature_summary = build_feature_summary(features_clean)
    pricing_summary = build_pricing_summary(raw["pricing_plans"])

    products_clean = build_products_clean(
        raw["products"], categories_clean, pricing_summary, feature_summary
    )
    category_summary = build_category_summary(products_clean)

    plans_clean = raw["pricing_plans"].merge(
        raw["products"][["id", "name"]].rename(columns={"id": "product_id", "name": "product_name"}),
        on="product_id",
        how="left",
    )

    products_clean.to_csv(OUT_DIR / "products_clean.csv", index=False)
    category_summary.to_csv(OUT_DIR / "category_summary.csv", index=False)
    plans_clean.to_csv(OUT_DIR / "pricing_plans_clean.csv", index=False)
    features_clean.to_csv(OUT_DIR / "features_clean.csv", index=False)

    print(f"products_clean.csv      -> {len(products_clean)} rows")
    print(f"category_summary.csv    -> {len(category_summary)} rows")
    print(f"pricing_plans_clean.csv -> {len(plans_clean)} rows")
    print(f"features_clean.csv      -> {len(features_clean)} rows")
    print(f"\nDropped phantom category '{PHANTOM_CATEGORY_SLUG}' from category list.")
    print(f"Products with missing overall_rating: {products_clean['overall_rating'].isna().sum()}")
    print(f"Products with at least one custom-priced plan: {products_clean['has_custom_pricing'].sum()}")


if __name__ == "__main__":
    main()
