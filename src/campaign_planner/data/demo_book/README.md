# The demo book

A fictional audience warehouse: twelve addressable segments across three markets and two
verticals, and the per-channel cost and performance benchmarks the deterministic allocation
engine spends against. No row describes a real audience, publisher or rate card.

One file per table, newline-delimited JSON, keys in the column order the BigQuery schema in
`infra/terraform/bigquery.tf` declares. The same rows feed three consumers:

| Consumer | How it reads the files |
|---|---|
| The `local` profile | `adapters/local/audience.py` opens a DuckDB file holding the same two tables and, when they are empty, inserts these rows |
| The deployment | `scripts/load_demo_book.py` streams them into the `mkt_campaign_audience` dataset |
| Tests | `campaign_planner.demo_book` builds the domain objects |

| File | Rows | What a row is |
|---|---|---|
| `audience_segments.ndjson` | 12 | one segment: its population, the reachable subset, the consented fraction, its modelled propensity and per-conversion value |
| `channel_benchmarks.ndjson` | 30 | one channel in one market and vertical: CPM, click-through rate, conversion rate, reach ceiling, spend floor |
| `book_manifest.ndjson` | 1 | the book's version and `fictional: true`, which is what the loader's overwrite guard reads |

**The dataset these rows load into did not exist.** `config/settings.yaml` has named
`mkt_campaign_audience` and both tables since the repository was written, and the managed
adapter queries them. Everything around them was provisioned: the BigQuery API was enabled
with a comment naming this dataset, the serving identity had `dataViewer` and `jobUser`, and
the CMEK binding was in place. All of it pointed at something nothing created.

**Every number here is load-bearing.** The allocation engine divides by the CPM, caps at the
reach ceiling, and may only target the reachable AND consented subset, so a segment reachable
beyond its own population or a channel with a zero CPM is not a cosmetic error: it is a
budget split that looks computed and is wrong. `tests/contract/test_demo_book.py` refuses
each of those.
