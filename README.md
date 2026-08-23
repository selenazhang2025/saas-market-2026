# SaaS Market 2026 — Pricing & Positioning Analysis

An end-to-end data analysis project on a 331-product SaaS market dataset: **SQL** for
querying and data-quality auditing, **Python** for cleaning/EDA/statistical testing, and
**Excel** for a chart-backed dashboard.

Data source: ComparEdge SaaS Market dataset, downloaded from Kaggle — a relational export
covering 331 SaaS/crypto products across 28 categories (project management, CRM, LLMs,
crypto exchanges, password managers, etc.), snapshotted 2026-04-27.

## Why this project

Most portfolio pricing-analysis projects use a single flat CSV. This dataset is a real
relational schema (5 tables, 1 view of price history, JSON blobs, inconsistent casing, a
phantom category, a unit mismatch hiding in one category) — so the interesting work isn't
just "make a chart," it's catching what's wrong with the data *before* trusting the chart.

## Project structure

```
saas market 2026/
├── data/
│   ├── raw/                    # original Kaggle files (SQLite db + source CSVs), untouched
│   └── processed/               # cleaned CSVs output by python/01_clean_and_load.py
├── sql/
│   ├── 01_schema_overview.sql       # table sizes, category structure
│   ├── 02_data_quality_checks.sql   # every data issue found, with detection queries
│   └── 03_business_questions.sql    # 12 analysis queries (pricing, ratings, features, value)
├── python/
│   ├── 01_clean_and_load.py         # cleans raw data -> data/processed/*.csv
│   ├── 02_eda_analysis.py           # stats tests + charts -> outputs/
│   └── 03_build_excel_dashboard.py  # builds excel/saas_market_dashboard.xlsx
├── excel/
│   └── saas_market_dashboard.xlsx   # Overview, Dashboard, Products, Pricing Plans,
│                                     # Category Summary, Billing Models (formula-driven)
└── outputs/
    ├── charts/                      # PNG charts from the Python EDA
    └── summary_stats.md             # key findings in plain language
```

## How to reproduce

```bash
pip install -r python/requirements.txt
python3 python/01_clean_and_load.py
python3 python/02_eda_analysis.py
python3 python/03_build_excel_dashboard.py
```

SQL files can be run directly against the SQLite database:

```bash
sqlite3 data/raw/comparedge.db < sql/03_business_questions.sql
```

## Data quality issues found (and how they were handled)

This is the part worth highlighting on a resume — the dataset looks clean at a glance but
has several issues that would silently distort an analysis if missed:

| Issue | Detection | Fix |
|---|---|---|
| `ai-tools` category claims 104 products but 0 are actually tagged with it — its count is a rollup of every `ai-*` subcategory + `llm` that the source data never assigned directly | `sql/02_data_quality_checks.sql` — stated vs. actual `COUNT()` per category | Dropped the phantom category row from the working category list |
| `features.feature_value` mixes `'True'`/`'true'` casing (89 of 6,052 rows) | `SELECT DISTINCT feature_value` | Lowercased before filtering |
| `dex` category's `price_monthly` stores **swap-fee percentages** (e.g. `0.01` = "0.01% Pool Fee"), not USD/month subscription prices — DEX protocols don't bill like SaaS | Spot-checked low ($<1) prices per crypto category | Flagged with a `price_comparable` column; excluded from every cross-category price stat, chart, and correlation |
| `products.review_count` is `0` for all 331 rows — an unpopulated placeholder, not real data | `MIN()/MAX()/AVG()` all equal 0 | Never used as a reliability/tie-break signal |
| 11 products have no `overall_rating`; ~89 products have at least one "Contact Sales" plan (`price_monthly IS NULL`) | Null checks | Left as null/flagged rather than imputed — a guessed number is worse than a visible gap |
| A few category names were auto-titlecased acronyms (`Crm`, `Dex`, `Vpn`, `Defi Tools`) | Manual review of category list | Corrected to `CRM`, `DEX`, `VPN`, `DeFi Tools` |

## Key findings

- Median entry-level paid price across the market: **$16.00/mo**.
- **Crypto Analytics** is the most expensive category to enter (avg $153.71/mo); **Password
  Managers** is the cheapest (avg $2.79/mo), excluding the unit-mismatched `dex` category.
- 74.3% of all products offer a free tier — highest in **DeFi Tools** (100%), lowest in
  **VPN** (20%).
- Entry price does **not** correlate with rating (Pearson r = -0.014, p = 0.823) — paying
  more doesn't reliably buy a higher-rated product in this market.
- Average rating **does** differ significantly by category (one-way ANOVA, p < 0.0001).
- 79% of all pricing plans use flat pricing; only 3.2% are usage-based, despite usage-based
  billing being a common narrative in SaaS pricing discourse.

Full write-up with numbers for every finding: [outputs/summary_stats.md](outputs/summary_stats.md).

## Known limitations

- `price_history` contains a single snapshot date (2026-04-27) — no real time series exists
  in this dataset, so no trend analysis is included (a chart showing fake month-over-month
  movement would be worse than no chart at all).
- `review_count` being empty means "best value" and "top rated" rankings can't be weighted
  by review volume the way a live G2/Capterra pull would allow.
