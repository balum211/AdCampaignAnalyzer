"""Pure pandas logic for the Ad Campaign Performance Analyzer.

Everything here is UI-free so it can be unit tested (see tests/).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["date", "campaign_name", "channel", "spend", "clicks", "conversions"]
OPTIONAL_COLUMNS = ["campaign_id", "audience", "goal", "impressions", "revenue"]
SUM_COLUMNS = ["spend", "impressions", "clicks", "conversions", "revenue"]

# Common header spellings from ad-platform exports -> our canonical names.
COLUMN_ALIASES = {
    "day": "date", "reporting_starts": "date", "date_start": "date",
    "campaign": "campaign_name", "campaign_title": "campaign_name", "ad_campaign": "campaign_name",
    "platform": "channel", "network": "channel", "source": "channel", "ad_platform": "channel",
    "target_audience": "audience", "segment": "audience", "demographic": "audience",
    "objective": "goal", "campaign_goal": "goal", "campaign_objective": "goal",
    "amount_spent": "spend", "cost": "spend", "amount_spent_usd": "spend", "acquisition_cost": "spend",
    "link_clicks": "clicks", "click": "clicks",
    "impression": "impressions", "views": "impressions",
    "results": "conversions", "purchases": "conversions", "conversion": "conversions",
    "conversion_value": "revenue", "purchase_value": "revenue", "sales": "revenue",
}

# Metric catalogue: label, unit, and whether higher is better. Used by the UI
# so every chart/table shows its unit.
METRICS = {
    "spend": ("Spend", "$", False),
    "revenue": ("Revenue", "$", True),
    "impressions": ("Impressions", "#", True),
    "clicks": ("Clicks", "#", True),
    "conversions": ("Conversions", "#", True),
    "ctr": ("CTR", "%", True),
    "cpc": ("CPC", "$", False),
    "cvr": ("Conversion rate", "%", True),
    "cpa": ("Cost per conversion", "$", False),
    "roas": ("ROAS", "x", True),
    "roi": ("ROI", "%", True),
}


def _snake(name: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in str(name).strip())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Snake-case headers and map common aliases onto canonical names."""
    renamed = {}
    for col in df.columns:
        key = _snake(col)
        renamed[col] = COLUMN_ALIASES.get(key, key)
    out = df.rename(columns=renamed)
    return out.loc[:, ~out.columns.duplicated()]


def missing_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, type-cast and fill optional columns. Raises ValueError if unusable."""
    df = normalize_columns(df)
    missing = missing_columns(df)
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    for col in SUM_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan if col in ("impressions", "revenue") else 0
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r"[$,\s]", "", regex=True), errors="coerce"
        )
    for col in ("spend", "clicks", "conversions"):
        df[col] = df[col].fillna(0)
    if "campaign_id" not in df.columns:
        df["campaign_id"] = df["campaign_name"]
    for col in ("audience", "goal"):
        if col not in df.columns:
            df[col] = "Unspecified"
        df[col] = df[col].fillna("Unspecified").astype(str)
    df["channel"] = df["channel"].astype(str).str.strip().str.title()
    df["campaign_name"] = df["campaign_name"].astype(str)
    return df.sort_values("date").reset_index(drop=True)


def load_csv(path_or_buffer) -> pd.DataFrame:
    return prepare(pd.read_csv(path_or_buffer))


@dataclass
class Filters:
    start: pd.Timestamp
    end: pd.Timestamp
    channels: list[str]
    audiences: list[str]
    goals: list[str]


def apply_filters(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    """The single filter function every view uses, so they always agree."""
    mask = (
        (df["date"] >= pd.Timestamp(f.start))
        & (df["date"] <= pd.Timestamp(f.end))
        & df["channel"].isin(f.channels)
        & df["audience"].isin(f.audiences)
        & df["goal"].isin(f.goals)
    )
    return df.loc[mask]


def _div(a, b):
    """Safe division that returns NaN instead of inf / ZeroDivisionError."""
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(b == 0, np.nan, a / np.where(b == 0, 1, b))
    return out if out.ndim else float(out)


def add_rates(agg: pd.DataFrame) -> pd.DataFrame:
    """Add ratio metrics to an aggregated frame (rates are computed AFTER summing)."""
    agg = agg.copy()
    agg["ctr"] = _div(agg["clicks"], agg["impressions"]) * 100
    agg["cpc"] = _div(agg["spend"], agg["clicks"])
    agg["cvr"] = _div(agg["conversions"], agg["clicks"]) * 100
    agg["cpa"] = _div(agg["spend"], agg["conversions"])
    agg["roas"] = _div(agg["revenue"], agg["spend"])
    agg["roi"] = _div(agg["revenue"] - agg["spend"], agg["spend"]) * 100
    return agg


def kpis(df: pd.DataFrame) -> dict[str, float]:
    totals = df[SUM_COLUMNS].sum(min_count=1).to_frame().T
    totals = totals.fillna({"spend": 0, "clicks": 0, "conversions": 0})
    return {k: (float(v) if pd.notna(v) else float("nan")) for k, v in add_rates(totals).iloc[0].items()}


def summarize(df: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    keys = [by] if isinstance(by, str) else list(by)
    agg = df.groupby(keys, dropna=False)[SUM_COLUMNS].sum(min_count=1).reset_index()
    return add_rates(agg)


def campaign_table(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["campaign_id", "campaign_name", "channel", "audience", "goal"]
    agg = df.groupby(keys, dropna=False).agg(
        start=("date", "min"), end=("date", "max"), days=("date", "nunique"),
        **{c: (c, "sum") for c in SUM_COLUMNS},
    ).reset_index()
    return add_rates(agg).sort_values("spend", ascending=False).reset_index(drop=True)


def search_campaigns(table: pd.DataFrame, query: str) -> pd.DataFrame:
    q = (query or "").strip().lower()
    if not q:
        return table
    text = table[["campaign_id", "campaign_name", "channel", "audience", "goal"]].astype(str)
    hit = text.apply(lambda col: col.str.lower().str.contains(q, regex=False)).any(axis=1)
    return table.loc[hit]


FREQ = {"Daily": "D", "Weekly": "W-MON", "Monthly": "MS"}


def timeseries(df: pd.DataFrame, freq: str = "Weekly", split: str | None = None) -> pd.DataFrame:
    rule = FREQ.get(freq, freq)
    keys = [pd.Grouper(key="date", freq=rule, label="left", closed="left")]
    if split:
        keys.append(split)
    agg = df.groupby(keys)[SUM_COLUMNS].sum(min_count=1).reset_index()
    return add_rates(agg)


def period_change(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Month-over-month table for one metric."""
    m = timeseries(df, "Monthly")[["date", metric]].copy()
    m["change_pct"] = m[metric].pct_change() * 100
    m["month"] = m["date"].dt.strftime("%b %Y")
    return m[["month", metric, "change_pct"]]


def insights(df: pd.DataFrame) -> list[str]:
    """Plain-language findings for the Overview tab (no LLM needed)."""
    if df.empty:
        return []
    out: list[str] = []
    k = kpis(df)
    if pd.notna(k["roi"]):
        verdict = "profitable" if k["roi"] > 0 else "losing money"
        out.append(f"Overall the selection is **{verdict}**: ROI {k['roi']:.1f}% on ${k['spend']:,.0f} spend.")
    ch = summarize(df, "channel").dropna(subset=["roi"])
    if len(ch) > 1:
        best, worst = ch.loc[ch["roi"].idxmax()], ch.loc[ch["roi"].idxmin()]
        out.append(f"**{best.channel}** has the best ROI ({best.roi:.1f}%); "
                   f"**{worst.channel}** the weakest ({worst.roi:.1f}%).")
        cheapest = ch.loc[ch["cpa"].idxmin()]
        out.append(f"Cheapest conversions come from **{cheapest.channel}** at ${cheapest.cpa:,.2f} each.")
    camp = campaign_table(df).dropna(subset=["roi"])
    losers = camp[camp["roi"] < 0]
    if len(losers):
        waste = losers["spend"].sum()
        out.append(f"{len(losers)} campaign(s) have negative ROI, together spending ${waste:,.0f}. "
                   f"Worst: *{losers.loc[losers['roi'].idxmin(), 'campaign_name']}*.")
    if len(camp):
        top = camp.loc[camp["roi"].idxmax()]
        out.append(f"Top campaign by ROI: *{top.campaign_name}* ({top.roi:.1f}%, {int(top.conversions):,} conversions).")
    return out


def fmt(value: float, unit: str) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "–"
    if unit == "$":
        return f"${value:,.2f}" if abs(value) < 100 else f"${value:,.0f}"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "x":
        return f"{value:.2f}x"
    return f"{value:,.0f}"


def metric_label(key: str) -> str:
    label, unit, _ = METRICS[key]
    return f"{label} ({unit})"


def unique_sorted(values: Iterable) -> list[str]:
    return sorted({str(v) for v in values})
