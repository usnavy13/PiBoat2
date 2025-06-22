# PiBoat2 Project

## Project Overview
Semi-autonomous boat built as cheaply as possible, using software to overcome limitations of low-cost hardware components. The project consists of boat-side control software and a ground control server.

## Architecture
- **Boat**: Raspberry Pi-based autonomous control system with MQTT communication
- **Server**: Ground control station with web interface and database
- **Communication**: MQTT over LTE for real-time control and telemetry

## Hardware Components
- GPS module (low-cost)
- Compass/magnetometer
- Motor controllers
- LTE connectivity module
- Raspberry Pi as main controller

## Development Environment
- Python 3.12+ required
- Uses virtual environment (venv)
- Separate dependencies for boat and server components

## Setup Instructions

### Boat Setup (Raspberry Pi)
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install boat dependencies
pip install -r requirements/boat.txt
```

### Server Setup (Development/Ground Control)
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install server dependencies
pip install -r requirements/server.txt
```

## Project Structure
```
PiBoat2/
├── boat/                    # Boat-side code (Raspberry Pi)
│   ├── hardware/           # Hardware interface modules
│   ├── communication/      # MQTT communication
│   ├── navigation/         # Navigation and control
│   ├── config/            # Configuration management
│   └── main.py            # Main boat application
├── server/                 # Server-side code (Ground control)
│   ├── api/               # REST API endpoints
│   ├── mqtt/              # Server MQTT handling
│   ├── database/          # Data storage
│   ├── web/               # Web interface
│   └── main.py            # Main server application
├── tests/                 # Test files
├── scripts/               # Utility and calibration scripts
├── config/                # Configuration files
├── docs/                  # Documentation
└── requirements/          # Dependency files
```

## Key Components

### Boat Hardware Modules
- `boat/hardware/gps_handler.py` - GPS functionality
- `boat/hardware/compass_handler.py` - Compass/magnetometer control
- `boat/hardware/motor_controller.py` - Motor control systems
- `boat/hardware/agps_helper.py` - Assisted GPS functionality

### Communication System
- `boat/communication/mqtt_client.py` - MQTT client for boat
- `boat/communication/command_dispatcher.py` - Command processing
- `boat/communication/status_reporter.py` - Status reporting

### Navigation System
- `boat/navigation/navigation_controller.py` - Waypoint navigation
- `boat/navigation/safety_monitor.py` - Safety checks and limits

## Testing
```bash
# Test individual hardware components
python scripts/test_motor_controller.py
python scripts/test_lte_connectivity.py

# Hardware calibration
python scripts/calibrate_compass.py
python scripts/set_compass_calibration.py

# Run boat hardware tests
python -m pytest tests/boat/test_hardware/

# Run server tests
python -m pytest tests/server/
```

## Running the System

### Start Boat Control System
```bash
cd boat
python main.py
```

### Start Ground Control Server
```bash
cd server
python main.py
```

## Configuration
- `config/boat_config.yaml` - Boat-side configuration
- `config/server_config.yaml` - Server-side configuration
- `config/compass_calibration.json` - Compass calibration data

## Documentation
- `docs/MQTT_SYSTEM_SPEC.md` - MQTT communication protocol specification
- `docs/API_DOCUMENTATION.md` - REST API documentation

## Development Workflow
- Hardware testing and calibration
- Individual component debugging
- Integration testing
- Performance optimization to work around low-cost hardware limitations

## Notes
- Focus on software solutions to overcome cheap hardware limitations
- Semi-autonomous operation is the goal
- Cost optimization is a primary constraint
- MQTT communication enables remote control and monitoring