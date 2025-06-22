# PiBoat2 MQTT Command & Control System Specification

## Overview
Remote command and control system for PiBoat2 using MQTT protocol over LTE connection. Enables real-time boat control, navigation commands, and status monitoring.

## System Architecture

### Core Components
1. **MQTTClient** - Connection management and message handling
2. **CommandDispatcher** - Routes and validates incoming commands
3. **NavigationController** - High-level navigation and waypoint management
4. **StatusReporter** - Periodic status updates and telemetry
5. **SafetyMonitor** - Safety checks and emergency procedures

### Dependencies
- `paho-mqtt` - MQTT client library
- Existing hardware controllers:
  - `MotorController` (hardware_code/motor_controller.py)
  - `GPSHandler` (hardware_code/gps_handler.py)
- LTE connectivity via wwan0 interface

## Message Protocol

### Base Message Structure
```json
{
  "command_id": "uuid4_string",
  "timestamp": "ISO8601_datetime", 
  "boat_id": "unique_boat_identifier",
  "command_type": "navigation|control|status|config|emergency",
  "payload": {},
  "priority": "critical|high|medium|low",
  "requires_ack": true|false,
  "timeout_seconds": 30
}
```

### Command Types

#### Navigation Commands
- **set_waypoint**
  ```json
  {
    "command_type": "navigation",
    "payload": {
      "action": "set_waypoint",
      "latitude": 40.7128,
      "longitude": -74.0060,
      "max_speed": 50,
      "arrival_radius": 10.0
    }
  }
  ```

- **set_course**
  ```json
  {
    "command_type": "navigation", 
    "payload": {
      "action": "set_course",
      "heading": 270.0,
      "speed": 30,
      "duration": 60
    }
  }
  ```

- **hold_position**
  ```json
  {
    "command_type": "navigation",
    "payload": {
      "action": "hold_position",
      "max_drift": 5.0
    }
  }
  ```

#### Direct Control Commands
- **set_rudder**
  ```json
  {
    "command_type": "control",
    "payload": {
      "action": "set_rudder",
      "angle": -20.0
    }
  }
  ```

- **set_throttle**
  ```json
  {
    "command_type": "control",
    "payload": {
      "action": "set_throttle", 
      "speed": 25,
      "ramp_time": 2.0
    }
  }
  ```

#### Status Commands
- **get_status**
  ```json
  {
    "command_type": "status",
    "payload": {
      "action": "get_status",
      "include": ["gps", "motors", "system"]
    }
  }
  ```

#### Emergency Commands
- **emergency_stop**
  ```json
  {
    "command_type": "emergency",
    "payload": {
      "action": "emergency_stop",
      "reason": "user_initiated"
    }
  }
  ```

## MQTT Topics

### Inbound (Server → Boat)
- `boat/{boat_id}/commands` - Command messages
- `boat/{boat_id}/config` - Configuration updates
- `boat/{boat_id}/emergency` - Emergency commands (high priority)

### Outbound (Boat → Server)  
- `boat/{boat_id}/status` - Status updates and telemetry
- `boat/{boat_id}/gps` - GPS position data
- `boat/{boat_id}/ack` - Command acknowledgments
- `boat/{boat_id}/logs` - System logs and errors
- `boat/{boat_id}/heartbeat` - Connection health

## File Structure

### New Files to Create
```
hardware_code/
├── mqtt_client.py          # MQTT connection and message handling
├── command_dispatcher.py   # Command routing and validation  
├── navigation_controller.py # High-level navigation logic
├── status_reporter.py      # Status reporting and telemetry
├── safety_monitor.py       # Safety checks and limits
└── mqtt_config.py          # Configuration management

test_mqtt_system.py         # MQTT system test script
boat_control_main.py        # Main application entry point
```

### Configuration
- MQTT broker settings in environment variables or config file
- Boat ID, authentication credentials
- Safety limits (max speed, boundary coordinates)
- Status reporting intervals

## Implementation Details

### MQTTClient Class
```python
class MQTTClient:
    def __init__(self, broker_host, port, boat_id, credentials)
    def connect() -> bool
    def disconnect()
    def subscribe_to_commands()
    def publish_status(topic, message)
    def set_message_callback(callback_func)
    def handle_connection_lost()
```

### CommandDispatcher Class
```python
class CommandDispatcher:
    def __init__(self, motor_controller, gps_handler, nav_controller)
    def dispatch_command(message) -> dict
    def validate_command(command) -> bool
    def execute_navigation_command(payload) -> dict
    def execute_control_command(payload) -> dict
    def execute_status_command(payload) -> dict
```

### NavigationController Class
```python
class NavigationController:
    def __init__(self, motor_controller, gps_handler)
    def navigate_to_waypoint(lat, lon, max_speed, arrival_radius)
    def set_course(heading, speed, duration)
    def hold_position(max_drift)
    def calculate_bearing(current_pos, target_pos) -> float
    def calculate_distance(pos1, pos2) -> float
```

### StatusReporter Class
```python
class StatusReporter:
    def __init__(self, mqtt_client, gps_handler, motor_controller)
    def start_periodic_reporting(interval=10)
    def stop_periodic_reporting()
    def get_system_status() -> dict
    def publish_status()
    def publish_gps_data()
```

## Safety Features

### Built-in Safety Limits
- Maximum speed limits (configurable)
- Rudder angle limits (±45°)
- Geographic boundaries (geofencing)
- Command timeout handling
- Emergency stop functionality

### Error Handling
- MQTT connection resilience with exponential backoff
- Command validation and sanitization
- Hardware failure detection and reporting
- Graceful degradation when GPS/motors unavailable

### Logging
- All commands logged with timestamps
- System status changes logged
- Error conditions logged with stack traces
- Configurable log levels (DEBUG, INFO, WARN, ERROR)

## Testing Strategy

### Unit Tests
- Individual component testing
- Mock hardware interfaces for development
- Command validation testing
- Message parsing and generation

### Integration Tests
- End-to-end command flow testing
- MQTT connectivity testing
- Hardware integration testing
- Safety limit testing

### Test Script Features
- Simulate various command scenarios
- Test connection resilience
- Validate safety mechanisms
- Performance and latency testing

## Configuration Example

### Environment Variables
```bash
MQTT_BROKER_HOST=mqtt.example.com
MQTT_BROKER_PORT=8883
MQTT_USE_TLS=true
BOAT_ID=piboat2_001
MQTT_USERNAME=boat_client
MQTT_PASSWORD=secure_password
MAX_SPEED_PERCENT=70
STATUS_REPORT_INTERVAL=10
GPS_UPDATE_INTERVAL=5
```

### Runtime Configuration
```python
CONFIG = {
    'mqtt': {
        'broker_host': os.getenv('MQTT_BROKER_HOST'),
        'port': int(os.getenv('MQTT_BROKER_PORT', 1883)),
        'use_tls': os.getenv('MQTT_USE_TLS', 'false').lower() == 'true',
        'keepalive': 60,
        'qos': 1
    },
    'boat': {
        'id': os.getenv('BOAT_ID', 'piboat2_default'),
        'max_speed': int(os.getenv('MAX_SPEED_PERCENT', 70)),
        'status_interval': int(os.getenv('STATUS_REPORT_INTERVAL', 10)),
        'gps_interval': int(os.getenv('GPS_UPDATE_INTERVAL', 5))
    },
    'safety': {
        'max_rudder_angle': 45.0,
        'command_timeout': 30,
        'emergency_stop_timeout': 5,
        'geofence_enabled': False
    }
}
```

## Implementation Priority

### Phase 1 (Core Functionality)
1. MQTTClient with basic pub/sub
2. CommandDispatcher with basic command routing
3. Integration with existing MotorController
4. Basic status reporting

### Phase 2 (Navigation)
1. NavigationController with waypoint navigation
2. GPS integration for position-based commands
3. Course and heading control
4. Position holding functionality

### Phase 3 (Advanced Features)
1. Safety monitoring and geofencing
2. Advanced error handling and recovery
3. Comprehensive logging and diagnostics
4. Performance optimization

### Phase 4 (Testing & Deployment)
1. Comprehensive test suite
2. Integration testing with real hardware
3. Performance and reliability testing
4. Documentation and deployment guides

## Expected Files After Implementation

### Primary Implementation Files
- `hardware_code/mqtt_client.py` (~300 lines)
- `hardware_code/command_dispatcher.py` (~200 lines)
- `hardware_code/navigation_controller.py` (~250 lines)
- `hardware_code/status_reporter.py` (~150 lines)
- `hardware_code/safety_monitor.py` (~100 lines)
- `hardware_code/mqtt_config.py` (~50 lines)
- `boat_control_main.py` (~100 lines)
- `test_mqtt_system.py` (~200 lines)

### Configuration Updates
- Update `requirements.txt` to include `paho-mqtt`
- Update `CLAUDE.md` with MQTT system documentation

## Notes
- Leverage existing LTE connectivity through wwan0 interface
- Maintain compatibility with current hardware controller interfaces
- Ensure graceful shutdown procedures for safety
- Design for reliability in marine environment with intermittent connectivity