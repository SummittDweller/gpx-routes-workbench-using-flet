#!/bin/bash
# Launcher script for GPX Routes Workbench
# This script automatically:
# 1. Creates a Python virtual environment if it doesn't exist
# 2. Activates the virtual environment
# 3. Installs all required dependencies
# 4. Launches the GPX Routes Workbench application

set -e  # Exit on error

echo "GPX Routes Workbench - Launcher"
echo "================================"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3.8 or higher from https://www.python.org/"
    exit 1
fi

# Display Python version
PYTHON_VERSION=$(python3 --version)
echo "✓ Found: $PYTHON_VERSION"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
    echo ""
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Check if requirements are installed (check for flet package)
if ! python3 -c "import flet" &> /dev/null; then
    echo "📥 Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✓ Dependencies installed"
    echo ""
else
    echo "✓ Dependencies already installed"
    echo ""
fi

# Run the application
echo "🚀 Launching GPX Routes Workbench..."
echo "================================"
echo ""
python3 main.py
