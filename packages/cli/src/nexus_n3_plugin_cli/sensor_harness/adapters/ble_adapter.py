"""Bleak-backed BLE adapter for harness execution."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from nexus_n3_plugin_sdk.types.connections import ConnectionStatus

from ..ble_runtime import HarnessBLERuntimeConfig


class BLEAdapter:
    """Reduced BLE adapter preserving the sensor-facing contract."""

    adapter_type = "BLE"

    def __init__(self, runtime_config: HarnessBLERuntimeConfig):
        self.runtime_config = runtime_config

    @staticmethod
    def _import_bleak():
        try:
            from bleak import BleakClient, BleakScanner  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Bleak backend requested but 'bleak' is not installed in this environment."
            ) from exc
        return BleakClient, BleakScanner

    def create_transport_client(self, address: str, loop=None, disconnected_callback=None):
        BleakClient, _ = self._import_bleak()
        return BleakClient(address, disconnected_callback=disconnected_callback)

    async def discover_devices(self, requested, timeout: float = 5.0):
        _, BleakScanner = self._import_bleak()
        discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
        device_map = {}
        for address, pair in discovered.items():
            device, adv_data = pair
            local_name = getattr(adv_data, "local_name", None) or getattr(device, "name", None) or ""
            normalized_adv = SimpleNamespace(
                local_name=local_name,
                service_uuids=tuple(getattr(adv_data, "service_uuids", ()) or ()),
            )
            device_map[address] = (device, normalized_adv)
        return device_map

    async def connect(self, client):
        return await client.connect()

    async def disconnect(self, client):
        result = await client.disconnect()
        if result is None:
            return not bool(getattr(client, "is_connected", False))
        return result

    async def connect_to_device(self, sensor, _adapter, timeout: float = 10.0):
        connected = await asyncio.wait_for(self.connect(sensor.transport_client), timeout=timeout)
        if connected is None:
            connected = bool(getattr(sensor.transport_client, "is_connected", False))
        if connected:
            sensor.set_connection_status(ConnectionStatus.CONNECTED)
        return connected

    async def read(self, client, uuid):
        return await client.read_gatt_char(uuid)

    async def write(self, client, uuid, payload):
        return await client.write_gatt_char(uuid, payload, response=True)

    async def set_notify_callback(self, client, uuid, callback, *, indicate: bool = False):
        def wrapped(sender, data):
            result = callback(sender, data)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
            return result

        return await client.start_notify(uuid, wrapped)

    async def unset_notify_callback(self, client, uuid):
        return await client.stop_notify(uuid)
