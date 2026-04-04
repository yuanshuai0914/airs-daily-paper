#!/bin/bash
# AI RS Daily Papers - Fetch, Download PDFs, and Send to Feishu
# Usage: FEISHU_TARGET="chat_id" ./run_and_send.sh [--days N]
# Optional: AI_RS_DAILY_PAPERS_PROXY="http://proxy:port"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TODAY=$(date +%Y-%m-%d)
DAYS=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --days)
            DAYS="$2"
            shift 2
            ;;
        --days=*)
            DAYS="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: FEISHU_TARGET='chat_id' ./run_and_send.sh [--days N]" >&2
            exit 1
            ;;
    esac
done

if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [[ "$DAYS" -le 0 ]]; then
    echo "Error: --days must be a positive integer" >&2
    exit 1
fi

# Check required env var
if [[ -z "$FEISHU_TARGET" ]]; then
    echo "Error: FEISHU_TARGET environment variable is required" >&2
    echo "Usage: FEISHU_TARGET='chat_id' ./run_and_send.sh" >&2
    exit 1
fi

echo "=========================================="
echo "AI RS Daily Papers - $(date)"
echo "=========================================="

# Fetch papers and download PDFs
echo ""
echo "Step 1: Fetching papers and downloading PDFs (days=${DAYS})..."
MSG=$(cd "$SCRIPT_DIR" && python3 "$SCRIPT_DIR/fetch_and_download.py" --pdf-dir "$SCRIPT_DIR/pdfs" --max-papers 10 --days "$DAYS")

# Save message to file for logging
MSG_FILE="$SCRIPT_DIR/logs/message_${TODAY}.txt"
mkdir -p "$SCRIPT_DIR/logs"
echo "$MSG" > "$MSG_FILE"
echo "Message saved to: $MSG_FILE"

# Send to Feishu
echo ""
echo "Step 2: Sending notification to Feishu..."
openclaw message send --channel feishu --target "$FEISHU_TARGET" --message "$MSG"

echo ""
echo "=========================================="
echo "✅ Done!"
echo "PDFs saved to: $SCRIPT_DIR/pdfs/${TODAY}/"
echo "Please manually upload PDFs to:"
echo "https://my.feishu.cn/drive/folder/KcGmfS1y6lRd4gd1ofLclbzSnXc"
echo "=========================================="
