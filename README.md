# BTC/VIX spot beta

Hourly-updating tracker of BTC's sensitivity to VIX: **β = Cov(BTC % return, ΔVIX pts) / Var(ΔVIX)**, i.e. BTC % move per +1 VIX point.

- `etl/update.py`: stdlib-only updater. Pulls ^VIX 60m and 1d bars from Yahoo Finance and BTC-USD candles from Coinbase, fetching only missing points. Writes `data/hourly.csv`, `data/daily.csv` and `data/beta.json`.
- `.github/workflows/update.yml` runs it every hour at :50 and commits the new data.
- `index.html` is the GitHub Pages dashboard. It reads `data/beta.json` and shows rolling hourly β (30/120 obs), daily β (20/60 days), a scatter and the latest observations.

Hourly observations use only intraday pairs in the US cash session. Overnight gaps are excluded.
