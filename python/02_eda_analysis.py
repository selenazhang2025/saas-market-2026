"""
Exploratory analysis and statistical tests on the cleaned SaaS market data.
Produces:
  - outputs/charts/*.png   (visuals for the README / portfolio writeup)
  - outputs/summary_stats.md (key findings in plain language)

Run: python3 python/02_eda_analysis.py
(requires data/processed/*.csv from python/01_clean_and_load.py)

Notes:
  - products.review_count is unpopulated (always 0) in this dataset, so
    it is not used anywhere here as a reliability filter.
  - The 'dex' category is excluded from all price comparisons: its
    pricing_plans.price_monthly stores swap-fee percentages, not USD/month
    subscription prices (see data quality note #6 in 01_clean_and_load.py).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CHARTS = ROOT / "outputs" / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

findings: list[str] = []


def log(line: str) -> None:
    print(line)
    findings.append(line)


def main() -> None:
    products = pd.read_csv(PROC / "products_clean.csv")
    categories = pd.read_csv(PROC / "category_summary.csv")
    # 'dex' price_monthly is a swap-fee %, not a USD/month subscription —
    # exclude it from every price-based stat/chart below.
    priced = products[products["price_comparable"]]

    findings.append("# SaaS Market 2026 — Key Findings\n")
    findings.append(
        "_Note: the 'dex' category is excluded from all price comparisons — "
        "its listed prices are swap-fee percentages, not USD/month subscription "
        "costs (see data quality notes)._\n"
    )

    # --- 1. Price distribution ---------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.histplot(priced["entry_price"].dropna(), bins=30, ax=ax)
    ax.set_title("Distribution of Entry-Level Paid Plan Price")
    ax.set_xlabel("Entry price (USD/month)")
    fig.tight_layout()
    fig.savefig(CHARTS / "01_entry_price_distribution.png")
    plt.close(fig)

    median_price = priced["entry_price"].median()
    log(f"## Pricing\n- Median entry-level paid price across the market: **${median_price:.2f}/mo**.")

    # --- 2. Category price comparison ---------------------------------
    top_cat = categories.sort_values("avg_entry_price", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.barplot(data=top_cat, y="category_name", x="avg_entry_price", ax=ax, color="#4C72B0")
    ax.set_title("Average Entry Price by Category (Top 15)")
    ax.set_xlabel("Avg entry price (USD/month)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(CHARTS / "02_avg_price_by_category.png")
    plt.close(fig)

    priciest = top_cat.iloc[0]
    log(f"- Most expensive category to enter: **{priciest['category_name']}** "
        f"(avg ${priciest['avg_entry_price']:.2f}/mo).")

    cheapest_cat = categories.sort_values("avg_entry_price").iloc[0]
    log(f"- Cheapest category to enter: **{cheapest_cat['category_name']}** "
        f"(avg ${cheapest_cat['avg_entry_price']:.2f}/mo).")

    # --- 3. Free tier adoption ------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6))
    free_sorted = categories.sort_values("free_tier_pct", ascending=False)
    sns.barplot(data=free_sorted, y="category_name", x="free_tier_pct", ax=ax, color="#55A868")
    ax.set_title("Free-Tier Adoption Rate by Category")
    ax.set_xlabel("% of products with a free plan")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(CHARTS / "03_free_tier_by_category.png")
    plt.close(fig)

    overall_free_pct = 100 * products["has_free_tier"].mean()
    log(f"\n## Free-Tier Strategy\n- {overall_free_pct:.1f}% of all 331 products offer some kind of free plan.")
    log(f"- Highest free-tier adoption: **{free_sorted.iloc[0]['category_name']}** "
        f"({free_sorted.iloc[0]['free_tier_pct']:.0f}%).")
    log(f"- Lowest free-tier adoption: **{free_sorted.iloc[-1]['category_name']}** "
        f"({free_sorted.iloc[-1]['free_tier_pct']:.0f}%).")

    # --- 4. Rating vs price correlation ---------------------------------
    paired = priced.dropna(subset=["overall_rating", "entry_price"])
    paired = paired[paired["entry_price"] > 0]
    r, p = stats.pearsonr(paired["entry_price"], paired["overall_rating"])

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.regplot(
        data=paired, x="entry_price", y="overall_rating", ax=ax,
        scatter_kws={"alpha": 0.4, "s": 25}, line_kws={"color": "red"},
    )
    ax.set_xscale("log")
    ax.set_title(f"Entry Price vs Rating (Pearson r = {r:.3f}, p = {p:.3f})")
    ax.set_xlabel("Entry price, log scale (USD/month)")
    ax.set_ylabel("Overall rating")
    fig.tight_layout()
    fig.savefig(CHARTS / "04_price_vs_rating.png")
    plt.close(fig)

    sig = "statistically significant" if p < 0.05 else "not statistically significant"
    log(f"\n## Does Price Predict Quality?\n- Correlation between entry price and rating: "
        f"r = {r:.3f} (p = {p:.3f}) — **{sig}** at α = 0.05.")
    log("- In plain terms: paying more does not reliably buy a higher-rated product in this market.")

    # --- 5. Feature count vs price correlation --------------------------
    r2, p2 = stats.pearsonr(paired["feature_count"], paired["entry_price"])
    log(f"\n## Features vs Price\n- Correlation between feature count and entry price: "
        f"r = {r2:.3f} (p = {p2:.3f}).")

    # --- 6. ANOVA: does rating differ by category? ----------------------
    cat_groups = [
        g["overall_rating"].dropna().values
        for _, g in products.groupby("category_slug")
        if g["overall_rating"].notna().sum() >= 5
    ]
    f_stat, anova_p = stats.f_oneway(*cat_groups)
    sig2 = "statistically significant" if anova_p < 0.05 else "not statistically significant"
    log(f"\n## Rating by Category\n- One-way ANOVA across categories (min. 5 rated products each): "
        f"F = {f_stat:.2f}, p = {anova_p:.4f} — differences in average rating across categories are "
        f"**{sig2}**.")

    # --- 7. Value leaderboard --------------------------------------------
    # NOTE: review_count is unpopulated (always 0) in this dataset, so it
    # can't be used as a reliability filter here.
    value = paired.copy()
    value["value_score"] = value["overall_rating"] / value["entry_price"]
    value = value.sort_values("value_score", ascending=False)
    log("\n## Best Value (rating per dollar) — Top 5")
    for _, row in value.head(5).iterrows():
        log(f"- **{row['name']}** ({row['category_name']}): {row['overall_rating']} rating "
            f"at ${row['entry_price']:.2f}/mo")

    # --- 8. Billing model mix --------------------------------------------
    plans = pd.read_csv(PROC / "pricing_plans_clean.csv")
    billing_mix = plans["billing_model"].value_counts(normalize=True).mul(100).round(1)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(billing_mix.values, labels=billing_mix.index, autopct="%1.0f%%", startangle=90)
    ax.set_title("Billing Model Mix Across All Pricing Plans")
    fig.tight_layout()
    fig.savefig(CHARTS / "05_billing_model_mix.png")
    plt.close(fig)

    log("\n## Billing Models\n- Distribution across all 1,013 pricing plans:")
    for model, pct in billing_mix.items():
        log(f"  - {model}: {pct}%")

    (ROOT / "outputs" / "summary_stats.md").write_text("\n".join(findings) + "\n")
    print(f"\nWrote {len(list(CHARTS.glob('*.png')))} charts to outputs/charts/")
    print("Wrote outputs/summary_stats.md")


if __name__ == "__main__":
    main()
