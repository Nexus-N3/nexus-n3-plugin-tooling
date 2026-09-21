"""Gateway-backed BLE adapter for harness execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from nexus_n3_plugin_sdk.types.connections import ConnectionStatus

from ..ble_runtime import HarnessBLERuntimeConfig
from .gateway_ble_client import (
    GatewaySerialClient,
    SensorConnection,
    StreamFrame,
    discovered_devices_to_discovery_map,
)


@dataclass
class GatewayBLETransportClient:
    """Per-sensor proxy transport client for gateway-managed BLE."""

    address: str
    disconnected_callback: Callable[[Any], None] | None = None
    is_connected: bool = False
    sensor_id: int | None = None
    binary_notify_uuid: str | None = None
    suppress_disconnect_event: bool = False
    notify_callbacks: dict[str, Callable[[Any, bytes], Any]] = field(default_factory=dict)


class GatewayBLEAdapter:
    """Reduced gateway adapter preserving the plugin BLE contract."""

    adapter_type = "BLE"

    def __init__(self, runtime_config: HarnessBLERuntimeConfig):
        self.runtime_config = runtime_config
        self.gateway_client = GatewaySerialClient(
            self.runtime_config,
            client_name="nexus_n3_plugin_harness",
            verbose=False,
        )
        self.transport_clients: dict[str, GatewayBLETransportClient] = {}
        self.gateway_client.register_event_handler("sensor_disconnected", self._handle_sensor_disconnected)
        self.gateway_client.register_event_handler("notification", self._handle_notification)
        self.gateway_client.register_event_handler("stream_frame", self._handle_stream_frame)

    def close(self):
        self.transport_clients.clear()
        self.gateway_client.close()

    def create_transport_client(self, address: str, loop=None, disconnected_callback=None):
        _ = loop
        client = GatewayBLETransportClient(
            address=address,
            disconnected_callback=disconnected_callback,
        )
        self.transport_clients[address.strip().upper()] = client
        return client

    async def discover_devices(self, requested, timeout: float = 5.0):
        timeout_ms = max(int(timeout * 1000.0), 1000)
        requested_names = []
        requires_unfiltered_scan = False
        for item in requested:
            name = item if isinstance(item, str) else getattr(item, "name", "")
            if not isinstance(item, str):
                spec = getattr(item, "spec", {}) or {}
                discovery = spec.get("discovery", {}) or {}
                if discovery.get("service_uuids"):
                    requires_unfiltered_scan = True
                prefixes = discovery.get("local_name_prefixes", []) or []
                if prefixes:
                    requested_names.extend(
                        str(prefix).strip() for prefix in prefixes if str(prefix).strip()
                    )
                    continue
            normalized = str(name).strip()
            if normalized:
                requested_names.append(normalized)
        unique_names = sorted(set(requested_names))

        if requires_unfiltered_scan or not unique_names:
            devices = await asyncio.to_thread(
                lambda: self.gateway_client.scan(timeout_ms)
            )
        elif len(unique_names) == 1:
            devices = await asyncio.to_thread(
                lambda: self.gateway_client.scan(
                    timeout_ms,
                    name_prefix_filter=unique_names[0],
                )
            )
        else:
            devices = await asyncio.to_thread(
                lambda: self.gateway_client.scan(timeout_ms)
            )
        return discovered_devices_to_discovery_map(devices)

    async def connect(self, client: GatewayBLETransportClient):
        connections = await asyncio.to_thread(
            self.gateway_client.connect,
            [client.address],
            self.runtime_config.gateway_connect_timeout_s,
        )
        if not connections:
            return False
        connection = connections[0]
        client.sensor_id = getattr(connection, "sensor_id", None)
        client.is_connected = True
        return True

    async def disconnect(self, client: GatewayBLETransportClient):
        client.suppress_disconnect_event = True
        try:
            disconnected = await asyncio.to_thread(
                lambda: self.gateway_client.disconnect(
                    [client.address],
                    self.runtime_config.gateway_connect_timeout_s,
                    allow_timeout=False,
                )
            )
            ok = client.address.strip().upper() in disconnected
            client.is_connected = False
            client.sensor_id = None
            client.binary_notify_uuid = None
            client.notify_callbacks.clear()
            self.transport_clients.pop(client.address.strip().upper(), None)
            return ok
        finally:
            client.suppress_disconnect_event = False

    async def connect_to_device(self, sensor, _adapter, timeout: float = 10.0):
        connected = await asyncio.wait_for(self.connect(sensor.transport_client), timeout=timeout)
        if connected:
            sensor.set_connection_status(ConnectionStatus.CONNECTED)
        return connected

    async def set_notify_callback(self, client: GatewayBLETransportClient, uuid, callback, *, indicate: bool = False,):
        subscribe_as_binary = (
            not indicate
            and len(client.notify_callbacks) == 0
        )

        client.notify_callbacks[str(uuid)] = callback
        if subscribe_as_binary:
            client.binary_notify_uuid = str(uuid)

        await asyncio.to_thread(
            self.gateway_client.subscribe_with_retry,
            client.address,
            str(uuid),
            self.runtime_config.gateway_subscribe_timeout_s,
            binary_notifications=subscribe_as_binary,
            indicate=indicate
        )

    async def unset_notify_callback(self, client: GatewayBLETransportClient, uuid):
        characteristic_uuid = str(uuid)
        await asyncio.to_thread(
            self.gateway_client.unsubscribe,
            client.address,
            characteristic_uuid,
            self.runtime_config.gateway_subscribe_timeout_s,
        )
        client.notify_callbacks.pop(characteristic_uuid, None)
        if client.binary_notify_uuid == characteristic_uuid:
            client.binary_notify_uuid = None

    async def write(self, client: GatewayBLETransportClient, uuid, payload):
        return await asyncio.to_thread(
            self.gateway_client.write_gatt,
            client.address,
            str(uuid),
            bytes(payload).hex(),
            self.runtime_config.gateway_write_timeout_s,
        )

    async def read(self, client: GatewayBLETransportClient, uuid):
        return await asyncio.to_thread(
            self.gateway_client.read_gatt,
            client.address,
            str(uuid),
            self.runtime_config.gateway_read_timeout_s,
        )

    def _handle_sensor_disconnected(self, msg: dict[str, Any]) -> None:
        address = str(msg.get("address", "")).strip().upper()
        if not address:
            return
        transport_client = self.transport_clients.get(address)
        if not transport_client:
            return
        if transport_client.suppress_disconnect_event:
            transport_client.is_connected = False
            return
        transport_client.is_connected = False
        if transport_client.disconnected_callback:
            transport_client.disconnected_callback(transport_client)

    def _handle_notification(self, msg: dict[str, Any]) -> None:
        address = str(msg.get("address", "")).strip().upper()
        uuid = str(msg.get("characteristic_uuid", ""))
        payload_hex = str(msg.get("payload_hex", ""))
        if not address or not uuid:
            return
        transport_client = self.transport_clients.get(address)
        if not transport_client:
            return
        callback = transport_client.notify_callbacks.get(uuid)
        if not callback:
            return
        callback(uuid, bytes.fromhex(payload_hex))

    def _handle_stream_frame(self, frame: StreamFrame) -> None:
        transport_client = None
        for candidate in self.transport_clients.values():
            if candidate.sensor_id == frame.sensor_id:
                transport_client = candidate
                break
        if not transport_client or not transport_client.binary_notify_uuid:
            return
        callback = transport_client.notify_callbacks.get(transport_client.binary_notify_uuid)
        if not callback:
            return
        callback(transport_client.binary_notify_uuid, frame.payload)
