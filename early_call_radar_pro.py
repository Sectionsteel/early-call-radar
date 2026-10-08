
"""
EARLY CALL RADAR PRO
Target: Solana Pump.fun / PumpSwap tokens in the $2K-$5K MC range.

ALERT-ONLY. No private key, no automatic buying.

Scoring:
  +20 MC is in target band
  +15 liquidity >= $1.5K
  +15 >= 8 buys in 30s
  +10 >= 6 unique buyers in 30s
  +10 buy/sell count ratio >= 2.0
  +10 buy volume/sell volume ratio >= 2.0
  +10 creator wallet is not yet flagged by your local blacklist
  +10 early-wallet score (if you populate SMART_WALLETS)
  -15 creator has launched too many recent tokens (if data is available)
  -20 suspicious bundled/clustered buyers (if your event feed exposes the fields)

DEFAULT ALERT: score >= 70.

Because feed schemas can evolve, this script safely accepts multiple field names.
Run it first in "observe" mode and tune thresholds after collecting data.
"""

import os, time, json, threading
from collections import defaultdict, deque
from pathlib import Path

import requests
import socketio

MIN_MC = float(os.getenv("MIN_MC", "2000"))
MAX_MC = float(os.getenv("MAX_MC", "5000"))
MIN_LIQ = float(os.getenv("MIN_LIQ", "1500"))
MIN_BUYS_30S = int(os.getenv("MIN_BUYS_30S", "8"))
MIN_UNIQUE_30S = int(os.getenv("MIN_UNIQUE_30S", "6"))
MAX_AGE_SEC = int(os.getenv("MAX_AGE_SEC", "180"))
ALERT_SCORE = int(os.getenv("ALERT_SCORE", "70"))
OBSERVE_ONLY = os.getenv("OBSERVE_ONLY", "1") == "1"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Put known profitable early-buy wallets here, one address per line.
SMART_WALLETS_FILE = Path(os.getenv("SMART_WALLETS_FILE", "smart_wallets.txt"))
BLACKLIST_FILE = Path(os.getenv("BLACKLIST_FILE", "blacklist.txt"))

WS_URL = "https://sol.shrine.trade"

sio = socketio.Client(reconnection=True)
tokens = {}
events = defaultdict(lambda: deque(maxlen=500))
alerted = set()

def load_lines(path):
    if not path.exists():
        return set()
    return {
        x.strip() for x in path.read_text().splitlines()
        if x.strip() and not x.strip().startswith("#")
    }

SMART_WALLETS = load_lines(SMART_WALLETS_FILE)
BLACKLIST = load_lines(BLACKLIST_FILE)

def num(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        try:
            if v is not None and str(v).strip() != "":
                return float(v)
        except Exception:
            pass
    return None

def wallet(d):
    return (
        d.get("wallet") or d.get("trader") or d.get("user") or
        d.get("buyer") or d.get("owner") or ""
    )

def action(d):
    return str(
        d.get("action") or d.get("side") or d.get("type") or ""
    ).lower()

def age(t):
    ts = num(t, "timestamp", "time", "createdAt", "created_at")
    return 999999 if ts is None else max(0, time.time() - ts)

def mc(t):
    return num(t, "marketCapUSD", "mcapUSD", "market_cap_usd", "marketCap")

def liq(t):
    return num(t, "liquidityUSD", "liquidity_usd", "liquidity")

def volume_usd(e):
    return num(e, "volumeUSD", "volume_usd", "usdValue", "amountUSD", "valueUSD")

def classify(e):
    a = action(e)
    if a in ("buy", "swap_buy", "trade_buy"):
        return "buy"
    if a in ("sell", "swap_sell", "trade_sell"):
        return "sell"
    return ""

def score(mint):
    t = tokens.get(mint, {})
    m = mc(t)
    l = liq(t)
    if m is None or not (MIN_MC <= m <= MAX_MC):
        return None

    a = age(t)
    if a > MAX_AGE_SEC:
        return None
    if l is not None and l < MIN_LIQ:
        return None

    now = time.time()
    ev = [x for x in events[mint] if now - x["time"] <= 30]
    buys = [x for x in ev if x["kind"] == "buy"]
    sells = [x for x in ev if x["kind"] == "sell"]
    unique = {x["wallet"] for x in buys if x["wallet"]}

    buy_vol = sum(x["usd"] or 0 for x in buys)
    sell_vol = sum(x["usd"] or 0 for x in sells)

    # We only award activity points if the feed actually supplied enough data.
    points = 20
    reasons = [f"MC ${m:,.0f}"]

    if l is not None and l >= MIN_LIQ:
        points += 15
        reasons.append(f"liq ${l:,.0f}")

    if len(buys) >= MIN_BUYS_30S:
        points += 15
        reasons.append(f"{len(buys)} buys/30s")

    if len(unique) >= MIN_UNIQUE_30S:
        points += 10
        reasons.append(f"{len(unique)} unique buyers")

    if sells > []:
        ratio = len(buys) / max(1, len(sells))
        if ratio >= 2:
            points += 10
            reasons.append(f"buy/sell {ratio:.1f}x")

    if buy_vol > 0 and sell_vol > 0:
        ratio = buy_vol / sell_vol
        if ratio >= 2:
            points += 10
            reasons.append(f"buy vol/sell vol {ratio:.1f}x")

    creator = t.get("creator") or ""
    if creator and creator in BLACKLIST:
        return -999, ["BLACKLISTED CREATOR"], t, ev

    if creator and creator not in BLACKLIST:
        points += 10
        reasons.append("creator not locally blacklisted")

    smart = {x["wallet"] for x in buys if x["wallet"] in SMART_WALLETS}
    if smart:
        points += 10
        reasons.append(f"{len(smart)} tracked early wallet(s)")

    # Optional suspicious-cluster signal if a feed/event supplies bundle/cluster labels.
    suspicious = sum(
        1 for x in ev
        if x.get("bundle") is True or x.get("bundled") is True
        or x.get("cluster_suspicious") is True
    )
    if suspicious:
        points -= 20
        reasons.append(f"{suspicious} suspicious bundled event(s)")

    return points, reasons, t, ev

def tg(msg):
    print("\n" + msg + "\n")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10,
        )
    except Exception as e:
        print("Telegram error:", e)

def alert(mint, sc, reasons, t):
    if mint in alerted:
        return
    alerted.add(mint)

    name = t.get("symbol") or t.get("name") or "UNKNOWN"
    creator = t.get("creator") or "?"
    short_creator = creator[:6] + "…" + creator[-4:] if len(creator) > 12 else creator
    m = mc(t)
    l = liq(t)

    msg = (
        "🚨 EARLY CALL RADAR — PRO\n\n"
        f"${name}\n"
        f"Score: {sc}/100\n"
        f"MC: ${m:,.0f}\n"
        f"Liquidity: ${l:,.0f}\n" if l is not None else
        f"${name}\nScore: {sc}/100\nMC: ${m:,.0f}\n"
    )
    msg += (
        f"Age: {age(t):.0f}s\n"
        f"Creator: {short_creator}\n"
        f"Signals: {', '.join(reasons)}\n\n"
        f"CA:\n{mint}\n\n"
        f"https://dexscreener.com/solana/{mint}"
    )

    if OBSERVE_ONLY:
        msg = "👀 OBSERVE MODE\n" + msg

    tg(msg)

@sio.event
def connect():
    print("Connected.")
    sio.emit("subscribe_new_tokens", {"protocols": ["PUMPFUN", "PUMPSWAP"]})
    print("Watching PUMPFUN + PUMPSWAP.")

@sio.on("new_token")
def on_new(n):
    if n.get("protocol") not in ("PUMPFUN", "PUMPSWAP"):
        return
    mint = n.get("mint")
    if not mint:
        return
    tokens[mint] = dict(n)

@sio.on("token_update")
def on_update(u):
    mint = u.get("mint")
    if not mint:
        return

    tokens.setdefault(mint, {}).update(u)

    k = classify(u)
    if k:
        events[mint].append({
            "time": time.time(),
            "kind": k,
            "wallet": wallet(u),
            "usd": volume_usd(u),
            "bundle": u.get("bundle"),
            "bundled": u.get("bundled"),
            "cluster_suspicious": u.get("cluster_suspicious"),
        })

    result = score(mint)
    if not result:
        return

    sc, reasons, t, ev = result
    if sc >= ALERT_SCORE:
        alert(mint, sc, reasons, t)

@sio.event
def disconnect():
    print("Disconnected; Socket.IO will retry.")

def cleanup():
    while True:
        now = time.time()
        for mint in list(events):
            q = events[mint]
            while q and now - q[0]["time"] > 30:
                q.popleft()
        time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=cleanup, daemon=True).start()
    tg(
        "🟢 EARLY CALL RADAR PRO ONLINE\n"
        f"MC: ${MIN_MC:,.0f}-${MAX_MC:,.0f}\n"
        f"Min liquidity: ${MIN_LIQ:,.0f}\n"
        f"Alert score: {ALERT_SCORE}/100\n"
        f"Observe only: {OBSERVE_ONLY}\n"
        "No auto-trading."
    )
    sio.connect(WS_URL, transports=["websocket", "polling"])
    sio.wait()
