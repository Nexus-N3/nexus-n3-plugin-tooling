"""Reduced threaded gateway client adapted from nexus-n3-core."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import queue
import threading
import time
from typing import Any, Callable

import serial

from ..ble_runtime import HarnessBLERuntimeConfig


STREAM_FRAME_MAGIC = b"\xA5\x5A"


@dataclass(frozen=True)
class StreamFrame:
    sensor_id: int
    gateway_timestamp_us: int
    payload: bytes


@dataclass(frozen=True)
class DiscoveredDevice:
    address: str
    name: str = ""
    rssi: int | None = None
    service_uuids: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SensorConnection:
    address: str
    sensor_id: int | None = None


@dataclass(frozen=True)
class GatewayAdvertisementData:
    local_name: str = ""
    service_uuids: tuple[str, ...] = ()
    rssi: int | None = None


@dataclass(frozen=True)
class GatewayBLEDevice:
    address: str
    name: str = ""
    path: str | None = None


def discovered_devices_to_discovery_map(devices: list[DiscoveredDevice]):
    discovered = {}
    for device in devices:
        address = str(device.address).strip().upper()
        discovered[address] = (
            GatewayBLEDevice(address=address, name=device.name, path=device.address),
            GatewayAdvertisementData(
                local_name=device.name,
                service_uuids=device.service_uuids,
                rssi=device.rssi,
            ),
        )
    return discovered


def json_objects_from_line(line: str):
    decoder = json.JSONDecoder()
    for index, character in enumerate(line):
        if character != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(line[index:])
            yield obj
        except json.JSONDecodeError:
            continue


class GatewaySerialClient:
    """Threaded request/response and event client for the BLE gateway."""

    def __init__(
        self,
        config: HarnessBLERuntimeConfig,
        *,
        client_name: str = "nexus_n3_plugin_harness",
        verbose: bool = False,
    ):
        self.config = config
        self.client_name = client_name
        self.verbose = verbose
        self.ser: serial.Serial | None = None
        self.buf = bytearray()
        self.running = False
        self.started = False
        self.read_thread: threading.Thread | None = None
        self.write_lock = threading.Lock()
        self.pending_requests: dict[str, queue.Queue] = {}
        self.event_handlers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self.disconnected_addresses: set[str] = set()
        self.notification_drop_count = 0
        self.gateway_transport_stats: dict[str, Any] = {}
        self.gateway_ble_rx_stats: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        if self.started:
            return
        port = self.config.gateway_serial_port
        if not port:
            raise ValueError("gateway_serial_port is required for gateway backend")
        self.ser = serial.Serial(
            port=port,
            baudrate=self.config.gateway_baudrate,
            timeout=0.1,
            write_timeout=1.0,
            dsrdtr=False,
            rtscts=False,
        )
        self.ser.setDTR(True)
        self.ser.setRTS(True)
        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True, name="gateway-read")
        self.read_thread.start()
        self.started = True
        self.reset_session(timeout_s=5.0)
        self.hello(protocol_version=self.config.gateway_protocol_version)

    def close(self) -> None:
        self.running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)
        self.read_thread = None
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        self.pending_requests.clear()
        self.buf.clear()
        self.disconnected_addresses.clear()
        self.started = False

    def request_id(self, prefix: str) -> str:
        return f"{prefix}_{int(time.time() * 1000)}"

    def register_event_handler(self, event_type: str, callback: Callable[[Any], None]) -> None:
        self.event_handlers[event_type].append(callback)

    def send(self, obj: dict[str, Any]) -> None:
        self.start()
        assert self.ser is not None
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        with self.write_lock:
            self.ser.write(line.encode("utf-8"))
            self.ser.flush()

    def hello(self, protocol_version: int = 1) -> None:
        request_id = "hello_host_tool"
        request_queue = self._register_request(request_id)
        try:
            self.send(
                {
                    "type": "hello",
                    "request_id": request_id,
                    "protocol_version": protocol_version,
                    "client": self.client_name,
                }
            )
            self._wait_for_success(request_id, request_queue, "hello_ack", timeout_s=5.0)
        finally:
            self._unregister_request(request_id)

    def reset_session(self, timeout_s: float = 5.0) -> None:
        request_id = self.request_id("reset")
        request_queue = self._register_request(request_id)
        try:
            self.send({"type": "reset_session", "request_id": request_id})
            self._wait_for_success(request_id, request_queue, "reset_session_complete", timeout_s)
        finally:
            self._unregister_request(request_id)

    def scan(
        self,
        timeout_ms: int,
        *,
        name_filter: str | None = None,
        name_prefix_filter: str | None = None,
    ) -> list[DiscoveredDevice]:
        request_id = self.request_id("scan")
        request_queue = self._register_request(request_id)
        matches: dict[str, DiscoveredDevice] = {}
        try:
            self.send({"type": "scan_start", "request_id": request_id, "timeout_ms": timeout_ms})
            deadline = time.time() + max(10.0, timeout_ms / 1000.0 + 5.0)
            while time.time() < deadline:
                msg = self._wait_for_message(request_queue, deadline)
                msg_type = msg.get("type")
                if msg_type == "scan_result" and msg.get("request_id") == request_id:
                    name = str(msg.get("name", ""))
                    if name_filter is not None and name != name_filter:
                        continue
                    if name_prefix_filter is not None and not name.startswith(name_prefix_filter):
                        continue
                    address = self._normalize_address(msg.get("address"))
                    if not address or address in matches:
                        continue
                    service_uuids = tuple(
                        str(value).lower()
                        for value in msg.get("service_uuids", [])
                        if isinstance(value, str)
                    )
                    matches[address] = DiscoveredDevice(
                        address=address,
                        name=name,
                        rssi=msg.get("rssi"),
                        service_uuids=service_uuids,
                        raw=dict(msg),
                    )
                    print("matches in ble gateway client", matches)
                    continue
                if msg_type == "scan_complete" and msg.get("request_id") == request_id:
                    return list(matches.values())
            raise TimeoutError("Timed out waiting for scan_complete")
        finally:
            self._unregister_request(request_id)

    def connect(self, addresses: list[str], timeout_s: float) -> list[SensorConnection]:
        request_id = self.request_id("connect")
        request_queue = self._register_request(request_id)
        pending = [self._normalize_address(address) for address in addresses]
        connected: list[SensorConnection] = []
        try:
            self.send({"type": "connect_addresses", "request_id": request_id, "addresses": pending})
            deadline = time.time() + timeout_s
            while time.time() < deadline and pending:
                msg = self._wait_for_message(request_queue, deadline)
                msg_type = msg.get("type")
                if msg_type == "sensor_connected":
                    address = self._normalize_address(msg.get("address"))
                    if address in pending:
                        pending.remove(address)
                        connected.append(
                            SensorConnection(
                                address=address,
                                sensor_id=msg.get("sensor_id") if isinstance(msg.get("sensor_id"), int) else None,
                            )
                        )
                    continue
                if msg_type == "sensor_disconnected":
                    address = self._normalize_address(msg.get("address"))
                    if address in pending:
                        pending.remove(address)
                    continue
                if msg_type == "error" and msg.get("request_id") == request_id:
                    raise RuntimeError(
                        f"Gateway connect failed: {msg.get('message')} ({msg.get('error_code')})"
                    )
            if pending:
                raise TimeoutError("Failed to connect: " + ", ".join(pending))
            return connected
        finally:
            self._unregister_request(request_id)

    def disconnect(
        self,
        addresses: list[str],
        timeout_s: float,
        *,
        allow_timeout: bool = False,
    ) -> list[str]:
        request_id = self.request_id("disconnect")
        request_queue = self._register_request(request_id)
        pending = [self._normalize_address(address) for address in addresses]
        disconnected: list[str] = []
        try:
            self.send({"type": "disconnect_addresses", "request_id": request_id, "addresses": pending})
            deadline = time.time() + timeout_s
            while time.time() < deadline and pending:
                msg = self._wait_for_message(request_queue, deadline)
                msg_type = msg.get("type")
                if msg_type == "sensor_disconnected":
                    address = self._normalize_address(msg.get("address"))
                    if address in pending:
                        pending.remove(address)
                        disconnected.append(address)
                    continue
                if msg_type == "error" and msg.get("request_id") == request_id:
                    raise RuntimeError(
                        f"Gateway disconnect failed: {msg.get('message')} ({msg.get('error_code')})"
                    )
            if pending and not allow_timeout:
                raise TimeoutError("Failed to disconnect: " + ", ".join(pending))
            return disconnected
        finally:
            self._unregister_request(request_id)

    def subscribe_with_retry(
        self,
        address: str,
        characteristic_uuid: str,
        timeout_s: float,
        *,
        binary_notifications: bool = False,
        indicate: bool = False,
        attempts: int = 2,
        retry_delay_s: float = 0.3,
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, max(attempts, 1) + 1):
            try:
                self.subscribe(
                    address,
                    characteristic_uuid,
                    timeout_s,
                    binary_notifications=binary_notifications,
                    indicate=indicate,
                )
                return
            except Exception as exc:
                last_exc = exc
                if attempt < max(attempts, 1):
                    time.sleep(retry_delay_s)
        raise RuntimeError(f"subscribe failed address={address} after retries: {last_exc}")

    def subscribe(
        self,
        address: str,
        characteristic_uuid: str,
        timeout_s: float,
        *,
        binary_notifications: bool = False,
        indicate: bool = False,
    ) -> None:
        request_id = self.request_id("subscribe")
        request_queue = self._register_request(request_id)
        try:
            self.send(
                {
                    "type": "subscribe",
                    "request_id": request_id,
                    "address": address,
                    "characteristic_uuid": characteristic_uuid,
                    "binary_notifications": binary_notifications,
                    "indicate": indicate,
                }
            )
            self._wait_for_success(request_id, request_queue, "subscribe_complete", timeout_s)
        finally:
            self._unregister_request(request_id)

    def unsubscribe(
        self,
        address: str,
        characteristic_uuid: str,
        timeout_s: float,
    ) -> None:
        request_id = self.request_id("unsubscribe")
        request_queue = self._register_request(request_id)
        try:
            self.send(
                {
                    "type": "unsubscribe",
                    "request_id": request_id,
                    "address": address,
                    "characteristic_uuid": characteristic_uuid,
                }
            )
            self._wait_for_success(
                request_id,
                request_queue,
                "unsubscribe_complete",
                timeout_s,
            )
        finally:
            self._unregister_request(request_id)

    def write_gatt(
        self,
        address: str,
        characteristic_uuid: str,
        payload_hex: str,
        timeout_s: float,
        *,
        without_response: bool = False,
    ):
        request_id = self.request_id("write")
        request_queue = self._register_request(request_id)
        try:
            self.send(
                {
                    "type": "gatt_write",
                    "request_id": request_id,
                    "address": address,
                    "characteristic_uuid": characteristic_uuid,
                    "payload_hex": payload_hex,
                    "without_response": without_response,
                }
            )
            self._wait_for_success(request_id, request_queue, "write_complete", timeout_s)
            return time.monotonic()
        finally:
            self._unregister_request(request_id)

    def read_gatt(self, address: str, characteristic_uuid: str, timeout_s: float):
        request_id = self.request_id("read")
        request_queue = self._register_request(request_id)
        try:
            self.send(
                {
                    "type": "gatt_read",
                    "request_id": request_id,
                    "address": address,
                    "characteristic_uuid": characteristic_uuid,
                }
            )
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                msg = self._wait_for_message(request_queue, deadline)
                if msg.get("type") == "read_complete" and msg.get("request_id") == request_id:
                    return bytes.fromhex(str(msg.get("payload_hex", "")))
                if msg.get("type") == "error" and msg.get("request_id") == request_id:
                    raise RuntimeError(
                        f"Gateway read failed: {msg.get('message')} ({msg.get('error_code')})"
                    )
            raise TimeoutError(f"Timed out waiting for read_complete address={address}")
        finally:
            self._unregister_request(request_id)

    def _register_request(self, request_id: str):
        request_queue = queue.Queue()
        self.pending_requests[request_id] = request_queue
        return request_queue

    def _unregister_request(self, request_id: str) -> None:
        self.pending_requests.pop(request_id, None)

    def _wait_for_success(self, request_id: str, request_queue, success_type: str, timeout_s: float) -> dict[str, Any]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msg = self._wait_for_message(request_queue, deadline)
            if msg.get("type") == success_type and msg.get("request_id") == request_id:
                return msg
            if msg.get("type") == "error" and msg.get("request_id") == request_id:
                raise RuntimeError(
                    f"Gateway request failed: {msg.get('message')} ({msg.get('error_code')})"
                )
        raise TimeoutError(f"Timed out waiting for {success_type}")

    @staticmethod
    def _wait_for_message(request_queue, deadline: float) -> dict[str, Any]:
        timeout_s = max(0.1, deadline - time.time())
        return request_queue.get(timeout=timeout_s)

    def _read_loop(self) -> None:
        assert self.ser is not None
        while self.running:
            try:
                chunk = self.ser.read(256)
                if chunk:
                    self.buf.extend(chunk)
                while True:
                    item = self._extract_item()
                    if item is None:
                        break
                    item_type, payload = item
                    if item_type == "json":
                        self._observe_json(payload)
                        self._route_json(payload)
                    else:
                        self._dispatch_event("stream_frame", payload)
            except Exception:
                time.sleep(0.1)

    def _route_json(self, msg: dict[str, Any]) -> None:
        request_id = msg.get("request_id")
        if request_id and request_id in self.pending_requests:
            self.pending_requests[request_id].put(msg)
        self._dispatch_event(str(msg.get("type", "")), msg)

    def _dispatch_event(self, event_type: str, payload: Any) -> None:
        for callback in list(self.event_handlers.get(event_type, [])):
            try:
                callback(payload)
            except Exception:
                pass

    def _extract_item(self):
        while self.buf:
            if self.buf[0] == ord("{"):
                newline_index = self.buf.find(b"\n")
                if newline_index < 0:
                    return None
                line = self.buf[:newline_index].decode("utf-8", errors="replace").strip()
                del self.buf[: newline_index + 1]
                if not line:
                    continue
                for msg in json_objects_from_line(line):
                    return ("json", msg)
                continue

            if len(self.buf) >= 2 and self.buf[:2] == STREAM_FRAME_MAGIC:
                if len(self.buf) < 14:
                    return None
                version = self.buf[2]
                if version != 0x01:
                    del self.buf[:1]
                    continue
                sensor_id = self.buf[3]
                gateway_timestamp_us = int.from_bytes(self.buf[4:12], "little")
                payload_len = self.buf[12]
                total_len = 13 + payload_len + 1
                if len(self.buf) < total_len:
                    return None
                payload = bytes(self.buf[13 : 13 + payload_len])
                checksum = self.buf[13 + payload_len]
                computed = sum(self.buf[2 : 13 + payload_len]) & 0xFF
                if checksum != computed:
                    del self.buf[:1]
                    continue
                del self.buf[:total_len]
                return ("stream_frame", StreamFrame(sensor_id, gateway_timestamp_us, payload))

            next_json = self.buf.find(b"{")
            next_frame = self.buf.find(STREAM_FRAME_MAGIC)
            candidates = [index for index in (next_json, next_frame) if index >= 0]
            if not candidates:
                self.buf.clear()
                return None
            drop_len = min(candidates)
            if drop_len > 0:
                del self.buf[:drop_len]

        return None

    def _observe_json(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "sensor_disconnected":
            address = msg.get("address")
            if address:
                self.disconnected_addresses.add(self._normalize_address(address))
            return
        if msg_type == "notification_drops":
            value = msg.get("drop_count")
            if isinstance(value, int):
                self.notification_drop_count = value
            return
        if msg_type == "gateway_transport_stats":
            self.gateway_transport_stats = dict(msg)
            return
        if msg_type == "ble_notification_rx_stats":
            address = self._normalize_address(str(msg.get("address", "")))
            if address:
                normalized = dict(msg)
                normalized["address"] = address
                self.gateway_ble_rx_stats[address] = normalized

    @staticmethod
    def _normalize_address(address: str | None) -> str:
        return "" if not address else address.strip().upper()
