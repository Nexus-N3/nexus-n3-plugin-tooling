"""Reduced sensor-manager runtime adapted for plugin harness execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import time
from typing import Any, Protocol

from nexus_n3_plugin_sdk.types.connections import ConnectionStatus

from .adapter_pool import HarnessAdapterPool
from .ble_runtime import HarnessBLERuntimeConfig, normalize_ble_backend
from .connection_service import ConnectionService
from .config import HarnessConfig, HarnessPluginTarget
from .discovery_service import DiscoveryService
from .events import HarnessEvent, HarnessSummary
from .polling_stream_service import PollingStreamService
from .sensor_controller import SensorController
from .streaming_service import StreamingService


class SensorManagerAdapterProtocol(Protocol):
    """Minimal adapter contract required by sensor plugins in the harness."""

    adapter_type: str

    async def discover_devices(self, names: list[str], timeout: float = 5.0):
        ...

    async def connect_to_device(self, sensor, adapter, timeout: float = 10.0):
        ...

    async def disconnect(self, client):
        ...

    async def read(self, client, uuid):
        ...

    async def write(self, client, uuid, payload):
        ...

    async def set_notify_callback(self, client, uuid, callback):
        ...

    async def unset_notify_callback(self, client, uuid):
        ...

    def create_transport_client(self, address: str, loop=None, disconnected_callback=None):
        ...


@dataclass
class HarnessSensorManager:
    """Reduced sensor-manager facade used by the harness runtime."""

    config: HarnessConfig
    target: HarnessPluginTarget
    observed_events: list[HarnessEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.logger = logging.getLogger("nexus_n3_plugin_harness.sensor_manager")
        self.listeners = {
            "on_discover": None,
            "on_connected": None,
            "on_disconnected": None,
            "on_data": None,
            "on_identify": None,
            "on_battery": None,
            "on_button": None,
            "on_stream_started": None,
            "on_stream_stopped": None,
            "on_error": None,
        }
        runtime_config = HarnessBLERuntimeConfig(
            backend=normalize_ble_backend(self.config.adapter_backend),
            gateway_serial_port=self.config.gateway_serial_port,
            gateway_baudrate=self.config.gateway_baudrate,
            gateway_protocol_version=self.config.gateway_protocol_version,
        )
        self.ble_runtime_config = runtime_config
        self.adapter_pool = HarnessAdapterPool(runtime_config)
        self.sensors: list[Any] = []
        self.polling_stream_service = PollingStreamService()
        self.discovery_service = DiscoveryService(self.adapter_pool)
        self.connection_service = ConnectionService(self.adapter_pool)
        self.streaming_service = StreamingService(
            adapter_pool=self.adapter_pool,
            polling_stream_service=self.polling_stream_service,
        )
        self.controller = SensorController(
            sensors_ref=lambda: self.sensors,
            get_connected_sensors=self.get_connected_sensors,
            get_connected_sensor_by_address=self.get_connected_sensor_by_address,
            set_up_sensor=self.set_up_sensor,
            register_listeners_with_sensor=self.register_listeners_with_sensor,
            emit_to_client=self._emit_to_client,
            loop=None,
            adapter_pool=self.adapter_pool,
            discovery_service=self.discovery_service,
            connection_service=self.connection_service,
            streaming_service=self.streaming_service,
        )

    def record_event(self, event_name: str, payload: Any) -> None:
        self.observed_events.append(
            HarnessEvent(
                event_name=event_name,
                payload=payload,
                payload_type=type(payload).__name__,
                timestamp=time(),
            )
        )

    def register_listener(self, listener_event: str, listener_callback) -> None:
        if listener_event not in self.listeners:
            raise ValueError(f"Unsupported event type: {listener_event}")
        self.listeners[listener_event] = listener_callback

    def _emit_to_client(self, event_name: str, payload: Any) -> None:
        self.record_event(event_name, payload)
        callback = self.listeners.get(event_name)
        if callback:
            callback(payload)

    def register_listeners_with_sensor(self, sensor) -> None:
        for event_name in sensor.listeners.keys():
            if event_name in self.listeners:
                sensor.register_listener(
                    event_name,
                    lambda payload, en=event_name: self._emit_to_client(en, payload),
                )

    def init_sensor_manager(self, sensors_to_init: list[Any]) -> None:
        self.sensors = []
        self.adapter_pool.reset()

        for sensor in sensors_to_init:
            for name, value in self.config.attributes.items():
                sensor.attributes[name] = value
            if self.config.location:
                sensor.set_location(self.config.location)
            else:
                default_location = self._default_location_for_sensor(sensor)
                if default_location:
                    sensor.set_location(default_location)
            self.adapter_pool.get_or_create(sensor.adapter)
            self.register_listeners_with_sensor(sensor)
            self.sensors.append(sensor)

    async def set_up_sensor(self, sensor) -> None:
        adapter = self.adapter_pool.for_sensor(sensor)
        setattr(sensor, "_runtime_adapter", adapter)
        setup = getattr(sensor, "setup", None)
        if callable(setup):
            await setup(
                adapter,
                enable_battery=self.listeners["on_battery"] is not None,
                enable_button=self.listeners["on_button"] is not None,
            )

    def get_connected_sensors(self) -> list[Any]:
        return [
            sensor
            for sensor in self.sensors
            if getattr(getattr(sensor, "connection_status", None), "name", None)
            == ConnectionStatus.CONNECTED.name
        ]

    def get_connected_sensor_by_address(self, address: str) -> list[Any]:
        return [
            sensor
            for sensor in self.sensors
            if getattr(getattr(sensor, "connection_status", None), "name", None)
            == ConnectionStatus.CONNECTED.name
            and getattr(sensor, "address", None) == address
        ]

    async def dispatch(self, msg: dict):
        return await self.controller.dispatch(msg)

    async def discover(self, timeout: float = 5.0) -> list[Any]:
        return await self.dispatch({"message": "discover", "timeout": timeout})

    async def connect_all(self) -> list[Any]:
        return await self.dispatch({"message": "connect_all"})

    async def identify_all(self) -> list[str]:
        identified = []
        for sensor in self.get_connected_sensors():
            identify = getattr(sensor, "identify", None)
            if callable(identify):
                await identify(self.adapter_pool.for_sensor(sensor))
                identified.append(sensor.address)
        if identified:
            self._emit_to_client("on_identify", identified)
        return identified

    async def start_stream(self) -> None:
        await self.dispatch({"message": "start_all"})

    async def stop_stream(self) -> None:
        await self.dispatch({"message": "stop_all"})

    async def disconnect_all(self) -> list[str]:
        return await self.dispatch({"message": "disconnect_all"})

    async def shutdown(self) -> None:
        await self.streaming_service.shutdown()
        self.adapter_pool.close_all()

    @staticmethod
    def _default_location_for_sensor(sensor) -> str | None:
        spec = getattr(sensor, "spec", {}) or {}
        locations = spec.get("locations") or {}
        supported = list(locations.get("supported") or [])
        if len(supported) == 1:
            return supported[0]
        return None

    def build_summary(
        self,
        *,
        entry_point: str,
        capabilities: list[str],
        declared_events: list[str],
        consume_input_supported: bool,
    ) -> HarnessSummary:
        return HarnessSummary(
            plugin_id=self.target.plugin_id,
            entry_point=entry_point,
            adapter_family=self.target.adapter_family,
            adapter_backend=self.ble_runtime_config.backend_label,
            capabilities=capabilities,
            declared_events=declared_events,
            observed_events=list(self.observed_events),
            consume_input_supported=consume_input_supported,
        )
