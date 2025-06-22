# PiBoat2 - Semi-Autonomous Boat Project

A cost-effective semi-autonomous boat system built with Raspberry Pi, featuring remote control via MQTT over LTE connectivity.

## Quick Start

### Boat Setup (Raspberry Pi)
```bash
git clone <repository>
cd PiBoat2
python -m venv venv
source venv/bin/activate
pip install -r requirements/boat.txt
cd boat
python main.py
```

### Ground Control Server
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements/server.txt
cd server
python main.py
```

## Features

- **Remote Control**: MQTT-based command and control over LTE
- **Autonomous Navigation**: GPS waypoint navigation with safety monitoring
- **Web Interface**: Ground control station with real-time status
- **Hardware Integration**: GPS, compass, motor controllers
- **Cost Optimized**: Software solutions for low-cost hardware limitations

## Architecture

- **Boat**: Raspberry Pi running autonomous control software
- **Server**: Ground control station with web interface
- **Communication**: MQTT over LTE for real-time operations

## Documentation

See [CLAUDE.md](CLAUDE.md) for detailed project documentation and [docs/MQTT_SYSTEM_SPEC.md](docs/MQTT_SYSTEM_SPEC.md) for communication protocol details.

## License

This project is for educational and research purposes.