# BTC/VIX spot beta

Hourly-updating tracker of BTC's sensitivity to VIX: **β = Cov(BTC % return, ΔVIX pts) / Var(ΔVIX)**, i.e. BTC % move per +1 VIX point.

- `etl/update.py`: stdlib-only updater. Pulls ^VIX 60m and 1d bars from Yahoo Finance and BTC-USD candles from Coinbase, fetching only missing points. Writes `data/hourly.csv`, `data/daily.csv` and `data/beta.json`.
- `.github/workflows/update.yml` runs it every hour at :50 and commits the new data.
- `index.html` is the GitHub Pages dashboard. It reads `data/beta.json` and shows rolling hourly β (65/260 obs), daily β (20/60 days), a "Since 2023" daily view (60/252-day β and calendar-year betas), a scatter and the latest observations.

Hourly observations are intraday pairs from Cboe early trading hours (~03:15 ET) through the 16:15 close. Overnight gaps are excluded. Hourly windows are 65 and 260 obs (~5 and ~20 sessions).
