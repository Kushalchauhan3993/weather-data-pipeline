#!/bin/bash
# scripts/setup.sh — One-click project setup script
# Run with: bash scripts/setup.sh

echo "╔══════════════════════════════════════════╗"
echo "║   🌤  WEATHER PIPELINE SETUP SCRIPT      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check Python version
echo "✔ Checking Python version..."
python3 --version || { echo "❌ Python 3 not found. Install from python.org"; exit 1; }

# Create virtual environment
echo ""
echo "✔ Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo ""
echo "✔ Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "✔ Creating .env from template..."
    cp .env.example .env
    echo "  ⚠️  Edit .env with your OpenWeatherMap API key"
    echo "  ⚠️  Get a free key at: https://openweathermap.org/api"
fi

# Create required directories
echo ""
echo "✔ Creating directories..."
mkdir -p database logs reports

# Run database setup
echo ""
echo "✔ Initializing database..."
python main.py setup

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ SETUP COMPLETE!                      ║"
echo "║                                          ║"
echo "║  Next steps:                             ║"
echo "║  1. Edit .env with your API key          ║"
echo "║  2. Run: python main.py full             ║"
echo "╚══════════════════════════════════════════╝"
