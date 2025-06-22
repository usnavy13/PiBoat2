#!/bin/bash
#
# PiBoat2 Startup Script
# Run this script on the boat device to start the autonomous control system
#

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Starting PiBoat2 Boat Control System..."
echo "Project Root: $PROJECT_ROOT"
echo "Boat Directory: $SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "ERROR: Virtual environment not found at $PROJECT_ROOT/venv"
    echo "Please run the following commands first:"
    echo "  cd $PROJECT_ROOT"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements/boat.txt"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$SCRIPT_DIR/.env" ] && [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "WARNING: No .env file found. Using default configuration."
    echo "Create $SCRIPT_DIR/.env or $PROJECT_ROOT/.env with MQTT credentials:"
    echo "  MQTT_USERNAME=piboat2_user"
    echo "  MQTT_PASSWORD=your_mqtt_password"
    echo "  BOAT_ID=piboat2_001"
fi

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

# Check if required packages are installed
python3 -c "import paho.mqtt.client; import yaml; import serial" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Required packages not installed. Please run:"
    echo "  source $PROJECT_ROOT/venv/bin/activate"
    echo "  pip install -r $PROJECT_ROOT/requirements/boat.txt"
    exit 1
fi

# Create log directory if it doesn't exist
sudo mkdir -p /var/log/piboat2
sudo chown pi:pi /var/log/piboat2 2>/dev/null || true

# Start the boat application
echo "Starting boat control system..."
echo "Press Ctrl+C to stop"
echo "----------------------------------------"

cd "$SCRIPT_DIR"
python3 main.py "$@"

echo "Boat control system stopped."