"""
Integration Tests for Home Assistant VOLTTRON Driver — Sprint 3
================================================================

KEY DIFFERENCE FROM SPRINT 2 UNIT TESTS:
  Unit tests mocked individual driver methods (turn_on_switch, get_entity_data).
  Integration tests mock at the HTTP transport layer (requests_mock) so the
  FULL chain is exercised:
    _set_point() → helper method → _post_method() → requests.post() → [mock HTTP]
    _scrape_all() → get_entity_data() → requests.get() → [mock HTTP] → parse response

This verifies URLs, headers, payloads, and response handling end-to-end.

Test classes:
  1. TestWritePathIntegration   — full write chain for all 5 device types
  2. TestReadPathIntegration    — full read chain via _scrape_all() + HTTP GET
  3. TestRoundTrip              — write then verify scrape reads correct value
  4. TestMultiDeviceScrape      — multiple devices in one _scrape_all() call
  5. TestAPIErrorHandling       — HA returns 500, 404, connection errors
  6. TestConfigureIntegration   — configure() with registry CSV data
  7. TestAuthHeaders            — bearer token present on every request
  8. TestGetPoint               — get_point() reads single entity via HTTP
"""

import unittest
import json
import sys
import types
from unittest.mock import MagicMock

import requests_mock as rm

# ---------------------------------------------------------------------------
# VOLTTRON stubs (same approach as Sprint 2 unit tests)
# ---------------------------------------------------------------------------
for mod in [
    "platform_driver", "platform_driver.interfaces",
    "volttron", "volttron.platform", "volttron.platform.agent",
    "volttron.platform.vip", "volttron.platform.vip.agent",
]:
    sys.modules.setdefault(mod, types.ModuleType(mod))


class FakeBaseRegister:
    def __init__(self, reg_type, read_only, point_name, units, description=''):
        self.read_only = read_only
        self.point_name = point_name
        self.units = units


class FakeBaseInterface:
    def get_register_by_name(self, name):
        return self._registers.get(name)

    def get_registers_by_type(self, rtype, read_only):
        return [r for r in self._registers.values() if r.read_only == read_only]

    def insert_register(self, reg):
        self._registers[reg.point_name] = reg

    def set_default(self, *a):
        pass


class FakeBasicRevert:
    pass


sys.modules["platform_driver.interfaces"].BaseRegister = FakeBaseRegister
sys.modules["platform_driver.interfaces"].BaseInterface = FakeBaseInterface
sys.modules["platform_driver.interfaces"].BasicRevert = FakeBasicRevert
sys.modules["volttron.platform.agent"].utils = MagicMock()
sys.modules["volttron.platform.vip.agent"].Agent = object

import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sprint2-ha-driver-extension"))
from home_assistant import Interface, HomeAssistantRegister


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "http://192.168.1.100:8123"
TOKEN = "test_bearer_token_abc123"
HA_SUCCESS = [{"entity_id": "ok"}]  # typical HA 200 response body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_interface():
    """Create an Interface instance with connection settings but no registers."""
    iface = Interface.__new__(Interface)
    iface._registers = {}
    iface.ip_address = "192.168.1.100"
    iface.port = "8123"
    iface.access_token = TOKEN
    iface.units = "F"
    return iface


def add_register(iface, entity_id, entity_point, read_only=False, reg_type=int, point_name=None):
    """Add a single register to the interface. Returns (iface, register)."""
    pname = point_name or entity_point
    reg = HomeAssistantRegister(
        read_only=read_only,
        pointName=pname,
        units="None",
        reg_type=reg_type,
        attributes={},
        entity_id=entity_id,
        entity_point=entity_point,
    )
    iface._registers[pname] = reg
    return reg


# ===========================================================================
# 1. WRITE PATH — full chain from _set_point() to HTTP POST
# ===========================================================================
class TestWritePathIntegration(unittest.TestCase):
    """Verify _set_point() sends the correct HTTP POST for every device type."""

    # --- Switch ---

    @rm.Mocker()
    def test_switch_turn_on_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/switch/turn_on", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "switch.living_room_plug", "state")

        iface._set_point("state", 1)

        self.assertEqual(m.call_count, 1)
        req = m.last_request
        self.assertEqual(req.json(), {"entity_id": "switch.living_room_plug"})

    @rm.Mocker()
    def test_switch_turn_off_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/switch/turn_off", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "switch.living_room_plug", "state")

        iface._set_point("state", 0)

        self.assertEqual(m.call_count, 1)
        self.assertIn("switch/turn_off", m.last_request.url)

    # --- Fan ---

    @rm.Mocker()
    def test_fan_turn_on_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/fan/turn_on", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "fan.bedroom", "state")

        iface._set_point("state", 1)

        self.assertEqual(m.call_count, 1)
        self.assertEqual(m.last_request.json(), {"entity_id": "fan.bedroom"})

    @rm.Mocker()
    def test_fan_turn_off_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/fan/turn_off", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "fan.bedroom", "state")

        iface._set_point("state", 0)

        self.assertIn("fan/turn_off", m.last_request.url)

    @rm.Mocker()
    def test_fan_set_percentage_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/fan/set_percentage", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "fan.bedroom", "percentage")

        iface._set_point("percentage", 75)

        payload = m.last_request.json()
        self.assertEqual(payload["entity_id"], "fan.bedroom")
        self.assertEqual(payload["percentage"], 75)

    # --- Light ---

    @rm.Mocker()
    def test_light_turn_on_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/light/turn_on", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "light.kitchen", "state")

        iface._set_point("state", 1)

        self.assertEqual(m.call_count, 1)

    @rm.Mocker()
    def test_light_turn_off_sends_correct_post(self, m):
        m.post(f"{BASE_URL}/api/services/light/turn_off", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "light.kitchen", "state")

        iface._set_point("state", 0)

        self.assertIn("light/turn_off", m.last_request.url)

    @rm.Mocker()
    def test_light_brightness_sends_correct_payload(self, m):
        m.post(f"{BASE_URL}/api/services/light/turn_on", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "light.kitchen", "brightness")

        iface._set_point("brightness", 200)

        payload = m.last_request.json()
        self.assertEqual(payload["brightness"], 200)
        self.assertIn("light.kitchen", payload["entity_id"])

    # --- Climate ---

    @rm.Mocker()
    def test_climate_set_heat_mode(self, m):
        m.post(f"{BASE_URL}/api/services/climate/set_hvac_mode", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "climate.main", "state")

        iface._set_point("state", 2)  # 2 = heat

        self.assertEqual(m.last_request.json()["hvac_mode"], "heat")

    @rm.Mocker()
    def test_climate_set_temperature_fahrenheit(self, m):
        m.post(f"{BASE_URL}/api/services/climate/set_temperature", json=HA_SUCCESS)
        iface = make_interface()
        iface.units = "F"
        add_register(iface, "climate.main", "temperature")

        iface._set_point("temperature", 72)

        # When units=F, temperature is sent as-is (no conversion)
        self.assertEqual(m.last_request.json()["temperature"], 72)

    @rm.Mocker()
    def test_climate_set_temperature_celsius_conversion(self, m):
        m.post(f"{BASE_URL}/api/services/climate/set_temperature", json=HA_SUCCESS)
        iface = make_interface()
        iface.units = "C"
        add_register(iface, "climate.main", "temperature")

        iface._set_point("temperature", 72)

        # 72°F → 22.2°C
        sent_temp = m.last_request.json()["temperature"]
        self.assertAlmostEqual(sent_temp, 22.2, places=1)

    # --- Input boolean ---

    @rm.Mocker()
    def test_input_boolean_turn_on(self, m):
        m.post(f"{BASE_URL}/api/services/input_boolean/turn_on", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "input_boolean.guest_mode", "state")

        iface._set_point("state", 1)

        self.assertEqual(m.call_count, 1)
        self.assertIn("input_boolean/turn_on", m.last_request.url)

    @rm.Mocker()
    def test_input_boolean_turn_off(self, m):
        m.post(f"{BASE_URL}/api/services/input_boolean/turn_off", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "input_boolean.guest_mode", "state")

        iface._set_point("state", 0)

        self.assertIn("input_boolean/turn_off", m.last_request.url)


# ===========================================================================
# 2. READ PATH — full chain from _scrape_all() through HTTP GET
# ===========================================================================
class TestReadPathIntegration(unittest.TestCase):
    """Verify _scrape_all() sends GET requests and correctly parses responses."""

    def _mock_entity(self, m, entity_id, state, attributes=None):
        """Register a mock GET endpoint that returns a HA-style state response."""
        m.get(
            f"{BASE_URL}/api/states/{entity_id}",
            json={"state": state, "attributes": attributes or {}},
        )

    @rm.Mocker()
    def test_switch_on_reads_as_1(self, m):
        self._mock_entity(m, "switch.plug", "on")
        iface = make_interface()
        add_register(iface, "switch.plug", "state", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["state"], 1)

    @rm.Mocker()
    def test_switch_off_reads_as_0(self, m):
        self._mock_entity(m, "switch.plug", "off")
        iface = make_interface()
        add_register(iface, "switch.plug", "state", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["state"], 0)

    @rm.Mocker()
    def test_fan_on_reads_as_1(self, m):
        self._mock_entity(m, "fan.ceiling", "on")
        iface = make_interface()
        add_register(iface, "fan.ceiling", "state", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["state"], 1)

    @rm.Mocker()
    def test_fan_percentage_reads_from_attributes(self, m):
        self._mock_entity(m, "fan.ceiling", "on", {"percentage": 60})
        iface = make_interface()
        add_register(iface, "fan.ceiling", "percentage", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["percentage"], 60)

    @rm.Mocker()
    def test_light_on_reads_as_1(self, m):
        self._mock_entity(m, "light.bedroom", "on", {"brightness": 180})
        iface = make_interface()
        add_register(iface, "light.bedroom", "state", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["state"], 1)

    @rm.Mocker()
    def test_light_brightness_reads_attribute(self, m):
        self._mock_entity(m, "light.bedroom", "on", {"brightness": 180})
        iface = make_interface()
        add_register(iface, "light.bedroom", "brightness", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["brightness"], 180)

    @rm.Mocker()
    def test_climate_heat_reads_as_2(self, m):
        self._mock_entity(m, "climate.thermostat", "heat", {"current_temperature": 70})
        iface = make_interface()
        add_register(iface, "climate.thermostat", "state", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["state"], 2)

    @rm.Mocker()
    def test_climate_current_temperature(self, m):
        self._mock_entity(m, "climate.thermostat", "heat", {"current_temperature": 68.5})
        iface = make_interface()
        add_register(iface, "climate.thermostat", "current_temperature",
                     read_only=True, point_name="current_temperature")

        result = iface._scrape_all()

        self.assertEqual(result["current_temperature"], 68.5)

    @rm.Mocker()
    def test_input_boolean_on_reads_as_1(self, m):
        self._mock_entity(m, "input_boolean.vacation", "on")
        iface = make_interface()
        add_register(iface, "input_boolean.vacation", "state", read_only=True)

        result = iface._scrape_all()

        self.assertEqual(result["state"], 1)


# ===========================================================================
# 3. ROUND-TRIP — write then read back
# ===========================================================================
class TestRoundTrip(unittest.TestCase):
    """Write a value via _set_point(), then verify _scrape_all() reads it."""

    @rm.Mocker()
    def test_switch_write_then_read(self, m):
        # Mock the POST (write) and GET (read)
        m.post(f"{BASE_URL}/api/services/switch/turn_on", json=HA_SUCCESS)
        m.get(f"{BASE_URL}/api/states/switch.plug",
              json={"state": "on", "attributes": {}})

        iface = make_interface()
        add_register(iface, "switch.plug", "state")

        # Write
        iface._set_point("state", 1)
        self.assertEqual(m.call_count, 1)  # POST

        # Read back
        result = iface._scrape_all()
        self.assertEqual(result["state"], 1)
        self.assertEqual(m.call_count, 2)  # POST + GET

    @rm.Mocker()
    def test_fan_percentage_write_then_read(self, m):
        m.post(f"{BASE_URL}/api/services/fan/set_percentage", json=HA_SUCCESS)
        m.get(f"{BASE_URL}/api/states/fan.ceiling",
              json={"state": "on", "attributes": {"percentage": 80}})

        iface = make_interface()
        add_register(iface, "fan.ceiling", "percentage")

        iface._set_point("percentage", 80)
        result = iface._scrape_all()

        self.assertEqual(result["percentage"], 80)

    @rm.Mocker()
    def test_light_brightness_write_then_read(self, m):
        m.post(f"{BASE_URL}/api/services/light/turn_on", json=HA_SUCCESS)
        m.get(f"{BASE_URL}/api/states/light.kitchen",
              json={"state": "on", "attributes": {"brightness": 128}})

        iface = make_interface()
        add_register(iface, "light.kitchen", "brightness")

        iface._set_point("brightness", 128)
        result = iface._scrape_all()

        self.assertEqual(result["brightness"], 128)


# ===========================================================================
# 4. MULTI-DEVICE SCRAPE — many devices, one _scrape_all() call
# ===========================================================================
class TestMultiDeviceScrape(unittest.TestCase):
    """Register multiple device types, verify a single _scrape_all() reads all."""

    @rm.Mocker()
    def test_all_device_types_in_one_scrape(self, m):
        # Mock GET for each entity
        m.get(f"{BASE_URL}/api/states/light.bedroom",
              json={"state": "on", "attributes": {"brightness": 200}})
        m.get(f"{BASE_URL}/api/states/switch.plug",
              json={"state": "off", "attributes": {}})
        m.get(f"{BASE_URL}/api/states/fan.ceiling",
              json={"state": "on", "attributes": {"percentage": 50}})
        m.get(f"{BASE_URL}/api/states/climate.main",
              json={"state": "cool", "attributes": {"current_temperature": 72}})
        m.get(f"{BASE_URL}/api/states/input_boolean.away",
              json={"state": "on", "attributes": {}})

        iface = make_interface()
        add_register(iface, "light.bedroom", "state", read_only=True, point_name="light_state")
        add_register(iface, "light.bedroom", "brightness", read_only=True, point_name="light_brightness")
        add_register(iface, "switch.plug", "state", read_only=True, point_name="switch_state")
        add_register(iface, "fan.ceiling", "state", read_only=True, point_name="fan_state")
        add_register(iface, "fan.ceiling", "percentage", read_only=True, point_name="fan_speed")
        add_register(iface, "climate.main", "state", read_only=True, point_name="hvac_mode")
        add_register(iface, "climate.main", "current_temperature", read_only=True, point_name="current_temp")
        add_register(iface, "input_boolean.away", "state", read_only=True, point_name="away_mode")

        result = iface._scrape_all()

        # Verify all 8 points read correctly
        self.assertEqual(result["light_state"], 1)
        self.assertEqual(result["light_brightness"], 200)
        self.assertEqual(result["switch_state"], 0)
        self.assertEqual(result["fan_state"], 1)
        self.assertEqual(result["fan_speed"], 50)
        self.assertEqual(result["hvac_mode"], 3)       # "cool" → 3
        self.assertEqual(result["current_temp"], 72)
        self.assertEqual(result["away_mode"], 1)

        # Verify correct number of HTTP GET calls
        # 5 unique entities, but light.bedroom and fan.ceiling are each called 2x
        # (once per register using that entity_id)
        self.assertEqual(m.call_count, 8)


# ===========================================================================
# 5. API ERROR HANDLING
# ===========================================================================
class TestAPIErrorHandling(unittest.TestCase):
    """Verify the driver handles HA API errors gracefully."""

    @rm.Mocker()
    def test_write_to_500_raises_exception(self, m):
        m.post(f"{BASE_URL}/api/services/switch/turn_on", status_code=500, text="Internal Server Error")
        iface = make_interface()
        add_register(iface, "switch.plug", "state")

        with self.assertRaises(Exception) as ctx:
            iface._set_point("state", 1)

        self.assertIn("500", str(ctx.exception))

    @rm.Mocker()
    def test_write_to_401_raises_exception(self, m):
        m.post(f"{BASE_URL}/api/services/fan/turn_on", status_code=401, text="Unauthorized")
        iface = make_interface()
        add_register(iface, "fan.ceiling", "state")

        with self.assertRaises(Exception) as ctx:
            iface._set_point("state", 1)

        self.assertIn("401", str(ctx.exception))

    @rm.Mocker()
    def test_read_404_raises_exception_in_get_entity_data(self, m):
        m.get(f"{BASE_URL}/api/states/switch.missing", status_code=404, text="Not Found")
        iface = make_interface()

        with self.assertRaises(Exception) as ctx:
            iface.get_entity_data("switch.missing")

        self.assertIn("404", str(ctx.exception))

    @rm.Mocker()
    def test_scrape_all_continues_on_individual_error(self, m):
        """If one entity fails, _scrape_all() should still read the others."""
        m.get(f"{BASE_URL}/api/states/switch.good",
              json={"state": "on", "attributes": {}})
        m.get(f"{BASE_URL}/api/states/switch.bad", status_code=500, text="Error")

        iface = make_interface()
        add_register(iface, "switch.good", "state", read_only=True, point_name="good_switch")
        add_register(iface, "switch.bad", "state", read_only=True, point_name="bad_switch")

        result = iface._scrape_all()

        # Good device should still be read
        self.assertEqual(result["good_switch"], 1)
        # Bad device should not appear in results (exception caught internally)
        self.assertNotIn("bad_switch", result)

    @rm.Mocker()
    def test_connection_error_raises(self, m):
        m.post(f"{BASE_URL}/api/services/switch/turn_on",
               exc=ConnectionError("Connection refused"))
        iface = make_interface()
        add_register(iface, "switch.plug", "state")

        with self.assertRaises(Exception) as ctx:
            iface._set_point("state", 1)

        self.assertIn("Connection refused", str(ctx.exception))


# ===========================================================================
# 6. CONFIGURE INTEGRATION — full configure() with registry data
# ===========================================================================
class TestConfigureIntegration(unittest.TestCase):
    """Test configure() parses config dict and registry CSV into registers."""

    def test_configure_creates_registers_from_registry(self):
        iface = Interface.__new__(Interface)
        iface._registers = {}
        iface.point_name = None
        iface.ip_address = None
        iface.access_token = None
        iface.port = None
        iface.units = None

        config = {
            "ip_address": "10.0.0.50",
            "access_token": "my_token",
            "port": "8123",
        }

        registry = [
            {
                "Entity ID": "switch.garage_door",
                "Entity Point": "state",
                "Volttron Point Name": "GarageDoor_State",
                "Units": "None",
                "Writable": "True",
                "Type": "int",
                "Notes": "Garage door switch",
            },
            {
                "Entity ID": "fan.attic",
                "Entity Point": "percentage",
                "Volttron Point Name": "AtticFan_Speed",
                "Units": "None",
                "Writable": "True",
                "Type": "int",
                "Notes": "Attic fan speed",
            },
        ]

        iface.configure(config, registry)

        # Verify connection settings
        self.assertEqual(iface.ip_address, "10.0.0.50")
        self.assertEqual(iface.access_token, "my_token")

        # Verify registers were created
        reg1 = iface.get_register_by_name("GarageDoor_State")
        self.assertIsNotNone(reg1)
        self.assertEqual(reg1.entity_id, "switch.garage_door")
        self.assertEqual(reg1.entity_point, "state")
        self.assertFalse(reg1.read_only)

        reg2 = iface.get_register_by_name("AtticFan_Speed")
        self.assertIsNotNone(reg2)
        self.assertEqual(reg2.entity_id, "fan.attic")

    def test_configure_missing_ip_raises(self):
        iface = Interface.__new__(Interface)
        iface._registers = {}
        iface.point_name = None
        iface.ip_address = None
        iface.access_token = None
        iface.port = None
        iface.units = None

        with self.assertRaises(ValueError):
            iface.configure({"access_token": "x", "port": "8123"}, [])

    def test_configure_missing_token_raises(self):
        iface = Interface.__new__(Interface)
        iface._registers = {}
        iface.point_name = None
        iface.ip_address = None
        iface.access_token = None
        iface.port = None
        iface.units = None

        with self.assertRaises(ValueError):
            iface.configure({"ip_address": "1.2.3.4", "port": "8123"}, [])


# ===========================================================================
# 7. AUTH HEADERS — verify bearer token on every request
# ===========================================================================
class TestAuthHeaders(unittest.TestCase):
    """Ensure every HTTP request includes the correct Authorization header."""

    @rm.Mocker()
    def test_write_includes_bearer_token(self, m):
        m.post(f"{BASE_URL}/api/services/switch/turn_on", json=HA_SUCCESS)
        iface = make_interface()
        add_register(iface, "switch.plug", "state")

        iface._set_point("state", 1)

        auth = m.last_request.headers.get("Authorization")
        self.assertEqual(auth, f"Bearer {TOKEN}")

    @rm.Mocker()
    def test_read_includes_bearer_token(self, m):
        m.get(f"{BASE_URL}/api/states/fan.ceiling",
              json={"state": "on", "attributes": {}})
        iface = make_interface()
        add_register(iface, "fan.ceiling", "state", read_only=True)

        iface._scrape_all()

        auth = m.last_request.headers.get("Authorization")
        self.assertEqual(auth, f"Bearer {TOKEN}")

    @rm.Mocker()
    def test_get_entity_data_includes_bearer_token(self, m):
        m.get(f"{BASE_URL}/api/states/light.test",
              json={"state": "off", "attributes": {}})
        iface = make_interface()

        iface.get_entity_data("light.test")

        auth = m.last_request.headers.get("Authorization")
        self.assertEqual(auth, f"Bearer {TOKEN}")


# ===========================================================================
# 8. GET_POINT — single entity read via HTTP
# ===========================================================================
class TestGetPoint(unittest.TestCase):
    """Verify get_point() reads from the HA REST API correctly."""

    @rm.Mocker()
    def test_get_point_returns_state(self, m):
        m.get(f"{BASE_URL}/api/states/switch.plug",
              json={"state": "on", "attributes": {}})
        iface = make_interface()
        add_register(iface, "switch.plug", "state", point_name="state")

        val = iface.get_point("state")

        self.assertEqual(val, "on")

    @rm.Mocker()
    def test_get_point_returns_attribute(self, m):
        m.get(f"{BASE_URL}/api/states/fan.ceiling",
              json={"state": "on", "attributes": {"percentage": 42}})
        iface = make_interface()
        add_register(iface, "fan.ceiling", "percentage", point_name="percentage")

        val = iface.get_point("percentage")

        self.assertEqual(val, 42)

    @rm.Mocker()
    def test_get_point_returns_brightness(self, m):
        m.get(f"{BASE_URL}/api/states/light.lamp",
              json={"state": "on", "attributes": {"brightness": 220}})
        iface = make_interface()
        add_register(iface, "light.lamp", "brightness", point_name="brightness")

        val = iface.get_point("brightness")

        self.assertEqual(val, 220)


if __name__ == "__main__":
    unittest.main(verbosity=2)
