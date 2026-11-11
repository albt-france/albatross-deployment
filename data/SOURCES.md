# Data sources

## 1. Public data on Albatross (PUBLIC DATA)
All facts are in [`public/albatross_facts.csv`](public/albatross_facts.csv), one row per fact, with the source URL and the collection date.

| Page | URL | Collected | Used for |
|---|---|---|---|
| Home | https://usealbatross.ai/ | 2026-11-11 | scale (3B+ requests/month, 50M+ users/month, 150M+ products, 12 countries), technology layers, APIs, customer results, research list |
| Technology | https://usealbatross.ai/technology | 2026-11-11 | sequential embedding models, catalog / user / serving layers, new listings recommendable within minutes |
| Primitives | https://usealbatross.ai/primitives | 2026-11-11 | Discovery Feed, Similar Items, Playlist, Contextual Search (inputs and use cases) |
| The 7-week evaluation | https://usealbatross.ai/evaluation | 2026-11-11 | timeline (weeks 1-2, 3-4, 5-7), team (engineering lead + PM), data (event triplets + catalog), 3-month commitment, goal |
| Customers | https://usealbatross.ai/customers | 2026-11-11 | Wallapop +119 % homepage engagement, +11 % sold items; OfferUp +84 % homepage engagement, +15 % purchase intent |
| Wallapop case study | https://usealbatross.ai/customers/wallapop | 2026-11-11 | +118.9 % engagement, +46.9 % purchase intent, similar-items coverage 50 % -> 94 %, scale of the deployment |
| API pricing | https://usealbatross.ai/pricing | 2026-11-11 | platform fee by MAU tier (EUR 10k-40k / month), usage EUR 0.50 / 0.25 / 0.10 per 1,000 predictions, +10 % per extra primitive |
| Company | https://usealbatross.ai/company | 2026-11-11 | founded 2024, Switzerland, USD 16M seed (MMC Ventures, Redalpine, Daphni), Tech for Retail 2025 award |
| Resources | https://usealbatross.ai/resources | 2026-11-11 | research papers and press list |
| Funding release (Nov 2025) | https://finance.yahoo.com/news/albatross-raises-12-5-million-133500967.html | 2026-11-11 | USD 12.5M round led by MMC Ventures |
| Research | arXiv 2609.00913 (SwapRec), arXiv 2508.18442 (DenseRec), CEUR-WS Vol-4188 paper 6, arXiv 2408.09168 (Multinomial Blending) | 2026-11-11 | titles and one-line claims as listed on the site; papers not reproduced |

Collection rules: `robots.txt` read first (general crawling allowed; AI-training crawlers disallowed; this study does not train anything).
One request every 3 seconds, 13 pages, one dated snapshot. The site's terms of use do not allow republishing its content,
so the page copies stay local (`data/raw/albatross_site/`, git-ignored) and only facts, figures and links are published here.
Customer results are quoted as published by Albatross and its customers; no logo is used.

## 2. Real dataset used as "the customer's first data drop" (REAL DATASET)
**RetailRocket e-commerce dataset** (Retail Rocket, published on Kaggle as `retailrocket/ecommerce-dataset`). Licence: **CC BY-NC-SA 4.0**.
Downloaded without login from a public Hugging Face mirror (`DanielKiani/RetailRocket-Recommender-Data`) on 2026-11-11, then checked
against the totals published with the original dataset:

| Check | Value found | Published |
|---|---|---|
| events.csv rows | 2,756,101 | 2,756,101 |
| distinct visitors | 1,407,580 | 1,407,580 |
| view / addtocart / transaction | 2,664,312 / 69,332 / 22,457 | same |
| item_properties rows (2 files) | 20,275,902 | 20,275,902 |

SHA-256 of the files used:
```
3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7  events.csv
30aad5aeca58b2dc27dcc73e1708565f5818e45adb3eb57401f91e87355b0b81  item_properties_part1.csv
d5e7d1a91dc40f522aeb596b267e6c87d8aed689a7192d12369cfb165eb987e5  item_properties_part2.csv
94e865eb0a3d48cbbfe3b79079018dd92509315c88f5fd8d00d0b4b5af434f5b  category_tree.csv
```
The raw files are **not redistributed**. To reproduce, place the four CSV files in `data/raw/retailrocket/` (from Kaggle or the mirror)
and run `python src/load_dataset.py`. Aggregated tables derived from the dataset (`data/public/intake/`, `data/public/baselines/`,
`data/public/ab_design/`) are shared under the same licence, CC BY-NC-SA 4.0, with attribution to Retail Rocket.

## 3. Simulated data (SIMULATED)
`data/simulated/` is produced by `src/simulate.py` (fixed seed 42) and by the scripts that analyse it. It is **not** Albatross data and
**not** customer data. Calibration and every assumption: [`ASSUMPTIONS.md`](ASSUMPTIONS.md).
The visitor-level A/B table (2 M rows) is regenerated locally in `data/work/` and not committed.

## 4. Synthetic test data
`examples/` and the pytest fixtures come from `tests/sample_data.py`: a small invented data drop with known, injected anomalies.
