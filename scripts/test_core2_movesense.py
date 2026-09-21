#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace

from nexus_n3_plugin_cli.sensor_harness.config import HarnessConfig
from nexus_n3_plugin_cli.sensor_harness.plugin_loader import (
    load_plugin_manifest,
    load_sensor_class,
    load_sensor_target,
)
from nexus_n3_plugin_cli.sensor_harness.runner import CsvCaptureWriter
from nexus_n3_plugin_cli.sensor_harness.sensor_manager import (
    HarnessSensorManager,
)


class StubSensorType:
    def __init__(self, local_name: str):
        self.local_name = local_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live CORE 2 + Movesense plugin integration test."
    )

    parser.add_argument(
        "--core-plugin-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--movesense-plugin-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--adapter-backend",
        default="bleak",
        choices=[
            "bleak",
            "nexus_ble_gateway",
        ],
    )

    parser.add_argument(
        "--gateway-serial-port",
        default=None,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("plugin-test-core2-movesense"),
    )

    return parser


async def run(args: argparse.Namespace) -> int:
    core_root = args.core_plugin_root.resolve()
    movesense_root = args.movesense_plugin_root.resolve()

    core_manifest = load_plugin_manifest(core_root)
    movesense_manifest = load_plugin_manifest(movesense_root)

    core_cls = load_sensor_class(core_root)
    movesense_cls = load_sensor_class(movesense_root)

    # HarnessSensorManager currently requires one target for metadata /
    # summary purposes. Runtime discovery and streaming operate from each
    # actual sensor instance, so CORE is sufficient as the nominal target.
    target = load_sensor_target(core_root)

    config = HarnessConfig(
        plugin_root=core_root,
        adapter_backend=args.adapter_backend,
        sensor_count=2,
        duration_seconds=args.duration,
        identify=False,
        fail_on_no_data=True,
        location="CHEST",
        gateway_serial_port=args.gateway_serial_port,
        attributes={},
    )

    manager = HarnessSensorManager(
        config=config,
        target=target,
    )

    core = core_cls(
        StubSensorType(
            core_cls.sensor_type.local_name
        )
    )

    movesense = movesense_cls(
        StubSensorType(
            movesense_cls.sensor_type.local_name
        )
    )

    # We only need Movesense HR for this test.
    # Avoid producing the 200 Hz ECG stream unnecessarily.
    if "STREAMS" in movesense.attributes:
        movesense.attributes["STREAMS"] = ["HR"]

    output_dir = args.output_dir.resolve()
    capture = CsvCaptureWriter(output_dir)

    loop = asyncio.get_running_loop()
    routing_queue: asyncio.Queue = asyncio.Queue()

    routing_enabled = True

    def on_data(payload):
        """
        Capture all sensor output and queue Movesense HR samples for CORE.

        Notification callbacks may originate outside the asyncio task that
        owns this test, so queue insertion is scheduled thread-safely.
        """

        capture.write_event(
            "on_data",
            payload,
        )

        if not routing_enabled:
            return

        sample_type = str(
            getattr(payload, "sample_type", "") or ""
        ).strip().lower()

        if sample_type != "hr":
            return

        loop.call_soon_threadsafe(
            routing_queue.put_nowait,
            payload,
        )

    def on_error(payload):
        capture.write_event(
            "on_error",
            payload,
        )

        print(
            "PLUGIN ERROR:",
            payload,
        )

    manager.register_listener(
        "on_data",
        on_data,
    )

    manager.register_listener(
        "on_error",
        on_error,
    )

    manager.register_listener(
        "on_battery",
        lambda payload: print(
            "BATTERY:",
            payload,
        ),
    )

    manager.init_sensor_manager(
        [
            # CORE first is deliberate. Its 2101 measurement stream should
            # be established before Movesense begins producing HR.
            core,
            movesense,
        ]
    )

    async def route_hr():
        """
        Forward Movesense HR samples into CORE consume_input().

        This mimics the routing envelope Nexus N3 Core will ultimately use,
        without involving Nexus N3 Core itself.
        """

        while True:
            payload = await routing_queue.get()

            heart_rate = getattr(
                payload,
                "heart_rate",
                None,
            )

            envelope = SimpleNamespace(
                source_plugin_id=movesense_manifest[
                    "plugin_id"
                ],
                source_sensor_name=movesense.name,
                source_address=movesense.address,
                output_name="hr",
                schema="hr",
                payload=payload,
            )

            try:
                accepted = await core.consume_input(
                    movesense_manifest["plugin_id"],
                    envelope,
                )

                print(
                    "HR ROUTE:",
                    f"bpm={heart_rate}",
                    f"accepted={accepted}",
                )

            except Exception as exc:
                # External HR is optional. A routing/control-point failure
                # must not terminate either sensor stream.
                print(
                    "HR ROUTE ERROR:",
                    type(exc).__name__,
                    exc,
                )

            finally:
                routing_queue.task_done()

    routing_task = asyncio.create_task(
        route_hr()
    )

    try:
        print("")
        print("Discovering CORE 2 + Movesense...")

        discovered = await manager.dispatch(
            {
                "message": "discover",
                "timeout": 8.0,
            }
        )

        if len(discovered) != 2:
            print(
                "Expected two sensors, discovered:",
                [
                    (
                        getattr(sensor, "name", None),
                        getattr(sensor, "address", None),
                    )
                    for sensor in discovered
                ],
            )
            return 1

        print(
            "Discovered:",
            [
                (
                    sensor.name,
                    sensor.address,
                )
                for sensor in discovered
            ],
        )

        connected = await manager.dispatch(
            {
                "message": "connect_all",
            }
        )

        if len(connected) != 2:
            print(
                "Failed to connect both sensors."
            )
            return 1

        print(
            "Connected:",
            [
                (
                    sensor.name,
                    sensor.address,
                )
                for sensor in connected
            ],
        )

        print("")
        print("Starting streams...")

        await manager.dispatch(
            {
                "message": "start_all",
            }
        )

        print(
            f"Streaming for {args.duration:.1f}s..."
        )

        await asyncio.sleep(
            args.duration
        )

        # Stop forwarding new HR observations first. CORE's stop_stream()
        # will then disable its currently active external HR input itself.
        routing_enabled = False

        print("")
        print("Stopping streams...")

        await manager.dispatch(
            {
                "message": "stop_all",
            }
        )

    finally:
        routing_enabled = False

        routing_task.cancel()

        try:
            await routing_task
        except asyncio.CancelledError:
            pass

        try:
            await manager.dispatch(
                {
                    "message": "disconnect_all",
                }
            )
        finally:
            await manager.shutdown()
            capture.close()

    print("")
    print("Test complete.")
    print(f"Output: {output_dir}")

    return 0


def main():
    args = build_parser().parse_args()

    raise SystemExit(
        asyncio.run(
            run(args)
        )
    )


if __name__ == "__main__":
    main()