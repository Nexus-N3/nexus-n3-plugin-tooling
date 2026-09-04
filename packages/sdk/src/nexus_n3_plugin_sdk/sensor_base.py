"""Base sensor contract copied from nexus-n3-core for plugin authoring."""

from __future__ import annotations

import inspect
from pathlib import Path

from nexus_n3_plugin_sdk.types.connections import ConnectionStatus
from nexus_n3_plugin_sdk.yaml_loader import load_yaml


class SensorBase:
    """Base class for plugin sensor implementations."""

    def __init__(self, sensor, spec: dict):
        self.address = None
        self.name = sensor.local_name
        self.spec = spec
        self.adapter = spec["sensor"]["adapter"]
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.transport_client = None
        self.location = None
        self.capabilities = set(spec.get("capabilities", []))
        self.attributes = {k: v.get("default") for k, v in spec.get("attributes", {}).items()}
        self.listeners = {event: None for event in spec.get("events", [])}

    @classmethod
    def load_raw_spec(cls) -> dict:
        """Load the raw YAML spec for a sensor class."""
        spec_path = getattr(cls, "SPEC_PATH", None)
        if not spec_path:
            raise ValueError(f"{cls.__name__} missing SPEC_PATH")
        path = Path(spec_path)
        if not path.is_absolute():
            module_dir = Path(inspect.getfile(cls)).parent
            candidate = module_dir / path
            if candidate.exists():
                path = candidate
        return load_yaml(path)

    def set_transport_client(self, client):
        """Assign a transport client instance."""
        self.transport_client = client

    def set_connection_status(self, status: ConnectionStatus):
        """Update sensor connection status."""
        self.connection_status = status

    def get_connection_status(self):
        """Return the current connection status."""
        return self.connection_status

    def set_location(self, location: str):
        """Set the body location, validating against the spec."""
        locations = self.spec.get("locations")
        if not locations:
            raise ValueError(f"Sensor '{self.name}' does not support body locations")
        supported = locations.get("supported", [])
        if location not in supported:
            self._emit("on_error", {"ERROR": f"Unsupported body location '{location}'."})
            return None
        self.location = location

    def has_capability(self, capability: str) -> bool:
        """Check whether a capability is declared by the spec."""
        return capability in self.capabilities

    def register_listener(self, event: str, callback):
        """Register a callback for a sensor event."""
        if event not in self.listeners:
            raise ValueError(f"Unsupported event: {event}")
        self.listeners[event] = callback

    def unregister_listener(self, event: str):
        """Remove a callback for a sensor event."""
        if event in self.listeners:
            self.listeners[event] = None

    def consume_input(self, source_plugin_id: str, payload) -> bool:
        """Handle forwarded input from another plugin.

        Return True when the payload was accepted and consumed. Plugins that do
        not need upstream plugin inputs can keep the default implementation.
        """
        return False

    def reset_session_diagnostics(self) -> None:
        """Reset optional sensor-owned counters for a new recording session."""

    def get_diagnostics_snapshot(self) -> dict:
        """Return optional JSON-serializable sensor diagnostics."""
        return {}

    def _emit(self, event: str, payload):
        """Safely emit an event to the registered callback."""
        callback = self.listeners.get(event)
        if callback:
            callback(payload)
