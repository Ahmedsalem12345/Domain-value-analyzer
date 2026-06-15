#!/bin/bash
echo "=============================================="
echo "  ◆ Domain Value Analyzer V4 Market Intelligence"
echo "  Starting local server..."
echo "=============================================="

cd "$(dirname "$0")"

# Use the project-local venv Python directly.  The venv's activate scripts in
# this copy still point to the original folder path, so sourcing them would
# launch the wrong interpreter.  Calling the venv's python3 directly bypasses
# that and guarantees we use this folder's packages.
PYTHON="./venv/bin/python3"
PIP="./venv/bin/pip3"

if [ ! -x "$PYTHON" ]; then
    echo ""
    echo "  ✗ Virtual environment not found."
    echo "  Run: python3 -m venv venv && pip install -r requirements.txt"
    echo ""
    read -r -p "Press Enter to exit..."
    exit 1
fi

# Verify required packages are installed using the venv interpreter
if ! "$PYTHON" -c "import flask, pandas, sklearn" 2>/dev/null; then
    echo ""
    echo "  ✗ Missing dependencies. Installing now..."
    "$PIP" install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "  ✗ Dependency install failed. Check requirements.txt."
        read -r -p "Press Enter to exit..."
        exit 1
    fi
fi

echo ""
echo "  ✓ Environment ready. Launching analyzer..."
echo "  Open http://localhost:5050 in your browser"
echo ""

exec "$PYTHON" app.py
