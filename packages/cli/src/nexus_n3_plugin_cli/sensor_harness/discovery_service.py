"""Sensor discovery service for the harness manager."""

from __future__ import annotations

from nexus_n3_plugin_sdk.types.connections import ConnectionStatus


class DiscoveryService:
    """Discovery workflows for harness-managed sensors."""

    def __init__(self, adapter_pool):
        self.adapter_pool = adapter_pool

    async def discover_all(
        self,
        sensors,
        loop,
        register_listeners_with_sensor,
        emit_to_client,
        timeout: float = 5.0,
    ):
        pending_sensors = [sensor for sensor in sensors if getattr(sensor, "address", None) is None]
        print("Discovery service: discovering sensors", pending_sensors)
        return await self._discover_pending(
            pending_sensors=pending_sensors,
            loop=loop,
            register_listeners_with_sensor=register_listeners_with_sensor,
            emit_to_client=emit_to_client,
            timeout=timeout,
        )

    async def _discover_pending(
        self,
        pending_sensors,
        loop,
        register_listeners_with_sensor,
        emit_to_client,
        timeout,
    ):
        if not pending_sensors:
            return []

        discovered_sensors = []
        adapter_groups = self.adapter_pool.group_sensors(pending_sensors)
        for adapter, sensors_for_adapter in adapter_groups.items():
            sensor_names = [sensor.name for sensor in sensors_for_adapter]
            print(sensor_names)
            devices = await adapter.discover_devices(sensors_for_adapter, timeout=timeout)
            matched = self._match_devices(sensors_for_adapter, devices)
            missing = self._missing_sensor_names(sensor_names, matched)
            if missing:
                emit_to_client("on_discover", {"valid": False, "missing": missing})
                return []
            for sensor, entry in zip(sensors_for_adapter, matched):
                device, _adv_data = entry[0], entry[1]
                address = getattr(device, "address", None) or getattr(device, "path", None)
                sensor.address = address
                sensor.set_transport_client(
                    adapter.create_transport_client(
                        address,
                        loop=loop,
                        disconnected_callback=self._build_disconnect_callback(sensor, emit_to_client),
                    )
                )
                register_listeners_with_sensor(sensor)
                discovered_sensors.append(sensor)

        emit_to_client("on_discover", discovered_sensors)
        return discovered_sensors

    @staticmethod
    def _build_disconnect_callback(sensor, emit_to_client):
        def handle_disconnect(_client):
            sensor.set_connection_status(ConnectionStatus.DISCONNECTED)
            emit_to_client("on_disconnected", {"address": sensor.address})

        return handle_disconnect

    @staticmethod
    def _match_devices(requested_sensors, devices):
        matches = []
        used_addresses = set()
        for requested in requested_sensors:
            name = requested if isinstance(requested, str) else requested.name
            matched = None
            for address, pair in devices.items():
                if address in used_addresses:
                    continue
                device, adv_data = pair
                local_name = getattr(adv_data, "local_name", None) or getattr(device, "name", None) or ""
                spec = {} if isinstance(requested, str) else (getattr(requested, "spec", {}) or {})
                discovery = spec.get("discovery", {}) or {}
                expected_services = {
                    str(value).strip().lower()
                    for value in discovery.get("service_uuids", []) or []
                    if value
                }
                advertised_services = {
                    str(value).strip().lower()
                    for value in getattr(adv_data, "service_uuids", ()) or ()
                    if value
                }
                prefixes = discovery.get("local_name_prefixes", []) or []
                normalized_name = str(local_name).strip().casefold()
                matched_by_identity = bool(expected_services & advertised_services) or any(
                    normalized_name.startswith(str(prefix).strip().casefold())
                    for prefix in prefixes
                    if str(prefix).strip()
                )
                if matched_by_identity or local_name == name or local_name.startswith(name):
                    matched = (device, adv_data, name)
                    used_addresses.add(address)
                    break
            if matched:
                matches.append(matched)
        return matches

    @staticmethod
    def _missing_sensor_names(names, matched_devices):
        required_counts = {}
        found_counts = {}
        for name in names:
            required_counts[name] = required_counts.get(name, 0) + 1
        for _device, _adv_data, matched_name in matched_devices:
            found_counts[matched_name] = found_counts.get(matched_name, 0) + 1
        missing = []
        for name, required in required_counts.items():
            found = found_counts.get(name, 0)
            if found < required:
                missing.append(f"{name} missing {required - found}")
        return missing
