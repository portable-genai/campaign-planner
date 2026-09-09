"""The demo book: one audience warehouse, served the same way on the laptop and the deployment.

Pinned here, and each was watched failing first:

* **the managed dataset exists at all.** This repository had no ``bigquery.tf``: the API was
  enabled, the IAM roles were granted and the CMEK binding was in place, all naming a dataset
  and two tables nothing created. The managed profile would have failed at the first request
  on a deployment, and nothing offline could see it because the local profile served an
  in-process dictionary and ran no SQL;
* the managed adapter selects only columns the Terraform declares, and the shipped book
  carries exactly those columns, so a load cannot be short a field;
* the book's own arithmetic: a segment cannot be reachable beyond its own population, a
  consent rate cannot exceed one, and a channel cannot have a zero CPM, which would make it
  look free and take the whole budget.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from campaign_planner import demo_book
from campaign_planner.adapters.gcp import bigquery_audience as managed
from campaign_planner.adapters.local.audience import LocalAudienceDataAdapter
from campaign_planner.config import LocalSettings, Settings
from campaign_planner.domain.models import Market, Vertical

_REPO = Path(__file__).resolve().parents[2]
_TF = _REPO / "infra" / "terraform" / "bigquery.tf"

_SCOPE = (Market.SG, Vertical.BANKING)


def _settings() -> Settings:
    base = Settings.load("config/settings.yaml")
    return dataclasses.replace(
        base,
        profile="local",
        local=LocalSettings(audit_path=":memory:", book_path=":memory:"),
    )


@pytest.fixture
def store() -> LocalAudienceDataAdapter:
    adapter = LocalAudienceDataAdapter(_settings())
    yield adapter
    adapter.close()


# --------------------------------------------------------------------------- #
# The shipped rows
# --------------------------------------------------------------------------- #
def test_the_shipped_book_is_internally_consistent() -> None:
    demo_book.validate()
    assert len(demo_book.BOOK.rows("audience_segments")) == 12
    assert len(demo_book.BOOK.rows("channel_benchmarks")) == 30
    assert demo_book.BOOK.manifest()["fictional"] is True


@pytest.mark.parametrize(
    ("table", "field", "value", "message"),
    [
        ("audience_segments", "reachable_size", 10**9, "reachable beyond its own population"),
        ("audience_segments", "consent_rate", 1.5, "consent rate outside"),
        ("audience_segments", "expected_value", 0.0, "no expected value"),
        ("channel_benchmarks", "cpm", 0.0, "zero or negative CPM"),
        ("channel_benchmarks", "max_reach", 0, "can reach nobody"),
    ],
)
def test_the_book_refuses_a_row_the_engine_could_not_spend_against(
    monkeypatch: pytest.MonkeyPatch, table: str, field: str, value: object, message: str
) -> None:
    """Each of these is arithmetic the allocation engine depends on, silently breakable."""
    real = demo_book.BOOK.rows

    def broken(name: str):  # type: ignore[no-untyped-def]
        rows = real(name)
        return [dict(rows[0], **{field: value}), *rows[1:]] if name == table else rows

    monkeypatch.setattr(demo_book.BOOK, "rows", broken)
    with pytest.raises(demo_book.BookError, match=message):
        demo_book.validate()


def test_a_market_with_segments_and_no_benchmarks_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan for an audience with nothing to spend on is a plan that cannot be made."""
    real = demo_book.BOOK.rows

    def broken(name: str):  # type: ignore[no-untyped-def]
        rows = real(name)
        if name == "channel_benchmarks":
            return [r for r in rows if r["market"] != "SG"]
        return rows

    monkeypatch.setattr(demo_book.BOOK, "rows", broken)
    with pytest.raises(demo_book.BookError, match="no channel benchmarks"):
        demo_book.validate()


# --------------------------------------------------------------------------- #
# The managed schema, which did not exist
# --------------------------------------------------------------------------- #
def _terraform_tables() -> dict[str, set[str]]:
    assert _TF.exists(), (
        "infra/terraform/bigquery.tf is missing. The adapter queries a dataset and two "
        "tables; without this file nothing creates them and the managed profile fails at "
        "the first request."
    )
    text = _TF.read_text(encoding="utf-8")
    blocks = re.findall(
        r'resource\s+"google_bigquery_table"\s+"\w+"\s*\{(.*?)\n\}', text, flags=re.DOTALL
    )
    assert blocks, "no google_bigquery_table blocks found; the regex or the file moved"
    out: dict[str, set[str]] = {}
    for block in blocks:
        table_id = re.search(r'table_id\s*=\s*"(\w+)"', block)
        assert table_id is not None
        out[table_id.group(1)] = set(re.findall(r'name\s*=\s*"(\w+)"', block))
    return out


def test_the_dataset_the_settings_name_is_actually_created() -> None:
    """The settings named it, the IAM granted it, and nothing created it."""
    text = _TF.read_text(encoding="utf-8")
    dataset = _settings().bigquery.dataset
    assert f'dataset_id  = "{dataset}"' in text or f'dataset_id = "{dataset}"' in text, (
        f"no google_bigquery_dataset creates {dataset!r}"
    )


def test_the_managed_adapter_selects_only_columns_the_terraform_declares() -> None:
    declared = _terraform_tables()
    settings = _settings()
    for table_key, columns in managed.SELECTED_COLUMNS.items():
        table_id = getattr(settings.bigquery, table_key)
        assert table_id in declared, f"{table_key} -> {table_id!r} is not a Terraform table"
        undeclared = sorted(set(columns) - declared[table_id])
        assert not undeclared, f"{table_id} selects columns Terraform never declares: {undeclared}"


def test_the_book_and_the_terraform_declare_the_same_columns() -> None:
    """The set checked is ``load_order()``, so it includes the manifest the loader writes.

    ``TABLES`` is this repository's own tables and the loader writes one more: the manifest,
    stamped last because it records the load that wrote the others. The loader creates
    nothing, so a manifest missing from the Terraform is a load that exits before its first
    row -- which is exactly what iterating ``TABLES`` cannot see, and what it did not see in
    a sibling repository.
    """
    declared = _terraform_tables()
    for table in demo_book.BOOK.load_order():
        assert table.name in declared, f"the book ships {table.name} and Terraform does not"
        book_columns, tf_columns = sorted(table.columns), sorted(declared[table.name])
        assert book_columns == tf_columns, (
            f"{table.name}: book {book_columns} vs terraform {tf_columns}"
        )


# --------------------------------------------------------------------------- #
# The DuckDB store
# --------------------------------------------------------------------------- #
def test_the_store_serves_the_shipped_segments_most_responsive_first(
    store: LocalAudienceDataAdapter,
) -> None:
    segments = store.segments("grow deposits", *_SCOPE)
    shipped = [
        row
        for row in demo_book.BOOK.rows("audience_segments")
        if row["market"] == "SG" and row["vertical"] == "banking"
    ]
    assert [s.id for s in segments] == [
        row["id"] for row in sorted(shipped, key=lambda r: -r["propensity"])
    ]
    assert all(s.citations for s in segments), "a segment must cite the row it came from"


def test_consented_reach_is_never_more_than_reachable(store: LocalAudienceDataAdapter) -> None:
    """The only audience a campaign may target, and the book is where it can go wrong."""
    for segment in store.segments("grow deposits", *_SCOPE):
        assert segment.consented_reachable <= segment.reachable_size
        assert segment.reachable_size <= segment.size


def test_benchmarks_come_back_for_the_requested_scope_only(
    store: LocalAudienceDataAdapter,
) -> None:
    benchmarks = store.channel_benchmarks(*_SCOPE)
    assert benchmarks, "the SG banking scope has no channels to spend on"
    assert all(b.market is Market.SG and b.vertical is Vertical.BANKING for b in benchmarks)
    assert all(b.cpm > 0 for b in benchmarks), "a zero CPM would look free to buy"


def test_an_unknown_scope_returns_nothing_rather_than_someone_else_s_audience(
    store: LocalAudienceDataAdapter,
) -> None:
    assert store.segments("grow deposits", Market.JP, Vertical.ONLINE_RETAIL) != ()
    assert store.channel_benchmarks(Market.JP, Vertical.ONLINE_RETAIL) != ()
