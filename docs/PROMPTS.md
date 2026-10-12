# Vibe-coding log: Ad Campaign Performance Analyzer

These are the prompts used to build the app with an AI coding assistant, in order, along with the bugs and iterations each one led to. Reuse or adapt them for the Week 1 documentation, and add screenshots of your own runs.

## Prompts

**Prompt 1: dataset**
> Create a realistic sample CSV of daily ad-campaign performance for Jan–Jun 2026 across Facebook, Instagram, Pinterest and Twitter. Columns: date, campaign_id, campaign_name, channel, audience, goal (Awareness, Traffic, Lead Generation, Conversions), impressions, clicks, spend, conversions, revenue. Make it reproducible with a seed, and make some campaigns lose money so the analysis is interesting.

**Prompt 2: data layer**
> Write a pure-pandas module (no Streamlit) that loads the CSV, normalizes common ad-platform header names, strips $ and commas, and exposes: one filter function (date range, channel, audience, goal), KPI totals, group-by summaries, a campaign table, and time series at daily/weekly/monthly granularity. Compute CTR, CPC, conversion rate, CPA, ROAS and ROI *after* aggregating, and never divide by zero.

**Prompt 3: dashboard skeleton**
> Build a Streamlit app with a sidebar of global filters (date, channel, audience, campaign goal) and four tabs: Overview, Platform Comparison, Campaign Details, Time Series. Every tab must use the same filtered dataframe. If filters return no rows, show a clear message and stop.

**Prompt 4: views**
> Overview: 8 KPI cards with units in the label, a spend-vs-conversions chart on two axes, spend and conversion share donuts. Platform Comparison: metric picker bar chart, spend-vs-conversions bubble chart, ROI heatmap by channel × goal/audience, and a scorecard table. Campaign Details: searchable, sortable table with CSV download and a single-campaign drill-down. Time Series: metric, granularity, split-by and rolling-average controls plus a month-over-month table. Use Plotly and consistent brand colors per channel.

**Prompt 5: insights and AI**
> Add a "Key insights" list generated from the data (best/worst channel by ROI, cheapest conversions, campaigns with negative ROI and their wasted spend, top campaign). Add an optional "Generate AI summary" button that sends the channel × goal summary to Claude, only shown if an API key is configured.

**Prompt 6: hardening**
> Write pytest tests proving the KPIs match raw sums, all views agree on filtered totals, empty filters are safe, zero-division gives NaN, and alias headers and currency strings parse. Add a GitHub Actions workflow that runs the tests and boots the app headless with streamlit.testing.

## Iterations, pitfalls and fixes

Some of these are bugs caught during the build. Others are common pitfalls the prompts guarded against up front. Add your own bugs and screenshots here as you iterate.

| # | Issue | Fix |
|---|---|---|
| 1 | Averaging daily CTR/ROI gave different totals than the KPI cards | Rates are now computed from summed numerators and denominators (`add_rates`) everywhere |
| 2 | Days with 0 clicks produced `inf` CPC and broke chart axes | `_div()` returns NaN for zero denominators; the UI shows "–" |
| 3 | Clearing a multiselect produced empty Plotly charts and a crash on `idxmax` | Single empty-state check after filtering, then `st.stop()`; insights return `[]` for empty data |
| 4 | "Reset filters" didn't reset the widgets | Gave filter widgets `f_*` keys and cleared only those from `session_state` |
| 5 | First sample dataset had ROI ≈ 195% everywhere, which made the story boring | Lowered order values and widened campaign-quality spread, so Twitter now goes negative and 7 campaigns lose money |
| 6 | `use_container_width` is deprecated in newer Streamlit | Dropped it; Plotly charts and tables stretch by default |
| 7 | Uploaded CSVs used headers like "Amount Spent" and "$1,200" | Added header alias map plus currency stripping |

## Learnings
- Keeping the analytics in a UI-free module made it easy to test and kept the Streamlit file readable.
- Specifying *units* and *empty states* in the prompt up front saved a round of fixes.
- Asking the assistant for tests that check different views against each other caught the averaged-rates bug.
