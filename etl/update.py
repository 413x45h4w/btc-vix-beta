"""Hourly BTC/VIX spot-beta updater (stdlib only).

Beta = Cov(BTC % log return, VIX point change) / Var(VIX point change)
     = BTC % move per +1 VIX point.

Hourly obs: consecutive completed ^VIX 60m bars within one ET day (incl. Cboe global trading
hours ~03:15-09:15 ET; no overnight pairs).
BTC is sampled (Coinbase 15m candle close) at each VIX bar's end time.
Daily obs: VIX daily close vs BTC at the last full hour before the VIX close.
"""
import csv, json, math, os, time, urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (compatible; btc-vix-beta/1.0)"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
H_CSV, D_CSV, OUT = (os.path.join(D, f) for f in ("hourly.csv", "daily.csv", "beta.json"))
WIN_H, WIN_H_LONG, WIN_D, WIN_D_LONG = 65, 260, 20, 60  # ~5 / ~20 sessions of 13 hourly bars


def get(url, tries=5):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception as e:  # 429 / transient
            err = e
            time.sleep(3 * (i + 1))
    raise err


def yahoo(symbol, interval, rng):
    for host in ("query1", "query2"):
        try:
            j = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={rng}")
            return j["chart"]["result"][0]
        except Exception as e:
            last = e
    raise last


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {r["t"]: r for r in csv.DictReader(f)}


def save(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "vix", "btc"])
        w.writeheader()
        for k in sorted(rows, key=int):
            w.writerow(rows[k])


def coinbase(gran, ts_needed):
    """Return {candle_close_time: close} covering the needed sample times."""
    out, need = {}, sorted(set(ts_needed))
    if not need:
        return out
    span = 299 * gran
    start = need[0] - gran
    while start < need[-1]:
        end = min(start + span, need[-1])
        if any(start < t <= end + gran for t in need):
            s = datetime.fromtimestamp(start, timezone.utc).isoformat()
            e = datetime.fromtimestamp(end, timezone.utc).isoformat()
            for c in get(f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity={gran}&start={s}&end={e}"):
                out[c[0] + gran] = c[4]  # [time, low, high, open, close, vol]; key = candle end
            time.sleep(0.25)
        start = end
    return out


def session_end_tod(meta):
    p = meta.get("currentTradingPeriod", {}).get("regular", {})
    if "end" in p:
        e = datetime.fromtimestamp(p["end"], ET)
        return e.hour * 3600 + e.minute * 60
    return 16 * 3600 + 15 * 60


def update_hourly(now):
    rows = load(H_CSV)
    r = yahoo("%5EVIX", "60m", "5d" if len(rows) > 50 else "60d")
    end_tod = session_end_tod(r["meta"])
    for ts, c in zip(r.get("timestamp", []), r["indicators"]["quote"][0]["close"]):
        if c is None:
            continue
        st = datetime.fromtimestamp(ts, ET)
        day0 = st.replace(hour=0, minute=0, second=0, microsecond=0)
        mark = min(ts + 3600, int((day0 + timedelta(seconds=end_tod)).timestamp()))
        mark -= mark % 900
        if mark > now - 900:  # bar not complete (allow data delay)
            continue
        k = str(mark)
        rows.setdefault(k, {"t": k, "vix": "", "btc": ""})["vix"] = f"{c:.2f}"
    missing = [int(k) for k, v in rows.items() if not v["btc"]]
    px = coinbase(900, missing)
    for t in missing:
        if t in px:
            rows[str(t)]["btc"] = f"{px[t]:.2f}"
    save(H_CSV, rows)
    return rows


def update_daily(now):
    rows = load(D_CSV)
    r = yahoo("%5EVIX", "1d", "1mo" if len(rows) > 100 else "1y")
    end_tod = session_end_tod(r["meta"])
    today = datetime.fromtimestamp(now, ET).date()
    for ts, c in zip(r.get("timestamp", []), r["indicators"]["quote"][0]["close"]):
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, ET)
        close_t = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=end_tod)
        if d.date() == today and now < close_t.timestamp() + 900:
            continue  # today's close not final yet
        mark = int(close_t.timestamp()); mark -= mark % 3600
        k = str(mark)
        rows.setdefault(k, {"t": k, "vix": "", "btc": ""})["vix"] = f"{c:.2f}"
    missing = [int(k) for k, v in rows.items() if not v["btc"]]
    px = coinbase(3600, missing)
    for t in missing:
        if t in px:
            rows[str(t)]["btc"] = f"{px[t]:.2f}"
    save(D_CSV, rows)
    return rows


def obs(rows, same_session):
    pts = [(int(k), float(v["vix"]), float(v["btc"])) for k, v in rows.items() if v["vix"] and v["btc"]]
    pts.sort()
    o = []
    for (t0, v0, b0), (t1, v1, b1) in zip(pts, pts[1:]):
        if same_session and datetime.fromtimestamp(t0, ET).date() != datetime.fromtimestamp(t1, ET).date():
            continue
        o.append((t1, v1 - v0, 100 * math.log(b1 / b0), v1, b1))
    return o


def stats(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0 or syy == 0:
        return None, None
    return sxy / sxx, sxy / math.sqrt(sxx * syy)


def rolling(o, w):
    b, c = [], []
    for i in range(len(o)):
        if i + 1 < w:
            b.append(None); c.append(None); continue
        seg = o[i + 1 - w:i + 1]
        bb, cc = stats([s[1] for s in seg], [s[2] for s in seg])
        b.append(None if bb is None else round(bb, 4)); c.append(None if cc is None else round(cc, 3))
    return b, c


def block(o, w, wl):
    b, c = rolling(o, w)
    bl, cl = rolling(o, wl)
    return {"t": [s[0] for s in o], "beta": b, "corr": c, "beta_long": bl, "corr_long": cl,
            "dv": [round(s[1], 2) for s in o], "r": [round(s[2], 3) for s in o],
            "vix": [s[3] for s in o], "btc": [s[4] for s in o], "win": w, "win_long": wl}


def main():
    os.makedirs(D, exist_ok=True)
    now = int(time.time())
    errs = []
    try:
        h = update_hourly(now)
    except Exception as e:
        errs.append(f"hourly: {e}"); h = load(H_CSV)
    try:
        d = update_daily(now)
    except Exception as e:
        errs.append(f"daily: {e}"); d = load(D_CSV)
    out = {"updated": now, "errors": errs,
           "hourly": block(obs(h, True), WIN_H, WIN_H_LONG),
           "daily": block(obs(d, False), WIN_D, WIN_D_LONG)}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"hourly obs={len(out['hourly']['t'])} daily obs={len(out['daily']['t'])} errors={errs}")
    if errs and not out["hourly"]["t"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
