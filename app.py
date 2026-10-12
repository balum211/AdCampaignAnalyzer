"""Ad Campaign Performance Analyzer — Streamlit app.

Run:  streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import ai
from src.analytics import (
    METRICS, Filters, apply_filters, campaign_table, fmt, insights, kpis, load_csv,
    metric_label, period_change, search_campaigns, summarize, timeseries, unique_sorted,
)

SAMPLE = Path(__file__).parent / "data" / "ad_campaigns.csv"
CHANNEL_COLORS = {"Facebook": "#1877F2", "Instagram": "#C13584", "Pinterest": "#E60023", "Twitter": "#1DA1F2"}

st.set_page_config(page_title="Ad Campaign Analyzer", page_icon="📣", layout="wide")


@st.cache_data(show_spinner=False)
def load(source) -> pd.DataFrame:
    return load_csv(source)


# ---------------------------------------------------------------- data source
st.sidebar.title("📣 Ad Campaign Analyzer")
uploaded = st.sidebar.file_uploader("Upload a campaign CSV (optional)", type=["csv"])
try:
    data = load(uploaded if uploaded is not None else SAMPLE)
except ValueError as err:
    st.error(f"Could not read that CSV. {err}. See the README for the expected columns.")
    st.stop()
st.sidebar.caption("Using **uploaded file**." if uploaded else "Using the bundled **sample dataset** (synthetic).")

# ---------------------------------------------------------------- global filters
st.sidebar.header("Filters")
st.sidebar.caption("Every tab uses these same filters.")
min_d, max_d = data["date"].min().date(), data["date"].max().date()
picked = st.sidebar.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d,
                               key="f_date")
start, end = (picked if isinstance(picked, (list, tuple)) and len(picked) == 2 else (min_d, max_d))


def multi(label: str, col: str) -> list[str]:
    options = unique_sorted(data[col])
    return st.sidebar.multiselect(label, options, default=options, key=f"f_{col}")


channels = multi("Channel", "channel")
audiences = multi("Audience", "audience")
goals = multi("Campaign goal", "goal")
if st.sidebar.button("Reset filters"):
    for key in [k for k in st.session_state.keys() if str(k).startswith("f_")]:
        del st.session_state[key]
    st.rerun()

flt = Filters(pd.Timestamp(start), pd.Timestamp(end), channels, audiences, goals)
df = apply_filters(data, flt)

st.title("Ad Campaign Performance Analyzer")
st.caption(
    f"{start:%b %d, %Y} – {end:%b %d, %Y} · {len(channels)} channel(s) · "
    f"{df['campaign_id'].nunique() if not df.empty else 0} campaign(s) · {len(df):,} daily rows"
)

if df.empty:
    st.warning(
        "**No data matches the current filters.** Widen the date range or re-select at least one "
        "channel, audience and goal in the sidebar (or click *Reset filters*)."
    )
    st.stop()

tab_overview, tab_platform, tab_campaigns, tab_time = st.tabs(
    ["📊 Overview", "⚖️ Platform Comparison", "🔎 Campaign Details", "📈 Time Series"]
)

# ---------------------------------------------------------------- overview
with tab_overview:
    k = kpis(df)
    row1 = st.columns(4)
    row1[0].metric("Total spend ($)", fmt(k["spend"], "$"))
    row1[1].metric("Revenue ($)", fmt(k["revenue"], "$"))
    row1[2].metric("Conversions (#)", fmt(k["conversions"], "#"))
    row1[3].metric("ROI (%)", fmt(k["roi"], "%"), help="(Revenue − Spend) ÷ Spend")
    row2 = st.columns(4)
    row2[0].metric("CTR (%)", fmt(k["ctr"], "%"), help="Clicks ÷ Impressions")
    row2[1].metric("CPC ($)", fmt(k["cpc"], "$"), help="Spend ÷ Clicks")
    row2[2].metric("Cost per conversion ($)", fmt(k["cpa"], "$"), help="Spend ÷ Conversions")
    row2[3].metric("ROAS (x)", fmt(k["roas"], "x"), help="Revenue ÷ Spend")

    st.subheader("Spend vs conversions")
    gran = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], index=1, horizontal=True, key="ov_gran")
    ts = timeseries(df, gran)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=ts["date"], y=ts["spend"], name="Spend ($)", marker_color="#94a3b8")
    fig.add_trace(go.Scatter(x=ts["date"], y=ts["conversions"], name="Conversions (#)",
                             mode="lines+markers", line=dict(color="#16a34a", width=3)), secondary_y=True)
    fig.update_yaxes(title_text="Spend ($)", tickprefix="$", secondary_y=False)
    fig.update_yaxes(title_text="Conversions (#)", secondary_y=True)
    fig.update_layout(height=380, legend=dict(orientation="h", y=1.1), margin=dict(t=30, b=10))
    st.plotly_chart(fig)

    c1, c2 = st.columns(2)
    by_ch = summarize(df, "channel")
    c1.plotly_chart(px.pie(by_ch, names="channel", values="spend", hole=0.5, title="Share of spend ($)",
                           color="channel", color_discrete_map=CHANNEL_COLORS))
    c2.plotly_chart(px.pie(by_ch, names="channel", values="conversions", hole=0.5,
                           title="Share of conversions (#)", color="channel",
                           color_discrete_map=CHANNEL_COLORS))

    st.subheader("Key insights")
    for line in insights(df):
        st.markdown(f"- {line}")

    if ai.available(st.secrets):
        if st.button("✨ Generate AI summary"):
            context = summarize(df, ["channel", "goal"]).round(2).to_csv(index=False)
            with st.spinner("Asking Claude…"):
                try:
                    st.markdown(ai.summarize(context, "Summarize campaign performance and where to shift budget.",
                                             st.secrets))
                except Exception as exc:  # network / auth issues shouldn't crash the app
                    st.error(f"AI summary failed: {exc}")
    else:
        st.caption("Tip: set ANTHROPIC_API_KEY and `pip install anthropic` to enable an AI-written summary.")

# ---------------------------------------------------------------- platform comparison
with tab_platform:
    st.subheader("How do the channels compare?")
    metric_keys = list(METRICS)
    metric = st.selectbox("Metric", metric_keys, index=metric_keys.index("roi"),
                          format_func=metric_label, key="pc_metric")
    by_ch = summarize(df, "channel").sort_values(metric, ascending=False)
    unit = METRICS[metric][1]
    fig = px.bar(by_ch, x="channel", y=metric, color="channel", color_discrete_map=CHANNEL_COLORS,
                 text=by_ch[metric].map(lambda v: fmt(v, unit)), labels={metric: metric_label(metric)})
    fig.update_layout(showlegend=False, height=380, xaxis_title=None)
    st.plotly_chart(fig)

    c1, c2 = st.columns(2)
    bubble = px.scatter(by_ch, x="spend", y="conversions", size="revenue", color="channel",
                        color_discrete_map=CHANNEL_COLORS, size_max=60, hover_name="channel",
                        labels={"spend": "Spend ($)", "conversions": "Conversions (#)", "revenue": "Revenue ($)"},
                        title="Spend vs conversions (bubble = revenue)")
    c1.plotly_chart(bubble)
    split = c2.selectbox("Break down by", ["goal", "audience"], format_func=str.title, key="pc_split")
    grid = summarize(df, ["channel", split]).pivot(index=split, columns="channel", values="roi")
    heat = px.imshow(grid, text_auto=".0f", color_continuous_scale="RdYlGn", aspect="auto",
                     labels=dict(color="ROI (%)"), title=f"ROI (%) by channel × {split}")
    c2.plotly_chart(heat)

    st.markdown("**Channel scorecard**")
    show = ["channel", "spend", "revenue", "impressions", "clicks", "conversions", "ctr", "cpc", "cvr", "cpa", "roas", "roi"]
    st.dataframe(
        by_ch[show], hide_index=True,
        column_config={
            "channel": "Channel",
            "spend": st.column_config.NumberColumn("Spend ($)", format="$%.0f"),
            "revenue": st.column_config.NumberColumn("Revenue ($)", format="$%.0f"),
            "impressions": st.column_config.NumberColumn("Impressions (#)", format="%d"),
            "clicks": st.column_config.NumberColumn("Clicks (#)", format="%d"),
            "conversions": st.column_config.NumberColumn("Conversions (#)", format="%d"),
            "ctr": st.column_config.NumberColumn("CTR (%)", format="%.2f%%"),
            "cpc": st.column_config.NumberColumn("CPC ($)", format="$%.2f"),
            "cvr": st.column_config.NumberColumn("Conv. rate (%)", format="%.2f%%"),
            "cpa": st.column_config.NumberColumn("Cost/conv. ($)", format="$%.2f"),
            "roas": st.column_config.NumberColumn("ROAS (x)", format="%.2fx"),
            "roi": st.column_config.NumberColumn("ROI (%)", format="%.1f%%"),
        },
    )

# ---------------------------------------------------------------- campaign details
with tab_campaigns:
    st.subheader("Campaign-level results")
    c1, c2, c3 = st.columns([3, 2, 1])
    query = c1.text_input("Search campaigns", placeholder="name, ID, channel, audience or goal…")
    sort_key = c2.selectbox("Sort by", ["spend", "revenue", "conversions", "roi", "roas", "cpa", "ctr"],
                            format_func=metric_label, key="cd_sort")
    ascending = c3.toggle("Ascending", value=False)
    table = search_campaigns(campaign_table(df), query).sort_values(sort_key, ascending=ascending)

    if table.empty:
        st.info(f"No campaigns match “{query}”. Try a different search term.")
    else:
        st.caption(f"{len(table)} campaign(s)")
        st.dataframe(
            table, hide_index=True, height=420,
            column_config={
                "campaign_id": "ID", "campaign_name": "Campaign", "channel": "Channel",
                "audience": "Audience", "goal": "Goal",
                "start": st.column_config.DateColumn("Start"), "end": st.column_config.DateColumn("End"),
                "days": st.column_config.NumberColumn("Active days (#)"),
                "spend": st.column_config.NumberColumn("Spend ($)", format="$%.0f"),
                "revenue": st.column_config.NumberColumn("Revenue ($)", format="$%.0f"),
                "impressions": st.column_config.NumberColumn("Impr. (#)", format="%d"),
                "clicks": st.column_config.NumberColumn("Clicks (#)", format="%d"),
                "conversions": st.column_config.NumberColumn("Conv. (#)", format="%d"),
                "ctr": st.column_config.NumberColumn("CTR (%)", format="%.2f%%"),
                "cpc": st.column_config.NumberColumn("CPC ($)", format="$%.2f"),
                "cvr": st.column_config.NumberColumn("Conv. rate (%)", format="%.2f%%"),
                "cpa": st.column_config.NumberColumn("Cost/conv. ($)", format="$%.2f"),
                "roas": st.column_config.NumberColumn("ROAS (x)", format="%.2fx"),
                "roi": st.column_config.ProgressColumn(
                    "ROI (%)", format="%.0f%%",
                    min_value=float(min(table["roi"].min(), 0)), max_value=float(max(table["roi"].max(), 1))),
            },
        )
        st.download_button("⬇️ Download this table (CSV)", table.to_csv(index=False).encode(),
                           file_name="campaigns_filtered.csv", mime="text/csv")

        st.markdown("**Drill into one campaign**")
        pick = st.selectbox("Campaign", table["campaign_name"].tolist(), key="cd_pick")
        one = timeseries(df[df["campaign_name"] == pick], "Daily")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_bar(x=one["date"], y=one["spend"], name="Spend ($)", marker_color="#94a3b8")
        fig.add_trace(go.Scatter(x=one["date"], y=one["revenue"], name="Revenue ($)",
                                 line=dict(color="#2563eb")), secondary_y=False)
        fig.add_trace(go.Scatter(x=one["date"], y=one["conversions"], name="Conversions (#)",
                                 line=dict(color="#16a34a", dash="dot")), secondary_y=True)
        fig.update_yaxes(title_text="$", tickprefix="$", secondary_y=False)
        fig.update_yaxes(title_text="Conversions (#)", secondary_y=True)
        fig.update_layout(height=340, legend=dict(orientation="h", y=1.12), margin=dict(t=30, b=10))
        st.plotly_chart(fig)

# ---------------------------------------------------------------- time series
with tab_time:
    st.subheader("Performance over time")
    c1, c2, c3, c4 = st.columns(4)
    ts_metric = c1.selectbox("Metric", list(METRICS), index=list(METRICS).index("conversions"),
                             format_func=metric_label, key="ts_metric")
    ts_gran = c2.selectbox("Granularity", ["Daily", "Weekly", "Monthly"], index=1, key="ts_gran")
    ts_split = c3.selectbox("Split by", ["None", "channel", "goal", "audience"], key="ts_split",
                            format_func=lambda s: s.title())
    smooth = c4.checkbox("7-period rolling average", value=False)

    split_col = None if ts_split == "None" else ts_split
    ts = timeseries(df, ts_gran, split_col)
    y = ts_metric
    if smooth:
        if split_col:
            ts[y] = ts.groupby(split_col)[y].transform(lambda s: s.rolling(7, min_periods=1).mean())
        else:
            ts[y] = ts[y].rolling(7, min_periods=1).mean()
    fig = px.line(ts, x="date", y=y, color=split_col, markers=ts_gran != "Daily",
                  color_discrete_map=CHANNEL_COLORS if split_col == "channel" else None,
                  labels={y: metric_label(y), "date": ""})
    fig.update_layout(height=420, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig)

    st.markdown(f"**Month-over-month: {metric_label(ts_metric)}**")
    mom = period_change(df, ts_metric)
    unit = METRICS[ts_metric][1]
    mom_display = pd.DataFrame({
        "Month": mom["month"],
        metric_label(ts_metric): mom[ts_metric].map(lambda v: fmt(v, unit)),
        "Change vs prior month": mom["change_pct"].map(lambda v: "–" if pd.isna(v) else f"{v:+.1f}%"),
    })
    st.dataframe(mom_display, hide_index=True)

st.sidebar.divider()
st.sidebar.caption("Built with Streamlit · pandas · Plotly. Week 1 project, The Gen Academy.")
