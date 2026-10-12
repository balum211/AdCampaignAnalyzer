import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics import (  # noqa: E402
    Filters, apply_filters, campaign_table, insights, kpis, load_csv, normalize_columns,
    prepare, search_campaigns, summarize, timeseries,
)


@pytest.fixture(scope="module")
def data():
    return load_csv(ROOT / "data" / "ad_campaigns.csv")


def all_filters(df):
    return Filters(df.date.min(), df.date.max(), list(df.channel.unique()),
                   list(df.audience.unique()), list(df.goal.unique()))


def test_sample_has_four_channels(data):
    assert set(data.channel) == {"Facebook", "Instagram", "Pinterest", "Twitter"}


def test_kpis_match_raw_sums(data):
    k = kpis(data)
    assert k["spend"] == pytest.approx(data.spend.sum())
    assert k["roi"] == pytest.approx((data.revenue.sum() - data.spend.sum()) / data.spend.sum() * 100)
    assert k["ctr"] == pytest.approx(data.clicks.sum() / data.impressions.sum() * 100)


def test_rates_computed_after_aggregation(data):
    by = summarize(data, "channel")
    fb = data[data.channel == "Facebook"]
    row = by.set_index("channel").loc["Facebook"]
    assert row.cpa == pytest.approx(fb.spend.sum() / fb.conversions.sum())


def test_views_agree_on_filtered_totals(data):
    f = all_filters(data)
    f.channels = ["Twitter"]
    sub = apply_filters(data, f)
    total = kpis(sub)["spend"]
    assert summarize(sub, "channel").spend.sum() == pytest.approx(total)
    assert campaign_table(sub).spend.sum() == pytest.approx(total)
    assert timeseries(sub, "Weekly").spend.sum() == pytest.approx(total)


def test_empty_filter_returns_empty_and_safe_kpis(data):
    f = all_filters(data)
    f.goals = []
    sub = apply_filters(data, f)
    assert sub.empty
    assert insights(sub) == []


def test_zero_division_is_nan_not_inf():
    df = prepare(pd.DataFrame({
        "date": ["2026-01-01"], "campaign_name": ["x"], "channel": ["facebook"],
        "spend": [0], "clicks": [0], "conversions": [0],
    }))
    k = kpis(df)
    assert np.isnan(k["cpc"]) and np.isnan(k["roi"])


def test_alias_headers_and_currency_strings():
    raw = pd.DataFrame({
        "Day": ["2026-02-01"], "Campaign": ["Promo"], "Platform": ["instagram"],
        "Amount Spent": ["$1,200.50"], "Link Clicks": ["300"], "Results": [12],
    })
    df = prepare(raw)
    assert df.loc[0, "spend"] == pytest.approx(1200.50)
    assert df.loc[0, "channel"] == "Instagram"
    assert df.loc[0, "audience"] == "Unspecified"


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="spend"):
        prepare(pd.DataFrame({"date": [], "campaign_name": [], "channel": [], "clicks": [], "conversions": []}))


def test_search_is_case_insensitive(data):
    table = campaign_table(data)
    assert len(search_campaigns(table, "PINTEREST")) == (table.channel == "Pinterest").sum()
    assert len(search_campaigns(table, "")) == len(table)


def test_normalize_columns_snake_case():
    out = normalize_columns(pd.DataFrame(columns=["Campaign Goal", " Target Audience "]))
    assert list(out.columns) == ["goal", "audience"]
