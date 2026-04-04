#!/bin/bash
#
# AI Premium Remote Sensing Papers - Manual Run Script
# 
# Usage: ./script.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check for required packages
echo "Checking dependencies..."
python3 -c "import requests" 2>/dev/null || {
    echo "Installing required packages..."
    pip3 install requests -q
}

echo "=================================="
echo "Fetching Premium RS Papers"
echo "=================================="

# Run generator
python3 generator.py "$@"

echo ""
echo "Done! Check recommendations/ directory for reports."
