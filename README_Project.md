# Home Assistant Driver for VOLTTRON

A platform driver interface that enables two-way communication between [VOLTTRON](https://github.com/VOLTTRON/volttron) agents and [Home Assistant](https://www.home-assistant.io/) smart home devices via the Home Assistant REST API.

## Supported Devices

| Device Type | Read | Write | Controllable Points |
|-------------|------|-------|---------------------|
| **Light** (`light.*`) | ✅ | ✅ | state (on/off), brightness (0–255) |
| **Switch** (`switch.*`) | ✅ | ✅ | state (on/off) |
| **Fan** (`fan.*`) | ✅ | ✅ | state (on/off), percentage (0–100) |
| **Thermostat** (`climate.*`) | ✅ | ✅ | state (off/heat/cool/auto), temperature |
| **Input Boolean** (`input_boolean.*`) | ✅ | ✅ | state (on/off) |
| **Other Entities** | ✅ | ❌ | state and attributes (read-only) |

> **New in Sprint 2:** Switch and fan device support, including fan speed percentage control.

## Architecture

```
VOLTTRON Agent
      │
      ▼  set_point / get_point RPC
PlatformDriver
      │
      ▼  _set_point() / _scrape_all()
Home Assistant Interface  (home_assistant.py)
      │
      ▼  HTTP GET / POST
Home Assistant REST API
      /api/states/<entity_id>
      /api/services/<domain>/<service>
```

The driver translates VOLTTRON point read/write operations into Home Assistant REST API calls. Each device point is defined in a registry configuration file (`registry_config.csv`), which maps VOLTTRON point names to Home Assistant entity IDs and attributes.

## Prerequisites

- A running VOLTTRON instance (v9.x, Python 3.10)
- A running Home Assistant instance with the REST API enabled
- A Home Assistant **Long-Lived Access Token** (generated in HA under Profile → Security)
- Network connectivity between VOLTTRON and Home Assistant

## Installation

### 1. Copy Driver Files

Copy `home_assistant.py` into your VOLTTRON platform driver interfaces directory:

```bash
cp home_assistant.py <VOLTTRON_ROOT>/services/core/PlatformDriverAgent/platform_driver/interfaces/
```

### 2. Create Driver Configuration

Create a driver config JSON file (e.g., `homeassistant_driver.config`):

```json
{
    "driver_config": {
        "ip_address": "192.168.1.100",
        "access_token": "YOUR_HOME_ASSISTANT_LONG_LIVED_TOKEN",
        "port": "8123"
    },
    "driver_type": "home_assistant",
    "registry_config": "config://homeassistant_registry.csv",
    "interval": 30
}
```

| Parameter | Description |
|-----------|-------------|
| `ip_address` | IP address of your Home Assistant instance |
| `access_token` | Long-Lived Access Token from Home Assistant |
| `port` | Port number (default: 8123) |
| `interval` | Scrape interval in seconds |

### 3. Create Registry Configuration

Create a registry CSV file (`registry_config.csv`) that maps VOLTTRON point names to Home Assistant entities:

```csv
Volttron Point Name,Entity ID,Entity Point,Writable,Type,Units,Notes
BedroomLight_State,light.bedroom,state,True,int,None,On/Off control
BedroomLight_Brightness,light.bedroom,brightness,True,int,None,0-255
LivingRoomSwitch_State,switch.living_room_plug,state,True,int,None,On/Off control
BedroomFan_State,fan.bedroom_fan,state,True,int,None,On/Off control
BedroomFan_Speed,fan.bedroom_fan,percentage,True,int,None,0-100 speed
Thermostat_Mode,climate.main_thermostat,state,True,int,None,0=off 2=heat 3=cool 4=auto
Thermostat_Temp,climate.main_thermostat,temperature,True,float,F,Target temperature
Thermostat_CurrentTemp,climate.main_thermostat,current_temperature,False,float,F,Read-only
GuestMode,input_boolean.guest_mode,state,True,int,None,On/Off toggle
```

### 4. Install Configuration into VOLTTRON

```bash
# Store the registry config
vctl config store platform.driver homeassistant_registry.csv registry_config.csv --csv

# Store the driver config
vctl config store platform.driver devices/homeassistant homeassistant_driver.config
```

## Usage

Once the driver is installed and the PlatformDriver agent is running, VOLTTRON agents can interact with Home Assistant devices using standard RPC calls.

### Reading Device State

```python
# Read all device points at once
result = self.vip.rpc.call(
    'platform.driver',
    'scrape_all',
    'homeassistant'
).get(timeout=10)
# Returns: {'BedroomLight_State': 1, 'BedroomFan_Speed': 75, ...}

# Read a single point
value = self.vip.rpc.call(
    'platform.driver',
    'get_point',
    'homeassistant',
    'BedroomLight_State'
).get(timeout=10)
# Returns: 1
```

### Controlling Devices

```python
# Turn on a light
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'BedroomLight_State', 1)

# Set light brightness to 50%
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'BedroomLight_Brightness', 128)

# Turn on a switch
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'LivingRoomSwitch_State', 1)

# Turn on a fan
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'BedroomFan_State', 1)

# Set fan speed to 75%
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'BedroomFan_Speed', 75)

# Set thermostat to cool mode
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'Thermostat_Mode', 3)

# Set target temperature to 72°F
self.vip.rpc.call('platform.driver', 'set_point',
                   'homeassistant', 'Thermostat_Temp', 72)
```

### Value Reference

| Device | Point | Accepted Values |
|--------|-------|-----------------|
| Light | state | `0` = off, `1` = on |
| Light | brightness | `0` – `255` |
| Switch | state | `0` = off, `1` = on |
| Fan | state | `0` = off, `1` = on |
| Fan | percentage | `0` – `100` |
| Thermostat | state | `0` = off, `2` = heat, `3` = cool, `4` = auto |
| Thermostat | temperature | numeric (°F or °C depending on config) |
| Input Boolean | state | `0` = off, `1` = on |

## Demo Guide

This section provides step-by-step CLI commands for demonstrating the driver.

> **Note:** If you are not running an actual Home Assistant instance, state this explicitly at the start of your demo and use mock responses or logs to show expected behavior.

### Part 1: Verify Existing Functionality

Demonstrate that the original device support (lights, thermostats, input booleans) still works after Sprint 2 changes.

```bash
# Start VOLTTRON
cd <VOLTTRON_ROOT>
source env/bin/activate
volttron -vv -l volttron.log &

# Start the Platform Driver
vctl start --tag platform.driver

# Read all device states
vctl rpc call platform.driver scrape_all homeassistant

# Test light control (existing functionality)
vctl rpc call platform.driver set_point homeassistant BedroomLight_State 1
vctl rpc call platform.driver get_point homeassistant BedroomLight_State

# Test thermostat control (existing functionality)
vctl rpc call platform.driver set_point homeassistant Thermostat_Mode 2
vctl rpc call platform.driver get_point homeassistant Thermostat_Mode
```

### Part 2: Demonstrate New Functionality

Show the new switch and fan device support added in Sprint 2.

```bash
# Turn on a switch
vctl rpc call platform.driver set_point homeassistant LivingRoomSwitch_State 1
vctl rpc call platform.driver get_point homeassistant LivingRoomSwitch_State

# Turn off a switch
vctl rpc call platform.driver set_point homeassistant LivingRoomSwitch_State 0

# Turn on a fan
vctl rpc call platform.driver set_point homeassistant BedroomFan_State 1
vctl rpc call platform.driver get_point homeassistant BedroomFan_State

# Set fan speed to 75%
vctl rpc call platform.driver set_point homeassistant BedroomFan_Speed 75
vctl rpc call platform.driver get_point homeassistant BedroomFan_Speed

# Scrape all — shows switch and fan alongside existing devices
vctl rpc call platform.driver scrape_all homeassistant
```

### Part 3: Show Tests Passing

```bash
# Sprint 2 unit tests (17 tests)
cd sprint2-ha-driver-extension
python test_home_assistant.py

# Sprint 3 integration tests (40 tests)
cd ../sprint3-integration-testing
pip install requests-mock
python test_integration_home_assistant.py
```

### Part 4: Show Updated Documentation

```bash
# Generate and serve documentation locally
cd <VOLTTRON_ROOT>/docs
make html
cd build/html
python -m http.server 8080
# Open browser to http://localhost:8080
```

## Testing

### Unit Tests (Sprint 2)

17 tests that mock at the driver method level to verify routing logic:

```bash
cd sprint2-ha-driver-extension
python test_home_assistant.py
```

### Integration Tests (Sprint 3)

40 tests that mock at the HTTP transport layer to verify the full request/response chain:

```bash
cd sprint3-integration-testing
pip install requests-mock
python test_integration_home_assistant.py
```

| Test Class | Count | What It Verifies |
|------------|-------|------------------|
| TestWritePathIntegration | 14 | HTTP POST URLs, payloads for all 5 device types |
| TestReadPathIntegration | 9 | HTTP GET + JSON response parsing |
| TestRoundTrip | 3 | Write then read-back consistency |
| TestMultiDeviceScrape | 1 | 8 points across 5 entities in one call |
| TestAPIErrorHandling | 5 | HTTP 500, 401, 404, connection errors |
| TestConfigureIntegration | 3 | Driver config and registry parsing |
| TestAuthHeaders | 3 | Bearer token on every request |
| TestGetPoint | 3 | Single-entity reads via HTTP |

**Total: 57 tests (17 unit + 40 integration), 0 failures**

## Project Structure

```
volttron/
├── sprint2-ha-driver-extension/
│   ├── home_assistant.py              # Driver with switch + fan support
│   ├── test_home_assistant.py         # Unit tests (17 tests)
│   ├── HA_Driver_Change_Summary_v2.docx
│   └── README.md
├── sprint3-integration-testing/
│   ├── test_integration_home_assistant.py  # Integration tests (40 tests)
│   ├── Sprint3_Integration_Testing_Report.docx
│   └── README.md
└── ...
```

## Sprint History

| Sprint | Dates | Deliverables |
|--------|-------|--------------|
| **Sprint 1** | Feb 10 – Feb 23 | Design document, architecture overview, code review |
| **Sprint 2** | Feb 24 – Mar 9 | Switch + fan support, bug fix in `_scrape_all()`, 5 helper methods, 17 unit tests |
| **Sprint 3** | Mar 10 – Mar 30 | 40 integration tests, test report, documentation |

## Bug Fixes

### `_scrape_all()` — Incorrect Python `or`-condition (Fixed in Sprint 2)

**Before (buggy):**
```python
elif "light." or "input_boolean." in entity_id:  # always True
```

**After (fixed):**
```python
elif "light." in entity_id or "input_boolean." in entity_id:  # correct
```

In Python, `"light."` is a non-empty string that always evaluates to `True`, so the original condition matched every entity regardless of type. The fix ensures only light and input_boolean entities enter this branch.

## License

This project is part of Eclipse VOLTTRON and is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
