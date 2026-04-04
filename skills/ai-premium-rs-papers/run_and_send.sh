#!/bin/bash
#
# AI Premium Remote Sensing Papers - Generate and Send to Feishu
#
# Usage: ./run_and_send.sh
#
# Required environment variables:
#   FEISHU_TARGET - Feishu user/chat ID to send message to
#
# Optional environment variables:
#   NATURE_API_KEY - API key for Nature (SpringerNature)
#   SCIENCE_API_KEY - API key for Science/AAAS
#   PNAS_API_KEY - API key for PNAS (if needed)
#   AI_PREMIUM_RS_PAPERS_PROXY - HTTP proxy URL
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for FEISHU_TARGET
if [ -z "$FEISHU_TARGET" ]; then
    echo "Error: FEISHU_TARGET environment variable is not set."
    echo "Please set it to your Feishu user/chat ID."
    exit 1
fi

echo "=================================="
echo "Premium RS Papers -> Feishu"
echo "=================================="
echo "Target: $FEISHU_TARGET"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check for openclaw
if ! command -v openclaw &> /dev/null; then
    echo "Error: openclaw CLI not found."
    exit 1
fi

# Use virtual environment Python
PYTHON="$SCRIPT_DIR/venv/bin/python3"

# Ensure virtual environment exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Error: Virtual environment not found. Please run: python3 -m venv venv && ./venv/bin/pip install requests"
    exit 1
fi

# Generate compact summary
MSG=$($PYTHON generator.py --compact --output-dir "$SCRIPT_DIR/recommendations")

# Check if we got any papers
if [ -z "$MSG" ] || [ "$MSG" == "📡 今日暂无相关论文" ]; then
    echo "No papers found today, skipping Feishu notification."
    exit 0
fi

echo "Sending to Feishu..."

# Send via openclaw
openclaw message send --channel feishu --target "$FEISHU_TARGET" --message "$MSG"

echo ""
echo "✅ Sent successfully!"
