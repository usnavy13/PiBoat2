# PiBoat2 Project

## Project Overview
Semi-autonomous boat built as cheaply as possible, using software to overcome limitations of low-cost hardware components.

## Hardware Components
- GPS module (low-cost)
- Compass/magnetometer
- Motor controllers
- LTE connectivity module
- Raspberry Pi as main controller

## Development Environment
- Python 3.12+ required
- Uses virtual environment (venv)
- Dependencies managed via requirements.txt

## Setup Instructions
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Linux/Mac
# venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Key Components
- `hardware_code/` - Core hardware interface modules
  - `gps_handler.py` - GPS functionality
  - `compass_handler.py` - Compass/magnetometer control
  - `motor_controller.py` - Motor control systems
  - `agps_helper.py` - Assisted GPS functionality
- Calibration scripts for compass and other sensors
- Test scripts for individual hardware components
- LTE connectivity testing

## Testing
Currently no formal test framework setup. Individual test files exist:
- `test_*.py` files for hardware components
- Run individual tests with: `python test_filename.py`

## Development Workflow
- Hardware testing and calibration
- Individual component debugging
- Integration testing
- Performance optimization to work around low-cost hardware limitations

## Commands
```bash
# Test individual hardware components
python test_motor_controller.py
python test_lte_connectivity.py

# Calibrate compass
python calibrate_compass.py
python set_compass_calibration.py

# Install dependencies
pip install -r requirements.txt
```

## Notes
- Focus on software solutions to overcome cheap hardware limitations
- Semi-autonomous operation is the goal
- Cost optimization is a primary constraint