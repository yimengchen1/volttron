"""
Simple unit tests for Sprint 2 changes to home_assistant.py
Tests cover:
  - Switch on/off via _set_point()
  - Fan on/off and percentage via _set_point()
  - Switch and fan state reading via _scrape_all()
  - Bug fix: light/input_boolean condition in _scrape_all()
  - Invalid value rejection
"""

import unittest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Minimal stubs so we can import without VOLTTRON installed
# ---------------------------------------------------------------------------
import sys
import types

# Stub out volttron and platform_driver modules
for mod in [
    "platform_driver",
    "platform_driver.interfaces",
    "volttron",
    "volttron.platform",
    "volttron.platform.agent",
    "volttron.platform.vip",
    "volttron.platform.vip.agent",
]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

# Minimal base classes
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
    def set_default(self, *a): pass

class FakeBasicRevert: pass

sys.modules["platform_driver.interfaces"].BaseRegister   = FakeBaseRegister
sys.modules["platform_driver.interfaces"].BaseInterface  = FakeBaseInterface
sys.modules["platform_driver.interfaces"].BasicRevert    = FakeBasicRevert
sys.modules["volttron.platform.agent"].utils             = MagicMock()
sys.modules["volttron.platform.vip.agent"].Agent         = object

# Now import the driver
sys.path.insert(0, "/home/claude")
from home_assistant_final import Interface, HomeAssistantRegister


# ---------------------------------------------------------------------------
# Helper — build a ready-to-use Interface with one register
# ---------------------------------------------------------------------------
def make_interface(entity_id, entity_point, read_only=False, reg_type=int):
    iface = Interface.__new__(Interface)
    iface._registers   = {}
    iface.ip_address   = "192.168.1.1"
    iface.port         = "8123"
    iface.access_token = "fake_token"
    iface.units        = "F"

    reg = HomeAssistantRegister(
        read_only   = read_only,
        pointName   = entity_point,
        units       = "None",
        reg_type    = reg_type,
        attributes  = {},
        entity_id   = entity_id,
        entity_point= entity_point,
    )
    iface._registers[entity_point] = reg
    return iface, reg


# ===========================================================================
# Tests
# ===========================================================================

class TestSwitchSetPoint(unittest.TestCase):
    """_set_point() — switch.* entities"""

    def test_turn_on_switch(self):
        iface, _ = make_interface("switch.living_room_plug", "state")
        with patch.object(iface, "turn_on_switch") as mock_on:
            iface._set_point("state", 1)
            mock_on.assert_called_once_with("switch.living_room_plug")

    def test_turn_off_switch(self):
        iface, _ = make_interface("switch.living_room_plug", "state")
        with patch.object(iface, "turn_off_switch") as mock_off:
            iface._set_point("state", 0)
            mock_off.assert_called_once_with("switch.living_room_plug")

    def test_invalid_switch_value_raises(self):
        iface, _ = make_interface("switch.living_room_plug", "state")
        with self.assertRaises(ValueError):
            iface._set_point("state", 5)

    def test_unsupported_switch_point_raises(self):
        iface, _ = make_interface("switch.living_room_plug", "brightness")
        with self.assertRaises(ValueError):
            iface._set_point("brightness", 1)


class TestFanSetPoint(unittest.TestCase):
    """_set_point() — fan.* entities"""

    def test_turn_on_fan(self):
        iface, _ = make_interface("fan.bedroom_fan", "state")
        with patch.object(iface, "turn_on_fan") as mock_on:
            iface._set_point("state", 1)
            mock_on.assert_called_once_with("fan.bedroom_fan")

    def test_turn_off_fan(self):
        iface, _ = make_interface("fan.bedroom_fan", "state")
        with patch.object(iface, "turn_off_fan") as mock_off:
            iface._set_point("state", 0)
            mock_off.assert_called_once_with("fan.bedroom_fan")

    def test_set_fan_percentage(self):
        iface, _ = make_interface("fan.bedroom_fan", "percentage")
        with patch.object(iface, "set_fan_percentage") as mock_pct:
            iface._set_point("percentage", 60)
            mock_pct.assert_called_once_with("fan.bedroom_fan", 60)

    def test_invalid_percentage_raises(self):
        iface, _ = make_interface("fan.bedroom_fan", "percentage")
        with self.assertRaises(ValueError):
            iface._set_point("percentage", 150)

    def test_invalid_fan_state_raises(self):
        iface, _ = make_interface("fan.bedroom_fan", "state")
        with self.assertRaises(ValueError):
            iface._set_point("state", 99)


class TestScrapeAll(unittest.TestCase):
    """_scrape_all() — reading switch and fan state"""

    def _run_scrape(self, entity_id, entity_point, api_state, api_attrs=None):
        """Helper: set up a single register, mock get_entity_data, run _scrape_all."""
        iface, _ = make_interface(entity_id, entity_point, read_only=True)
        entity_data = {"state": api_state, "attributes": api_attrs or {}}
        with patch.object(iface, "get_entity_data", return_value=entity_data):
            return iface._scrape_all()

    def test_switch_on_reads_as_1(self):
        result = self._run_scrape("switch.plug", "state", "on")
        self.assertEqual(result["state"], 1)

    def test_switch_off_reads_as_0(self):
        result = self._run_scrape("switch.plug", "state", "off")
        self.assertEqual(result["state"], 0)

    def test_fan_on_reads_as_1(self):
        result = self._run_scrape("fan.bedroom_fan", "state", "on")
        self.assertEqual(result["state"], 1)

    def test_fan_off_reads_as_0(self):
        result = self._run_scrape("fan.bedroom_fan", "state", "off")
        self.assertEqual(result["state"], 0)

    def test_fan_percentage_reads_correctly(self):
        result = self._run_scrape("fan.bedroom_fan", "percentage", "on", {"percentage": 75})
        self.assertEqual(result["percentage"], 75)

    def test_light_still_reads_correctly(self):
        """Regression: bug fix should not break existing light reading."""
        result = self._run_scrape("light.bedroom", "state", "on")
        self.assertEqual(result["state"], 1)


class TestReadOnlyRejection(unittest.TestCase):
    """_set_point() should always reject read-only points."""

    def test_read_only_switch_raises(self):
        iface, _ = make_interface("switch.plug", "state", read_only=True)
        with self.assertRaises(IOError):
            iface._set_point("state", 1)

    def test_read_only_fan_raises(self):
        iface, _ = make_interface("fan.bedroom_fan", "state", read_only=True)
        with self.assertRaises(IOError):
            iface._set_point("state", 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
