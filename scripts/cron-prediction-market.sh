#!/bin/bash
# cron-prediction-market.sh — Prediction Market Arbitrage Scanner
# Schedule: 0 9,15,21 * * * (3x daily)
# Phase 4 — Trading + Arbitrage workflow

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-prediction-market.log"
OUT_DIR="${OPENCLAW_ROOT}/autoresearch/outputs/datasets"
SERPER_KEY=$(grep SERPER_API_KEY "${OPENCLAW_ROOT}/.env" | cut -d= -f2)

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a
mkdir -p "$OUT_DIR"

echo "[$(date)] cron-prediction-market start" >> "$LOG_FILE"

# Fetch live Polymarket markets (top volume)
POLY_MARKETS=$(curl -s "https://clob.polymarket.com/markets?active=true&closed=false&limit=20" 2>/dev/null \
  | python3 -c "
import sys, json
try:
  d = json.load(sys.stdin)
  markets = d if isinstance(d, list) else d.get('data', d.get('markets', []))
  for m in markets[:20]:
    print(json.dumps({'question': m.get('question',''), 'yes_price': m.get('tokens',[{}])[0].get('price',0) if m.get('tokens') else 0, 'volume': m.get('volume',0)}))
except: print('[]')
" 2>/dev/null || echo "[]")

PROMPT="You are SCOUT, the Research Agent for Omega MegaCorp's prediction market arbitrage operation.

Today: ${TODAY}
Mission: Identify high-confidence arbitrage opportunities in prediction markets.

Domain config:
$(cat ${OPENCLAW_ROOT}/autoresearch/domains/prediction-market/config.md)

Polymarket live markets (sample):
${POLY_MARKETS}

Using your knowledge of current events and base rates:
1. Identify markets where probability appears mispriced vs reality
2. Calculate implied edge (estimated_true_probability - current_odds)
3. Score confidence: high (>0.8), medium (0.6-0.8), low (<0.6)
4. This is PAPER TRADING ONLY — no real capital until 10 predictions verified

Output ONLY valid JSON matching this schema:
{
  \"scan_date\": \"${TODAY}\",
  \"opportunities\": [
    {
      \"market\": \"description\",
      \"platform\": \"polymarket\",
      \"current_odds\": 0.0,
      \"estimated_true_probability\": 0.0,
      \"edge\": 0.0,
      \"confidence\": \"high|medium|low\",
      \"evidence\": \"one sentence\",
      \"recommended_action\": \"buy_yes|buy_no|pass\",
      \"max_position_usd\": 0,
      \"resolution_date\": \"YYYY-MM-DD\"
    }
  ],
  \"meta\": {\"total_scanned\": 20, \"high_confidence\": 0, \"mode\": \"paper_trading\"}
}"

RESULT=$(echo "$PROMPT" | timeout 180 ollama run gemma4:26b 2>/dev/null | python3 -c "
import sys, json, re
txt = sys.stdin.read()
m = re.search(r'\{.*\}', txt, re.DOTALL)
if m:
    try:
        d = json.loads(m.group())
        print(json.dumps(d, indent=2))
    except: print(txt[:500])
else: print(txt[:500])
" 2>/dev/null)

OUT_FILE="${OUT_DIR}/prediction-market-${TODAY}-${TIMESTAMP//:/}.json"
echo "$RESULT" > "$OUT_FILE"

HIGH_CONF=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('meta',{}).get('high_confidence',0))" 2>/dev/null || echo "0")

if [[ "$HIGH_CONF" -gt 0 ]]; then
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
"Prediction Market Scan — ${TODAY} ${TIMESTAMP}

High-confidence opportunities: ${HIGH_CONF}
Mode: PAPER TRADING ONLY

Review: ${OUT_FILE}" 2>/dev/null || true
fi

echo "[$(date)] cron-prediction-market complete — ${HIGH_CONF} high-confidence signals" >> "$LOG_FILE"
