# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2023 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}


# ---------------------------------------------------------------------------
# Imports and constants — no changes made to this section
# ---------------------------------------------------------------------------
import random
from math import pi
import json
import sys
from platform_driver.interfaces import BaseInterface, BaseRegister, BasicRevert
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent
import logging
import requests
from requests import get

_log = logging.getLogger(__name__)

# Maps string type names from the registry config to Python types
type_mapping = {"string": str,
                "int": int,
                "integer": int,
                "float": float,
                "bool": bool,
                "boolean": bool}


# ---------------------------------------------------------------------------
# HomeAssistantRegister
# Defines a register object that stores the metadata for a single device point.
# Each row in registry_config.csv becomes one register instance.
# No changes made to this class.
# ---------------------------------------------------------------------------
class HomeAssistantRegister(BaseRegister):
    def __init__(self, read_only, pointName, units, reg_type, attributes, entity_id, entity_point, default_value=None,
                 description=''):
        super(HomeAssistantRegister, self).__init__("byte", read_only, pointName, units, description='')
        self.reg_type = reg_type
        self.attributes = attributes
        self.entity_id = entity_id        # e.g. "light.bedroom", "switch.living_room_plug"
        self.value = None
        self.entity_point = entity_point  # e.g. "state", "brightness", "percentage"


# ---------------------------------------------------------------------------
# _post_method
# Helper function that wraps all HTTP POST requests to the Home Assistant REST API.
# Handles error logging and raises exceptions on failure.
# No changes made to this function.
# ---------------------------------------------------------------------------
def _post_method(url, headers, data, operation_description):
    err = None
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            _log.info(f"Success: {operation_description}")
        else:
            err = f"Failed to {operation_description}. Status code: {response.status_code}. " \
                  f"Response: {response.text}"

    except requests.RequestException as e:
        err = f"Error when attempting - {operation_description} : {e}"
    if err:
        _log.error(err)
        raise Exception(err)


# ---------------------------------------------------------------------------
# Interface
# Main driver class. Reads connection settings from config, manages registers,
# and implements the VOLTTRON PlatformDriver interface (get_point, set_point, scrape_all).
# ---------------------------------------------------------------------------
class Interface(BasicRevert, BaseInterface):
    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.point_name = None
        self.ip_address = None
        self.access_token = None
        self.port = None
        self.units = None

    # Reads driver configuration (IP, token, port) and parses the registry CSV.
    # No changes made.
    def configure(self, config_dict, registry_config_str):
        self.ip_address = config_dict.get("ip_address", None)
        self.access_token = config_dict.get("access_token", None)
        self.port = config_dict.get("port", None)

        # Check for None values
        if self.ip_address is None:
            _log.error("IP address is not set.")
            raise ValueError("IP address is required.")
        if self.access_token is None:
            _log.error("Access token is not set.")
            raise ValueError("Access token is required.")
        if self.port is None:
            _log.error("Port is not set.")
            raise ValueError("Port is required.")

        self.parse_config(registry_config_str)

    # Reads a single point from Home Assistant via the REST API.
    # Returns the state value or a specific attribute depending on the register definition.
    # No changes made.
    def get_point(self, point_name):
        register = self.get_register_by_name(point_name)

        entity_data = self.get_entity_data(register.entity_id)
        if register.point_name == "state":
            result = entity_data.get("state", None)
            return result
        else:
            value = entity_data.get("attributes", {}).get(f"{register.point_name}", 0)
            return value

    # ---------------------------------------------------------------------------
    # _set_point
    # Writes a value to a Home Assistant entity via the REST API.
    # Routes the write to the correct helper method based on the entity_id prefix.
    #
    # SPRINT 2 CHANGES:
    #   - Added elif branch for switch.* devices (on/off state control)
    #   - Added elif branch for fan.* devices (on/off state + percentage speed control)
    #   - Updated the final else error message to list all supported device types
    # ---------------------------------------------------------------------------
    def _set_point(self, point_name, value):
        register = self.get_register_by_name(point_name)

        # Reject writes to read-only points
        if register.read_only:
            raise IOError(
                "Trying to write to a point configured read only: " + point_name)

        register.value = register.reg_type(value)  # Coerce value to the declared register type
        entity_point = register.entity_point

        # --- Light control (existing, unchanged) ---
        # Supports: state (0=off, 1=on), brightness (0-255)
        if "light." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_lights(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_lights(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.info(error_msg)
                    raise ValueError(error_msg)

            elif entity_point == "brightness":
                # Brightness must be an integer in the range 0-255
                if isinstance(register.value, int) and 0 <= register.value <= 255:
                    self.change_brightness(register.entity_id, register.value)
                else:
                    error_msg = "Brightness value should be an integer between 0 and 255"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Unexpected point_name {point_name} for register {register.entity_id}"
                _log.error(error_msg)
                raise ValueError(error_msg)

        # --- Input boolean control (existing, unchanged) ---
        # Supports: state (0=off, 1=on)
        elif "input_boolean." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.set_input_boolean(register.entity_id, "on")
                    elif register.value == 0:
                        self.set_input_boolean(register.entity_id, "off")
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.info(error_msg)
                    raise ValueError(error_msg)
            else:
                _log.info(f"Currently, input_booleans only support state")

        # --- Climate / thermostat control (existing, unchanged) ---
        # Supports: state (0=off, 2=heat, 3=cool, 4=auto), temperature (numeric)
        elif "climate." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 2, 3, 4]:
                    if register.value == 0:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="off")
                    elif register.value == 2:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="heat")
                    elif register.value == 3:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="cool")
                    elif register.value == 4:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="auto")
                else:
                    error_msg = f"Climate state should be an integer value of 0, 2, 3, or 4"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            elif entity_point == "temperature":
                # Temperature unit conversion (F to C) handled inside set_thermostat_temperature
                self.set_thermostat_temperature(entity_id=register.entity_id, temperature=register.value)
            else:
                error_msg = f"Currently set_point is supported only for thermostats state and temperature {register.entity_id}"
                _log.error(error_msg)
                raise ValueError(error_msg)

        # =======================================================================
        # [SPRINT 2 - NEW] Switch control
        # Handles write-access for switch.* entities.
        # Supports: state (0=off, 1=on)
        # Calls turn_on_switch() or turn_off_switch() via the HA REST API.
        # =======================================================================
        elif "switch." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_switch(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_switch(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Currently switch only supports state, got: {entity_point}"
                _log.error(error_msg)
                raise ValueError(error_msg)

        # =======================================================================
        # [SPRINT 2 - NEW] Fan control
        # Handles write-access for fan.* entities.
        # Supports:
        #   - state (0=off, 1=on): calls turn_on_fan() or turn_off_fan()
        #   - percentage (0-100): calls set_fan_percentage() to control fan speed
        # =======================================================================
        elif "fan." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_fan(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_fan(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            elif entity_point == "percentage":
                # Fan speed percentage must be an integer between 0 and 100
                if isinstance(register.value, int) and 0 <= register.value <= 100:
                    self.set_fan_percentage(register.entity_id, register.value)
                else:
                    error_msg = f"Fan percentage for {register.entity_id} should be an integer between 0 and 100"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Fan supports state or percentage, got: {entity_point}"
                _log.error(error_msg)
                raise ValueError(error_msg)

        # --- Unsupported device type (updated error message to list all supported types) ---
        else:
            error_msg = f"Unsupported entity_id: {register.entity_id}. " \
                        f"Currently set_point is supported for lights, input_boolean, climate, switch, and fan"
            _log.error(error_msg)
            raise ValueError(error_msg)

        return register.value

    # Fetches the current state and attributes of an entity from the HA REST API.
    # Returns the full JSON response as a dict.
    # No changes made.
    def get_entity_data(self, point_name):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        # /api/states/<entity_id> returns the current state AND all attributes
        url = f"http://{self.ip_address}:{self.port}/api/states/{point_name}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"Request failed with status code {response.status_code}, Point name: {point_name}, " \
                        f"response: {response.text}"
            _log.error(error_msg)
            raise Exception(error_msg)

    # ---------------------------------------------------------------------------
    # _scrape_all
    # Reads the current state of all registered devices from Home Assistant.
    # Returns a dict mapping point names to their current values.
    #
    # SPRINT 2 CHANGES:
    #   - BUG FIX: Corrected the light/input_boolean condition from:
    #       elif "light." or "input_boolean." in entity_id:   <-- always True (Python bug)
    #     to:
    #       elif "light." in entity_id or "input_boolean." in entity_id:   <-- correct
    #   - Added elif branch to read switch.* state (returns 1 for "on", 0 for "off")
    #   - Added elif branch to read fan.* state and percentage attribute
    # ---------------------------------------------------------------------------
    def _scrape_all(self):
        result = {}
        read_registers = self.get_registers_by_type("byte", True)
        write_registers = self.get_registers_by_type("byte", False)

        for register in read_registers + write_registers:
            entity_id = register.entity_id
            entity_point = register.entity_point
            try:
                entity_data = self.get_entity_data(entity_id)

                # --- Thermostat read (existing, unchanged) ---
                # Maps HA string states ("off", "heat", "cool", "auto") to integers (0, 2, 3, 4)
                if "climate." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        if state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                        elif state == "heat":
                            register.value = 2
                            result[register.point_name] = 2
                        elif state == "cool":
                            register.value = 3
                            result[register.point_name] = 3
                        elif state == "auto":
                            register.value = 4
                            result[register.point_name] = 4
                        else:
                            error_msg = f"State {state} from {entity_id} is not yet supported"
                            _log.error(error_msg)
                            ValueError(error_msg)
                    else:
                        # Read a named attribute (e.g. current_temperature)
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute

                # =======================================================================
                # [SPRINT 2 - BUG FIX] Light and input_boolean read
                # Original code used:  elif "light." or "input_boolean." in entity_id
                # In Python, "light." alone is a non-empty string and always evaluates
                # to True, so the original condition matched ALL entities regardless of
                # type. Fixed to use proper membership checks on entity_id.
                # Maps "on"/"off" string states to 1/0 integers.
                # =======================================================================
                elif "light." in entity_id or "input_boolean." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        # Convert string state to integer (1=on, 0=off)
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                    else:
                        # Read a named attribute (e.g. brightness)
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute

                # =======================================================================
                # [SPRINT 2 - NEW] Switch read
                # Reads the current state of a switch.* entity.
                # Maps "on"/"off" string states to 1/0 integers, consistent with
                # how light and input_boolean states are handled above.
                # =======================================================================
                elif "switch." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                    else:
                        # Read a named switch attribute if specified
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute

                # =======================================================================
                # [SPRINT 2 - NEW] Fan read
                # Reads the current state and attributes of a fan.* entity.
                # Supports:
                #   - state: maps "on"/"off" to 1/0
                #   - percentage: reads the fan speed percentage from HA attributes
                # =======================================================================
                elif "fan." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                    elif entity_point == "percentage":
                        # Fan speed percentage is stored under HA attributes, not state
                        attribute = entity_data.get("attributes", {}).get("percentage", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
                    else:
                        # Read any other named fan attribute
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute

                # --- Fallback for any other device type (existing, unchanged) ---
                else:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        register.value = state
                        result[register.point_name] = state
                    else:
                        # Read a named attribute
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute

            except Exception as e:
                _log.error(f"An unexpected error occurred for entity_id: {entity_id}: {e}")

        return result

    # ---------------------------------------------------------------------------
    # parse_config
    # Reads the registry_config.csv and creates a HomeAssistantRegister for each row.
    # No changes made.
    # ---------------------------------------------------------------------------
    def parse_config(self, config_dict):

        if config_dict is None:
            return
        for regDef in config_dict:

            if not regDef['Entity ID']:
                continue

            read_only = str(regDef.get('Writable', '')).lower() != 'true'
            entity_id = regDef['Entity ID']
            entity_point = regDef['Entity Point']
            self.point_name = regDef['Volttron Point Name']
            self.units = regDef['Units']
            description = regDef.get('Notes', '')
            default_value = ("Starting Value")
            type_name = regDef.get("Type", 'string')
            reg_type = type_mapping.get(type_name, str)
            attributes = regDef.get('Attributes', {})
            register_type = HomeAssistantRegister

            register = register_type(
                read_only,
                self.point_name,
                self.units,
                reg_type,
                attributes,
                entity_id,
                entity_point,
                default_value=default_value,
                description=description)

            if default_value is not None:
                self.set_default(self.point_name, register.value)

            self.insert_register(register)

    # ---------------------------------------------------------------------------
    # Helper methods — HTTP control actions
    # Each method builds the request URL, headers, and payload, then calls
    # _post_method() to execute the POST request to the HA REST API.
    # ---------------------------------------------------------------------------

    # --- Light helpers (existing, unchanged) ---

    def turn_off_lights(self, entity_id):
        """Send a turn_off command to a light entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn off {entity_id}")

    def turn_on_lights(self, entity_id):
        """Send a turn_on command to a light entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": f"{entity_id}"}
        _post_method(url, headers, payload, f"turn on {entity_id}")

    # --- Thermostat helpers (existing, unchanged) ---

    def change_thermostat_mode(self, entity_id, mode):
        """Set the HVAC mode of a climate entity (off / heat / cool / auto)."""
        if not entity_id.startswith("climate."):
            _log.error(f"{entity_id} is not a valid thermostat entity ID.")
            return
        url = f"http://{self.ip_address}:{self.port}/api/services/climate/set_hvac_mode"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
        }
        data = {
            "entity_id": entity_id,
            "hvac_mode": mode,
        }
        _post_method(url, headers, data, f"change mode of {entity_id} to {mode}")

    def set_thermostat_temperature(self, entity_id, temperature):
        """Set the target temperature of a climate entity.
        If the register units are 'C', converts the value from Fahrenheit first."""
        if not entity_id.startswith("climate."):
            _log.error(f"{entity_id} is not a valid thermostat entity ID.")
            return
        url = f"http://{self.ip_address}:{self.port}/api/services/climate/set_temperature"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
        }
        if self.units == "C":
            converted_temp = round((temperature - 32) * 5/9, 1)
            _log.info(f"Converted temperature {converted_temp}")
            data = {"entity_id": entity_id, "temperature": converted_temp}
        else:
            data = {"entity_id": entity_id, "temperature": temperature}
        _post_method(url, headers, data, f"set temperature of {entity_id} to {temperature}")

    def change_brightness(self, entity_id, value):
        """Set the brightness of a light entity. Value must be 0-255."""
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": f"{entity_id}",
            "brightness": value,  # HA brightness range: 0-255
        }
        _post_method(url, headers, payload, f"set brightness of {entity_id} to {value}")

    # --- Input boolean helper (existing, unchanged) ---

    def set_input_boolean(self, entity_id, state):
        """Turn an input_boolean entity on or off. state should be 'on' or 'off'."""
        service = 'turn_on' if state == 'on' else 'turn_off'
        url = f"http://{self.ip_address}:{self.port}/api/services/input_boolean/{service}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"Successfully set {entity_id} to {state}")
        else:
            print(f"Failed to set {entity_id} to {state}: {response.text}")

    # =======================================================================
    # [SPRINT 2 - NEW] Switch helper methods
    # Control switch.* entities via the HA REST API.
    # Both methods follow the same pattern as the existing light helpers above.
    # =======================================================================

    def turn_on_switch(self, entity_id):
        """Send a turn_on command to a switch entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/switch/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn on switch {entity_id}")

    def turn_off_switch(self, entity_id):
        """Send a turn_off command to a switch entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/switch/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn off switch {entity_id}")

    # =======================================================================
    # [SPRINT 2 - NEW] Fan helper methods
    # Control fan.* entities via the HA REST API.
    # Supports on/off state control and fan speed via percentage (0-100).
    # =======================================================================

    def turn_on_fan(self, entity_id):
        """Send a turn_on command to a fan entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/fan/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn on fan {entity_id}")

    def turn_off_fan(self, entity_id):
        """Send a turn_off command to a fan entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/fan/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn off fan {entity_id}")

    def set_fan_percentage(self, entity_id, percentage):
        """Set the speed of a fan entity as a percentage (0-100).
        Calls the HA fan.set_percentage service."""
        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_percentage"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "percentage": percentage,  # 0 = slowest, 100 = full speed
        }
        _post_method(url, headers, payload, f"set fan {entity_id} to {percentage}%")
