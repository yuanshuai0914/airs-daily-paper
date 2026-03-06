#!/bin/bash
# Send plants reminder every 4 days, anchored at 2026-03-09
ANCHOR="2026-03-09"
TODAY=$(date +%Y-%m-%d)
DAYS=$(( ( $(date -j -f %Y-%m-%d "$TODAY" +%s) - $(date -j -f %Y-%m-%d "$ANCHOR" +%s) ) / 86400 ))
if (( DAYS >= 0 )) && (( DAYS % 4 == 0 )); then
  /opt/homebrew/bin/openclaw message send --channel feishu --target ou_5bad990ac044099e73e61dbc78f63853 --message "⏰ 提醒：今天记得浇绿植（每4天）"
fi
