import asyncio
import importlib
import logging
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeConfigEntryNotReady(Exception):
    def __init__(self, message: str = "", *, translation_key: str | None = None):
        super().__init__(message)
        self.translation_key = translation_key
        self.translation_placeholders = None


class _FakeBleakError(Exception):
    pass


class _FakeConfigEntry:
    def __class_getitem__(cls, item):
        return cls


class _FakeDataCoordinator:
    def __init__(self, hass, ftms):
        self.hass = hass
        self.ftms = ftms


class _FakeFtmsData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeMachine:
    def __init__(self, exc: Exception):
        self._exc = exc
        self.disconnect_calls = 0

    async def connect(self):
        raise self._exc

    async def disconnect(self):
        self.disconnect_calls += 1


class _FakeHass:
    pass


class _FakeEntry:
    def __init__(self, address: str):
        self.data = {"address": address}
        self.options = {"sensors": []}
        self.entry_id = "entry-1"


class FtmsInitTests(unittest.TestCase):
    def tearDown(self):
        for name in [
            "custom_components.ftms",
            "custom_components.ftms.coordinator",
            "custom_components.ftms.models",
            "pyftms",
            "bleak",
            "bleak.exc",
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.bluetooth",
            "homeassistant.components.bluetooth.match",
            "homeassistant.config_entries",
            "homeassistant.const",
            "homeassistant.core",
            "homeassistant.exceptions",
            "homeassistant.helpers",
            "homeassistant.helpers.device_registry",
        ]:
            sys.modules.pop(name, None)

    def _load_module(self, exc: Exception):
        fake_machine = _FakeMachine(exc)

        pyftms = types.ModuleType("pyftms")
        pyftms.get_client = lambda *args, **kwargs: fake_machine
        pyftms.NotFitnessMachineError = type("NotFitnessMachineError", (Exception,), {})
        pyftms.FitnessMachine = object
        sys.modules["pyftms"] = pyftms

        bleak = types.ModuleType("bleak")
        bleak_exc = types.ModuleType("bleak.exc")
        bleak_exc.BleakError = _FakeBleakError
        sys.modules["bleak"] = bleak
        sys.modules["bleak.exc"] = bleak_exc

        ha = types.ModuleType("homeassistant")
        ha_components = types.ModuleType("homeassistant.components")
        ha_bluetooth = types.ModuleType("homeassistant.components.bluetooth")
        ha_bluetooth.async_last_service_info = (
            lambda hass, address: types.SimpleNamespace(
                device=object(), advertisement=object()
            )
        )
        ha_match = types.ModuleType("homeassistant.components.bluetooth.match")
        ha_match.BluetoothCallbackMatcher = lambda **kwargs: kwargs
        ha_config_entries = types.ModuleType("homeassistant.config_entries")
        ha_config_entries.ConfigEntry = _FakeConfigEntry
        ha_const = types.ModuleType("homeassistant.const")
        ha_const.CONF_ADDRESS = "address"
        ha_const.CONF_SENSORS = "sensors"
        ha_const.EVENT_HOMEASSISTANT_STOP = "stop"
        ha_const.Platform = types.SimpleNamespace(
            BUTTON="button",
            NUMBER="number",
            SENSOR="sensor",
            SWITCH="switch",
        )
        ha_core = types.ModuleType("homeassistant.core")
        ha_core.Event = object
        ha_core.HomeAssistant = object
        ha_core.callback = lambda func: func
        ha_exceptions = types.ModuleType("homeassistant.exceptions")
        ha_exceptions.ConfigEntryNotReady = _FakeConfigEntryNotReady
        ha_helpers = types.ModuleType("homeassistant.helpers")
        ha_device_registry = types.ModuleType("homeassistant.helpers.device_registry")
        ha_device_registry.CONNECTION_BLUETOOTH = "bluetooth"
        ha_device_registry.DeviceInfo = dict

        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.components"] = ha_components
        sys.modules["homeassistant.components.bluetooth"] = ha_bluetooth
        sys.modules["homeassistant.components.bluetooth.match"] = ha_match
        sys.modules["homeassistant.config_entries"] = ha_config_entries
        sys.modules["homeassistant.const"] = ha_const
        sys.modules["homeassistant.core"] = ha_core
        sys.modules["homeassistant.exceptions"] = ha_exceptions
        sys.modules["homeassistant.helpers"] = ha_helpers
        sys.modules["homeassistant.helpers.device_registry"] = ha_device_registry

        coordinator = types.ModuleType("custom_components.ftms.coordinator")
        coordinator.DataCoordinator = _FakeDataCoordinator
        models = types.ModuleType("custom_components.ftms.models")
        models.FtmsData = _FakeFtmsData
        sys.modules["custom_components.ftms.coordinator"] = coordinator
        sys.modules["custom_components.ftms.models"] = models

        module = importlib.import_module("custom_components.ftms")
        return module, fake_machine

    def test_async_setup_entry_maps_timeout_to_startup_timeout(self):
        module, machine = self._load_module(TimeoutError("read timed out"))
        hass = _FakeHass()
        entry = _FakeEntry("AA:BB")

        with self.assertLogs("custom_components.ftms", level="WARNING") as logs:
            with self.assertRaises(_FakeConfigEntryNotReady) as ctx:
                asyncio.run(module.async_setup_entry(hass, entry))

        self.assertEqual(ctx.exception.translation_key, "startup_timeout")
        self.assertEqual(machine.disconnect_calls, 1)
        self.assertIn("AA:BB", "\n".join(logs.output))
        self.assertIn("retry setup automatically", "\n".join(logs.output))

    def test_async_setup_entry_keeps_bleak_error_as_connection_failed(self):
        module, machine = self._load_module(_FakeBleakError("radio busy"))
        hass = _FakeHass()
        entry = _FakeEntry("AA:BB")

        with self.assertLogs("custom_components.ftms", level="WARNING") as logs:
            with self.assertRaises(_FakeConfigEntryNotReady) as ctx:
                asyncio.run(module.async_setup_entry(hass, entry))

        self.assertEqual(ctx.exception.translation_key, "connection_failed")
        self.assertEqual(machine.disconnect_calls, 1)
        self.assertIn("AA:BB", "\n".join(logs.output))
        self.assertIn("retry setup automatically", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
