
# EARLY CALL RADAR PRO — $2K-$5K

This is the upgraded alert-only version.

## Why this version is better

Instead of alerting simply because a token reached $2K-$5K MC, it assigns a score using:

- Market-cap window
- Liquidity
- 30-second buy count
- Unique buyers
- Buy/sell count ratio
- Buy/sell USD-volume ratio
- Local creator blacklist
- Tracked early-wallet hits
- Optional bundled/suspicious event penalty

Default alert threshold: **70/100**.

## Important: start in OBSERVE MODE

The default is:

`OBSERVE_ONLY=1`

It sends alerts but labels them as OBSERVE MODE. Do not treat the score as a proven trading edge yet.

Collect alerts and outcomes first. Then we can backtest and tune the weights.

## Install

```bash
pip install -r requirements.txt
```

## Telegram

Create a bot with Telegram's BotFather, then set:

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```

## Run

```bash
python early_call_radar_pro.py
```

## Main settings

```bash
export MIN_MC=2000
export MAX_MC=5000
export MIN_LIQ=1500
export MIN_BUYS_30S=8
export MIN_UNIQUE_30S=6
export MAX_AGE_SEC=180
export ALERT_SCORE=70
export OBSERVE_ONLY=1
```

## Smart wallets

Create `smart_wallets.txt`.

Put one Solana wallet address on each line.

Example:

```text
# profitable early wallets
ADDRESS_1
ADDRESS_2
ADDRESS_3
```

The scanner gives +10 when a tracked wallet appears among the early buyers.

### Do NOT blindly copy wallet lists from Twitter.

We should build the list from historical performance.

## Creator blacklist

Create `blacklist.txt`.

One creator address per line.

The scanner will reject a token if its creator is locally blacklisted.

## Next stage: real backtest

Shrine provides hourly historical archives of the same stream used live. The archive is free and can be replayed event-by-event. This lets us measure:

- how many $2K-$5K tokens were detected
- how many reached $10K / $25K / $50K
- maximum drawdown after alert
- time to target
- creator repeat-launch behavior
- which early-wallet signals actually worked
- optimal score threshold

The historical archive is large, so stream/decompress it rather than loading an entire hour into memory.

## Safety

This program does not contain a wallet/private key and does not buy or sell tokens.
