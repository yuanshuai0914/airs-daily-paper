#!/bin/bash
# Send fitness reminder every other day, anchored at 2026-03-07
ANCHOR="2026-03-07"
TODAY=$(date +%Y-%m-%d)
DAYS=$(( ( $(date -j -f %Y-%m-%d "$TODAY" +%s) - $(date -j -f %Y-%m-%d "$ANCHOR" +%s) ) / 86400 ))
if (( DAYS % 2 == 0 )); then
  /opt/homebrew/bin/openclaw message send --channel feishu --target ou_5bad990ac044099e73e61dbc78f63853 --message "⏰ 早上提醒：今天安排健身（隔天一次）"
fi
