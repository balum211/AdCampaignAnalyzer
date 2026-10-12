"""Generate a realistic, reproducible sample ad-campaign dataset.

The data is synthetic (seeded random numbers), shaped like an export from
Facebook / Instagram / Pinterest / Twitter ad managers: one row per campaign
per day. Run from the repo root:

    python scripts/generate_sample_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START = pd.Timestamp("2026-01-01")
END = pd.Timestamp("2026-06-30")
OUT = Path(__file__).resolve().parents[1] / "data" / "ad_campaigns.csv"

# Channel-level behaviour: click-through rate, cost per click, conversion rate,
# average order value. Rough, plausible industry ballparks.
CHANNELS = {
    "Facebook": dict(ctr=0.012, cpc=0.95, cvr=0.045, aov=46.0),
    "Instagram": dict(ctr=0.010, cpc=1.15, cvr=0.038, aov=50.0),
    "Pinterest": dict(ctr=0.007, cpc=0.70, cvr=0.030, aov=52.0),
    "Twitter": dict(ctr=0.009, cpc=0.80, cvr=0.020, aov=40.0),
}
AUDIENCES = ["Women 18-24", "Women 25-34", "Men 18-24", "Men 25-34", "Adults 35-54", "Adults 55+"]
# Goal changes how much of the funnel turns into revenue.
GOALS = {
    "Awareness": dict(ctr_mult=0.8, cvr_mult=0.5, cpc_mult=0.7),
    "Traffic": dict(ctr_mult=1.2, cvr_mult=0.8, cpc_mult=0.9),
    "Lead Generation": dict(ctr_mult=1.0, cvr_mult=1.2, cpc_mult=1.1),
    "Conversions": dict(ctr_mult=1.0, cvr_mult=1.5, cpc_mult=1.25),
}
THEMES = ["Spring Sale", "New Arrivals", "Loyalty Push", "Summer Preview", "Brand Story",
          "Retargeting", "Bundle Deals", "Clearance", "Influencer Collab", "App Install",
          "Email Signup", "Holiday Recap"]


def build() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    campaign_no = 0
    for channel, ch in CHANNELS.items():
        for _ in range(7):  # 7 campaigns per channel -> 28 campaigns
            campaign_no += 1
            goal = rng.choice(list(GOALS))
            audience = rng.choice(AUDIENCES)
            theme = THEMES[campaign_no % len(THEMES)]
            g = GOALS[goal]
            start = START + pd.Timedelta(days=int(rng.integers(0, 90)))
            end = min(END, start + pd.Timedelta(days=int(rng.integers(30, 120))))
            budget = float(rng.choice([80, 120, 150, 200, 300, 450]))
            quality = rng.lognormal(0, 0.35)  # some campaigns are simply better
            cid = f"CMP-{campaign_no:03d}"
            name = f"{theme} | {channel} | {audience}"
            for day in pd.date_range(start, end, freq="D"):
                weekday = 1.0 + (0.12 if day.dayofweek >= 5 else 0.0)
                spend = max(5.0, budget * rng.normal(1.0, 0.15))
                cpc = ch["cpc"] * g["cpc_mult"] * rng.normal(1.0, 0.08)
                clicks = max(0, int(round(spend / cpc)))
                ctr = ch["ctr"] * g["ctr_mult"] * quality * weekday * rng.normal(1.0, 0.1)
                impressions = int(round(clicks / max(ctr, 1e-4)))
                cvr = ch["cvr"] * g["cvr_mult"] * quality * rng.normal(1.0, 0.15)
                conversions = int(rng.binomial(clicks, float(np.clip(cvr, 0, 1))))
                revenue = round(conversions * ch["aov"] * rng.normal(1.0, 0.1), 2)
                rows.append(dict(
                    date=day.date().isoformat(), campaign_id=cid, campaign_name=name,
                    channel=channel, audience=audience, goal=goal,
                    impressions=impressions, clicks=clicks, spend=round(spend, 2),
                    conversions=conversions, revenue=max(revenue, 0.0),
                ))
    return pd.DataFrame(rows).sort_values(["date", "campaign_id"]).reset_index(drop=True)


if __name__ == "__main__":
    df = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df):,} rows, {df.campaign_id.nunique()} campaigns -> {OUT}")
