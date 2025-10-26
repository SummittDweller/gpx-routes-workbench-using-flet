#!/bin/bash
# Launcher script for GPX Routes Workbench

echo "Starting GPX Routes Workbench..."
echo "================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if requirements are installed
if ! python3 -c "import flet" &> /dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the application
python3 main.py
