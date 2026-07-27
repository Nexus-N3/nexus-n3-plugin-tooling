"""Command line entry point for Nexus N3 plugin tooling."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from nexus_n3_plugin_cli.scaffold.algorithm import scaffold_algorithm_plugin
from nexus_n3_plugin_cli.scaffold.sensor import scaffold_sensor_plugin
from nexus_n3_plugin_cli.build import DependencyTarget, build_plugin_bundle
from nexus_n3_plugin_cli.install import install_bundle
from nexus_n3_plugin_cli.plugin_env import (
    plugin_venv_is_prepared,
    prepare_plugin_venv,
    resolve_plugin_python,
    resolve_plugin_site_packages,
    resolve_venv_python,
    resolve_venv_site_packages,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(prog="nx3-plugin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Scaffold a new plugin")
    init_subparsers = init_parser.add_subparsers(dest="plugin_type", required=True)

    sensor_parser = init_subparsers.add_parser("sensor", help="Scaffold a sensor plugin")
    sensor_parser.add_argument("plugin_id", help="Plugin identifier, e.g. movella-dot")
    sensor_parser.add_argument(
        "--display-name",
        help="Human-readable sensor name",
    )
    sensor_parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where the plugin repository should be created",
    )
    sensor_parser.add_argument(
        "--adapter",
        default="BLE",
        help="Sensor adapter type to place in the generated spec",
    )
    sensor_parser.add_argument(
        "--sample-type",
        default="generic",
        help="Generated sample type identifier",
    )
    sensor_parser.add_argument(
        "--package-name",
        help="Override generated Python package name",
    )
    sensor_parser.add_argument(
        "--manufacturer-id",
        type=int,
        default=9000,
        help="Manufacturer id used in the generated SensorType",
    )
    sensor_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into an existing empty target directory",
    )

    algorithm_parser = init_subparsers.add_parser("algorithm", help="Scaffold an algorithm plugin")
    algorithm_parser.add_argument("plugin_id", help="Plugin identifier, e.g. generic-data-summary")
    algorithm_parser.add_argument(
        "--display-name",
        help="Human-readable algorithm name",
    )
    algorithm_parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where the plugin repository should be created",
    )
    algorithm_parser.add_argument(
        "--package-name",
        help="Override generated Python package name",
    )
    algorithm_parser.add_argument(
        "--with-intermediate",
        action="store_true",
        help="Enable the intermediate schedule and generate an example implementation",
    )
    algorithm_parser.add_argument(
        "--with-consolidation",
        action="store_true",
        help="Enable the consolidation schedule and generate an example implementation",
    )
    algorithm_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into an existing empty target directory",
    )

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Create or refresh an existing plugin's development environment",
    )
    prepare_parser.add_argument(
        "--plugin-root",
        default=".",
        help="Existing plugin source repository to prepare",
    )
    prepare_parser.add_argument(
        "--sdk-root",
        help="Optional path to the local nexus-n3-plugin-sdk source",
    )

    build_parser = subparsers.add_parser("build", help="Build a .rsnxplugin bundle for nexus-n3-core")
    build_source_group = build_parser.add_mutually_exclusive_group()
    build_source_group.add_argument(
        "--plugin-root",
        help="Plugin source repository to build",
    )
    build_source_group.add_argument(
        "--catalog-root",
        help="Catalog repository whose sensor and algorithm plugins should all be built",
    )
    build_parser.add_argument(
        "--output-dir",
        default="plugin-build",
        help="Bundle output directory; catalog builds create sensors/ and algorithms/ below it",
    )
    build_parser.add_argument(
        "--sdk-root",
        help="Optional path to the local nexus-n3-plugin-sdk repo to include as a wheel artifact",
    )
    build_parser.add_argument(
        "--no-sdk",
        action="store_true",
        help="Do not auto-build/include the local nexus-n3-plugin-sdk wheel",
    )
    build_parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Additional wheel artifact to include in the .rsnxplugin bundle",
    )
    build_parser.add_argument(
        "--wheelhouse",
        action="append",
        default=[],
        help="Additional local wheelhouse directory used to resolve target dependency wheels",
    )
    build_parser.add_argument(
        "--include-dependencies",
        action="store_true",
        help="Deprecated compatibility flag. Dependency-complete bundles are now the default.",
    )
    build_parser.add_argument(
        "--slim",
        action="store_true",
        help="Build a slim bundle without resolving third-party dependency wheels",
    )
    build_parser.add_argument(
        "--target",
        choices=["rpi", "jetson", "win", "local"],
        default="local",
        help="Bundle target preset used for naming, manifest metadata, and dependency wheel resolution",
    )
    build_parser.add_argument(
        "--target-platform",
        help="Optional pip download target platform, e.g. manylinux2014_aarch64",
    )
    build_parser.add_argument(
        "--target-python-version",
        help="Optional pip download target Python version, e.g. 3.12",
    )
    build_parser.add_argument(
        "--target-implementation",
        help="Optional pip download target implementation, e.g. cp",
    )
    build_parser.add_argument(
        "--target-abi",
        help="Optional pip download target ABI, e.g. cp312",
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Deprecated compatibility flag. Existing bundles of the same name/version are overwritten automatically.",
    )

    install_parser = subparsers.add_parser("install", help="Install a built .rsnxplugin bundle into nexus-n3-core")
    install_parser.add_argument(
        "--bundle-path",
        required=True,
        help="Path to the built .rsnxplugin bundle to install",
    )
    install_parser.add_argument(
        "--no-activate",
        action="store_true",
        help="Install the bundle without activating it as the current plugin version",
    )

    system_test_parser = subparsers.add_parser(
        "system-test",
        help="Run an interactive nexus-n3-core integration test against installed sensor and algorithm plugins",
    )
    system_test_parser.add_argument(
        "--host",
        default="localhost",
        help="Gateway host to test against, for example 192.168.50.1",
    )
    system_test_parser.add_argument(
        "--cmd-port",
        type=int,
        default=5555,
        help="Command socket port for the target gateway",
    )
    system_test_parser.add_argument(
        "--evt-port",
        type=int,
        default=5556,
        help="Event socket port for the target gateway",
    )

    test_parser = subparsers.add_parser("test", help="Run focused plugin development harnesses")
    test_subparsers = test_parser.add_subparsers(dest="test_type", required=True)
    sensor_test_parser = test_subparsers.add_parser("sensor", help="Run the sensor plugin harness")
    sensor_test_parser.add_argument(
        "--plugin-root",
        default=".",
        help="Sensor plugin source repository to load from source",
    )
    sensor_test_parser.add_argument("--adapter-backend", default="auto")
    sensor_test_parser.add_argument("--sensor-count", type=int, default=1)
    sensor_test_parser.add_argument("--duration", type=float, default=15.0)
    sensor_test_parser.add_argument("--identify", action="store_true")
    sensor_test_parser.add_argument("--location")
    sensor_test_parser.add_argument("--gateway-serial-port")
    sensor_test_parser.add_argument("--gateway-baudrate", type=int, default=1_000_000)
    sensor_test_parser.add_argument("--gateway-protocol-version", type=int, default=1)
    sensor_test_parser.add_argument(
        "--output-dir",
        help="Optional capture directory. Defaults to <plugin-root>/plugin-test/.",
    )
    sensor_test_parser.add_argument(
        "--attribute",
        action="append",
        default=[],
        help="Override a sensor attribute as KEY=VALUE. VALUE may be JSON.",
    )
    sensor_test_parser.add_argument("--fail-on-no-data", action="store_true")
    sensor_test_parser.add_argument(
        "--refresh-env",
        action="store_true",
        help="Reinstall the SDK and plugin into the plugin .venv before running the harness.",
    )
    algorithm_test_parser = test_subparsers.add_parser("algorithm", help="Run the algorithm plugin harness")
    algorithm_test_parser.add_argument(
        "--plugin-root",
        default=".",
        help="Algorithm plugin source repository to load from source",
    )
    algorithm_sensor_group = algorithm_test_parser.add_mutually_exclusive_group(required=True)
    algorithm_sensor_group.add_argument(
        "--sensor-plugin-root",
        help="Sensor plugin source repository used to feed samples into the algorithm",
    )
    algorithm_sensor_group.add_argument(
        "--sensor-bundle-path",
        help="Path to a built sensor .rsnxplugin bundle used to feed samples into the algorithm",
    )
    algorithm_test_parser.add_argument("--adapter-backend", default="auto")
    algorithm_test_parser.add_argument("--sensor-count", type=int, default=1)
    algorithm_test_parser.add_argument("--duration", type=float, default=15.0)
    algorithm_test_parser.add_argument("--identify", action="store_true")
    algorithm_test_parser.add_argument("--location")
    algorithm_test_parser.add_argument("--gateway-serial-port")
    algorithm_test_parser.add_argument("--gateway-baudrate", type=int, default=1_000_000)
    algorithm_test_parser.add_argument("--gateway-protocol-version", type=int, default=1)
    algorithm_test_parser.add_argument("--subject-id", default="harness-subject-1")
    algorithm_test_parser.add_argument(
        "--output-dir",
        help="Optional capture directory. Defaults to <algorithm-plugin-root>/plugin-test/.",
    )
    algorithm_test_parser.add_argument(
        "--attribute",
        action="append",
        default=[],
        help="Override a sensor attribute as KEY=VALUE. VALUE may be JSON.",
    )
    algorithm_test_parser.add_argument(
        "--algorithm-input",
        action="append",
        default=[],
        help="Override an algorithm input parameter as KEY=VALUE. VALUE may be JSON.",
    )
    algorithm_test_parser.add_argument("--fail-on-no-results", action="store_true")
    algorithm_test_parser.add_argument(
        "--refresh-env",
        action="store_true",
        help="Reinstall the SDK and source plugins into their .venv environments before running the harness.",
    )
    algorithm_bundle_test_parser = test_subparsers.add_parser("algorithm-bundle", help="Run the algorithm harness against a built .rsnxplugin bundle")
    algorithm_bundle_test_parser.add_argument("--bundle-path", required=True, help="Path to the built algorithm .rsnxplugin bundle")
    algorithm_bundle_test_parser.add_argument(
        "--plugin-root",
        help="Optional source algorithm repository. Defaults to an inferred plugin repo when using the standard nexus-n3-plugin-catalog layout.",
    )
    algorithm_bundle_sensor_group = algorithm_bundle_test_parser.add_mutually_exclusive_group(required=True)
    algorithm_bundle_sensor_group.add_argument(
        "--sensor-plugin-root",
        help="Sensor plugin source repository used to feed samples into the algorithm",
    )
    algorithm_bundle_sensor_group.add_argument(
        "--sensor-bundle-path",
        help="Path to a built sensor .rsnxplugin bundle used to feed samples into the algorithm",
    )
    algorithm_bundle_test_parser.add_argument("--adapter-backend", default="auto")
    algorithm_bundle_test_parser.add_argument("--sensor-count", type=int, default=1)
    algorithm_bundle_test_parser.add_argument("--duration", type=float, default=15.0)
    algorithm_bundle_test_parser.add_argument("--identify", action="store_true")
    algorithm_bundle_test_parser.add_argument("--location")
    algorithm_bundle_test_parser.add_argument("--gateway-serial-port")
    algorithm_bundle_test_parser.add_argument("--gateway-baudrate", type=int, default=1_000_000)
    algorithm_bundle_test_parser.add_argument("--gateway-protocol-version", type=int, default=1)
    algorithm_bundle_test_parser.add_argument("--subject-id", default="harness-subject-1")
    algorithm_bundle_test_parser.add_argument(
        "--output-dir",
        help="Optional capture directory. Defaults to <algorithm-plugin-root>/plugin-test/.",
    )
    algorithm_bundle_test_parser.add_argument(
        "--attribute",
        action="append",
        default=[],
        help="Override a sensor attribute as KEY=VALUE. VALUE may be JSON.",
    )
    algorithm_bundle_test_parser.add_argument(
        "--algorithm-input",
        action="append",
        default=[],
        help="Override an algorithm input parameter as KEY=VALUE. VALUE may be JSON.",
    )
    algorithm_bundle_test_parser.add_argument("--fail-on-no-results", action="store_true")
    algorithm_bundle_test_parser.add_argument(
        "--refresh-env",
        action="store_true",
        help="Reinstall the SDK and source sensor plugin into its .venv environment before running the harness.",
    )
    bundle_test_parser = test_subparsers.add_parser("sensor-bundle", help="Run the harness against a built .rsnxplugin bundle")
    bundle_test_parser.add_argument("--bundle-path", required=True, help="Path to the built .rsnxplugin bundle")
    bundle_test_parser.add_argument(
        "--plugin-root",
        help="Optional source plugin repository. Defaults to an inferred plugin repo when using the standard nexus-n3-plugin-catalog layout.",
    )
    bundle_test_parser.add_argument("--adapter-backend", default="auto")
    bundle_test_parser.add_argument("--sensor-count", type=int, default=1)
    bundle_test_parser.add_argument("--duration", type=float, default=15.0)
    bundle_test_parser.add_argument("--identify", action="store_true")
    bundle_test_parser.add_argument("--location")
    bundle_test_parser.add_argument("--gateway-serial-port")
    bundle_test_parser.add_argument("--gateway-baudrate", type=int, default=1_000_000)
    bundle_test_parser.add_argument("--gateway-protocol-version", type=int, default=1)
    bundle_test_parser.add_argument(
        "--output-dir",
        help="Optional capture directory. Defaults to <plugin-root>/plugin-test/.",
    )
    bundle_test_parser.add_argument(
        "--attribute",
        action="append",
        default=[],
        help="Override a sensor attribute as KEY=VALUE. VALUE may be JSON.",
    )
    bundle_test_parser.add_argument("--fail-on-no-data", action="store_true")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    try:
        args = parser.parse_args()

        if args.command == "init" and args.plugin_type == "sensor":
            print("Creating sensor plugin", args.plugin_id)
            plugin_root = scaffold_sensor_plugin(
                plugin_id=args.plugin_id,
                display_name=args.display_name,
                output_dir=Path(args.output_dir),
                adapter=args.adapter,
                sample_type=args.sample_type,
                package_name=args.package_name,
                manufacturer_id=args.manufacturer_id,
                force=args.force,
            )
            prepare_plugin_venv(plugin_root)
            return 0

        if args.command == "init" and args.plugin_type == "algorithm":
            print("Creating alogrithm plugin", args.plugin_id)
            plugin_root = scaffold_algorithm_plugin(
                plugin_id=args.plugin_id,
                display_name=args.display_name,
                output_dir=Path(args.output_dir),
                package_name=args.package_name,
                include_intermediate=args.with_intermediate,
                include_consolidation=args.with_consolidation,
                force=args.force,
            )
            prepare_plugin_venv(plugin_root)
            return 0

        if args.command == "prepare":
            prepare_plugin_venv(
                Path(args.plugin_root),
                sdk_root=Path(args.sdk_root) if args.sdk_root else None,
            )
            return 0

        if args.command == "build":
            dependency_target = DependencyTarget.from_preset(args.target)
            if args.target_platform:
                dependency_target = DependencyTarget(
                    target_id=dependency_target.target_id,
                    platform=args.target_platform,
                    python_version=args.target_python_version or dependency_target.python_version,
                    implementation=args.target_implementation or dependency_target.implementation,
                    abi=args.target_abi or dependency_target.abi,
                )
            elif any([args.target_python_version, args.target_implementation, args.target_abi]):
                dependency_target = DependencyTarget(
                    target_id=dependency_target.target_id,
                    platform=dependency_target.platform,
                    python_version=args.target_python_version or dependency_target.python_version,
                    implementation=args.target_implementation or dependency_target.implementation,
                    abi=args.target_abi or dependency_target.abi,
                )
            plugin_roots = (
                _discover_catalog_plugins(Path(args.catalog_root))
                if args.catalog_root
                else [(None, Path(args.plugin_root or "."))]
            )
            for family, plugin_root in plugin_roots:
                plugin_root = plugin_root.resolve()
                if not plugin_venv_is_prepared(plugin_root):
                    print(f"Preparing plugin environment: {plugin_root}")
                    prepare_plugin_venv(
                        plugin_root,
                        sdk_root=Path(args.sdk_root) if args.sdk_root else None,
                    )
                plugin_output_dir = (
                    Path(args.output_dir) / family if family is not None else Path(args.output_dir)
                )
                bundle_path = build_plugin_bundle(
                    plugin_root=plugin_root,
                    output_dir=plugin_output_dir,
                    force=args.force,
                    sdk_root=Path(args.sdk_root) if args.sdk_root else None,
                    include_sdk=not args.no_sdk,
                    include_dependencies=not args.slim,
                    dependency_target=dependency_target,
                    extra_artifacts=[Path(path) for path in args.artifact],
                    dependency_wheelhouses=[Path(path) for path in args.wheelhouse],
                )
                print(f"Built {bundle_path}")
            return 0

        if args.command == "install":
            return install_bundle(
                bundle_path=Path(args.bundle_path),
                activate=not args.no_activate,
            )

        if args.command == "system-test":
            from nexus_n3_plugin_cli.system_test.runner import run_system_test
            return run_system_test(
                start_dir=Path.cwd(),
                host=args.host,
                cmd_port=args.cmd_port,
                evt_port=args.evt_port,
            )

        if args.command == "test" and args.test_type == "sensor":
            plugin_root = Path(args.plugin_root).resolve()
            if args.refresh_env:
                prepare_plugin_venv(plugin_root)
            else:
                resolve_plugin_python(plugin_root)
            plugin_site_packages = resolve_plugin_site_packages(plugin_root)
            completed = _run_sensor_harness(
                plugin_root=plugin_root,
                plugin_site_packages=plugin_site_packages,
                adapter_backend=args.adapter_backend,
                sensor_count=args.sensor_count,
                duration=args.duration,
                identify=args.identify,
                location=args.location,
                gateway_serial_port=args.gateway_serial_port,
                gateway_baudrate=args.gateway_baudrate,
                gateway_protocol_version=args.gateway_protocol_version,
                output_dir=args.output_dir,
                attributes=args.attribute,
                fail_on_no_data=args.fail_on_no_data,
            )
            return completed.returncode

        if args.command == "test" and args.test_type == "algorithm":
            plugin_root = Path(args.plugin_root).resolve()
            sensor_plugin_root, sensor_site_packages, _cleanup = _resolve_sensor_harness_target(
                sensor_plugin_root=args.sensor_plugin_root,
                sensor_bundle_path=args.sensor_bundle_path,
                refresh_env=args.refresh_env,
            )
            if args.refresh_env:
                prepare_plugin_venv(plugin_root)
            else:
                resolve_plugin_python(plugin_root)
            algorithm_site_packages = resolve_plugin_site_packages(plugin_root)
            try:
                completed = _run_algorithm_harness(
                    algorithm_plugin_root=plugin_root,
                    algorithm_site_packages=algorithm_site_packages,
                    sensor_plugin_root=sensor_plugin_root,
                    sensor_site_packages=sensor_site_packages,
                    adapter_backend=args.adapter_backend,
                    sensor_count=args.sensor_count,
                    duration=args.duration,
                    identify=args.identify,
                    location=args.location,
                    gateway_serial_port=args.gateway_serial_port,
                    gateway_baudrate=args.gateway_baudrate,
                    gateway_protocol_version=args.gateway_protocol_version,
                    subject_id=args.subject_id,
                    output_dir=args.output_dir,
                    sensor_attributes=args.attribute,
                    algorithm_inputs=args.algorithm_input,
                    fail_on_no_results=args.fail_on_no_results,
                )
                return completed.returncode
            finally:
                _cleanup()

        if args.command == "test" and args.test_type == "algorithm-bundle":
            bundle_path = Path(args.bundle_path).resolve()
            with tempfile.TemporaryDirectory(prefix="nexusn3-algorithm-bundle-") as temp_dir:
                temp_root = Path(temp_dir)
                extracted_root = temp_root / "bundle"
                extracted_root.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(bundle_path, "r") as archive:
                    archive.extractall(extracted_root)

                bundle_manifest = _read_bundle_manifest(extracted_root)
                plugin_id = str(bundle_manifest["plugin_id"])
                plugin_type = str(bundle_manifest["plugin_type"])
                test_env_root = temp_root / "env"
                algorithm_site_packages = _prepare_bundle_test_env(extracted_root, test_env_root)
                algorithm_plugin_root = (
                    Path(args.plugin_root).resolve()
                    if args.plugin_root
                    else _infer_bundle_plugin_root(bundle_path, plugin_id, plugin_type)
                )
                sensor_plugin_root, sensor_site_packages, _cleanup = _resolve_sensor_harness_target(
                    sensor_plugin_root=args.sensor_plugin_root,
                    sensor_bundle_path=args.sensor_bundle_path,
                    refresh_env=args.refresh_env,
                )
                output_dir = args.output_dir or str(algorithm_plugin_root / "plugin-test")
                try:
                    completed = _run_algorithm_harness(
                        algorithm_plugin_root=extracted_root,
                        algorithm_site_packages=algorithm_site_packages,
                        sensor_plugin_root=sensor_plugin_root,
                        sensor_site_packages=sensor_site_packages,
                        adapter_backend=args.adapter_backend,
                        sensor_count=args.sensor_count,
                        duration=args.duration,
                        identify=args.identify,
                        location=args.location,
                        gateway_serial_port=args.gateway_serial_port,
                        gateway_baudrate=args.gateway_baudrate,
                        gateway_protocol_version=args.gateway_protocol_version,
                        subject_id=args.subject_id,
                        output_dir=output_dir,
                        sensor_attributes=args.attribute,
                        algorithm_inputs=args.algorithm_input,
                        fail_on_no_results=args.fail_on_no_results,
                    )
                    return completed.returncode
                finally:
                    _cleanup()

        if args.command == "test" and args.test_type == "sensor-bundle":
            bundle_path = Path(args.bundle_path).resolve()
            with tempfile.TemporaryDirectory(prefix="nexusn3-sensor-bundle-") as temp_dir:
                temp_root = Path(temp_dir)
                extracted_root = temp_root / "bundle"
                extracted_root.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(bundle_path, "r") as archive:
                    archive.extractall(extracted_root)

                bundle_manifest = _read_bundle_manifest(extracted_root)
                plugin_id = str(bundle_manifest["plugin_id"])
                plugin_type = str(bundle_manifest["plugin_type"])
                test_env_root = temp_root / "env"
                bundle_site_packages = _prepare_bundle_test_env(extracted_root, test_env_root)
                plugin_root = (
                    Path(args.plugin_root).resolve()
                    if args.plugin_root
                    else _infer_bundle_plugin_root(bundle_path, plugin_id, plugin_type)
                )
                output_dir = args.output_dir or str(plugin_root / "plugin-test")
                completed = _run_sensor_harness(
                    plugin_root=extracted_root,
                    plugin_site_packages=bundle_site_packages,
                    adapter_backend=args.adapter_backend,
                    sensor_count=args.sensor_count,
                    duration=args.duration,
                    identify=args.identify,
                    location=args.location,
                    gateway_serial_port=args.gateway_serial_port,
                    gateway_baudrate=args.gateway_baudrate,
                    gateway_protocol_version=args.gateway_protocol_version,
                    output_dir=output_dir,
                    attributes=args.attribute,
                    fail_on_no_data=args.fail_on_no_data,
                )
                return completed.returncode

        parser.error("Unsupported command")
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run_sensor_harness(
    *,
    plugin_root: Path,
    plugin_site_packages: Path,
    adapter_backend: str,
    sensor_count: int,
    duration: float,
    identify: bool,
    location: str | None,
    gateway_serial_port: str | None,
    gateway_baudrate: int,
    gateway_protocol_version: int,
    output_dir: str | None,
    attributes: list[str],
    fail_on_no_data: bool,
) -> subprocess.CompletedProcess:
    tooling_root = Path(__file__).resolve().parents[4]
    cli_src = tooling_root / "packages" / "cli" / "src"
    sdk_src = tooling_root / "packages" / "sdk" / "src"
    pythonpath_entries = [str(cli_src), str(sdk_src), str(plugin_site_packages)]
    existing_pythonpath = os.environ.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    cmd = [
        sys.executable,
        "-m",
        "nexus_n3_plugin_cli.sensor_harness.cli",
        "--plugin-root",
        str(plugin_root),
        "--adapter-backend",
        adapter_backend,
        "--sensor-count",
        str(sensor_count),
        "--duration",
        str(duration),
        "--gateway-baudrate",
        str(gateway_baudrate),
        "--gateway-protocol-version",
        str(gateway_protocol_version),
    ]
    if identify:
        cmd.append("--identify")
    if location:
        cmd.extend(["--location", location])
    if gateway_serial_port:
        cmd.extend(["--gateway-serial-port", gateway_serial_port])
    if output_dir:
        cmd.extend(["--output-dir", output_dir])
    for item in attributes:
        cmd.extend(["--attribute", item])
    if fail_on_no_data:
        cmd.append("--fail-on-no-data")
    return subprocess.run(cmd, check=False, env=env)


def _run_algorithm_harness(
    *,
    algorithm_plugin_root: Path,
    algorithm_site_packages: Path,
    sensor_plugin_root: Path,
    sensor_site_packages: Path,
    adapter_backend: str,
    sensor_count: int,
    duration: float,
    identify: bool,
    location: str | None,
    gateway_serial_port: str | None,
    gateway_baudrate: int,
    gateway_protocol_version: int,
    subject_id: str,
    output_dir: str | None,
    sensor_attributes: list[str],
    algorithm_inputs: list[str],
    fail_on_no_results: bool,
) -> subprocess.CompletedProcess:
    tooling_root = Path(__file__).resolve().parents[4]
    cli_src = tooling_root / "packages" / "cli" / "src"
    sdk_src = tooling_root / "packages" / "sdk" / "src"
    pythonpath_entries = [
        str(cli_src),
        str(sdk_src),
        str(algorithm_site_packages),
        str(sensor_site_packages),
    ]
    existing_pythonpath = os.environ.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    cmd = [
        sys.executable,
        "-m",
        "nexus_n3_plugin_cli.algorithm_harness.cli",
        "--plugin-root",
        str(algorithm_plugin_root),
        "--sensor-plugin-root",
        str(sensor_plugin_root),
        "--adapter-backend",
        adapter_backend,
        "--sensor-count",
        str(sensor_count),
        "--duration",
        str(duration),
        "--gateway-baudrate",
        str(gateway_baudrate),
        "--gateway-protocol-version",
        str(gateway_protocol_version),
        "--subject-id",
        subject_id,
    ]
    if identify:
        cmd.append("--identify")
    if location:
        cmd.extend(["--location", location])
    if gateway_serial_port:
        cmd.extend(["--gateway-serial-port", gateway_serial_port])
    if output_dir:
        cmd.extend(["--output-dir", output_dir])
    for item in sensor_attributes:
        cmd.extend(["--attribute", item])
    for item in algorithm_inputs:
        cmd.extend(["--algorithm-input", item])
    if fail_on_no_results:
        cmd.append("--fail-on-no-results")
    return subprocess.run(cmd, check=False, env=env)


def _resolve_sensor_harness_target(
    *,
    sensor_plugin_root: str | None,
    sensor_bundle_path: str | None,
    refresh_env: bool,
) -> tuple[Path, Path, callable]:
    if sensor_plugin_root:
        plugin_root = Path(sensor_plugin_root).resolve()
        if refresh_env:
            prepare_plugin_venv(plugin_root)
        else:
            resolve_plugin_python(plugin_root)
        return plugin_root, resolve_plugin_site_packages(plugin_root), lambda: None

    if sensor_bundle_path:
        bundle_path = Path(sensor_bundle_path).resolve()
        temp_dir = tempfile.TemporaryDirectory(prefix="nexusn3-algorithm-sensor-bundle-")
        temp_root = Path(temp_dir.name)
        extracted_root = temp_root / "bundle"
        extracted_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bundle_path, "r") as archive:
            archive.extractall(extracted_root)
        site_packages = _prepare_bundle_test_env(extracted_root, temp_root / "env")
        return extracted_root, site_packages, temp_dir.cleanup

    raise ValueError("Either sensor_plugin_root or sensor_bundle_path is required")


def _read_bundle_manifest(extracted_root: Path) -> dict:
    manifest_path = extracted_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Extracted bundle missing manifest.json: {manifest_path}")
    import json
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _prepare_bundle_test_env(extracted_root: Path, env_root: Path) -> Path:
    env_root.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(env_root)], check=True)
    python_bin = resolve_venv_python(env_root)
    artifacts_dir = extracted_root / "artifacts"
    wheel_paths = sorted(artifacts_dir.glob("*.whl"))
    if not wheel_paths:
        raise FileNotFoundError(f"No wheel artifacts found in {artifacts_dir}")
    subprocess.run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(artifacts_dir),
            *[str(path) for path in wheel_paths],
        ],
        check=True,
    )
    return resolve_venv_site_packages(env_root)


def _discover_catalog_plugins(catalog_root: Path) -> list[tuple[str, Path]]:
    """Return all valid plugin roots in a standard catalog checkout."""
    catalog_root = catalog_root.resolve()
    if not catalog_root.is_dir():
        raise FileNotFoundError(f"Catalog root not found: {catalog_root}")

    plugins: list[tuple[str, Path]] = []
    for family in ("sensors", "algorithms"):
        family_root = catalog_root / family
        if not family_root.is_dir():
            continue
        plugins.extend(
            (family, candidate)
            for candidate in sorted(family_root.iterdir())
            if candidate.is_dir()
            and candidate.joinpath("plugin.json").is_file()
            and candidate.joinpath("pyproject.toml").is_file()
        )

    if not plugins:
        raise FileNotFoundError(
            f"No plugins found under {catalog_root / 'sensors'} or {catalog_root / 'algorithms'}"
        )
    return plugins


def _infer_bundle_plugin_root(bundle_path: Path, plugin_id: str, plugin_type: str) -> Path:
    family_dir = "sensors" if plugin_type == "sensor" else "algorithms"
    repo_prefix = "nexus-n3-sensor-" if plugin_type == "sensor" else "nexus-n3-algorithm-"
    if bundle_path.parent.name == family_dir and bundle_path.parent.parent.name == "plugin-builds":
        workspace_root = bundle_path.parent.parent.parent
        candidate = workspace_root / family_dir / f"{repo_prefix}{plugin_id}"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not infer the source plugin repository from the bundle path.\n\n"
        f"Bundle path:\n  {bundle_path}\n\n"
        "Pass --plugin-root explicitly when testing a built bundle outside the standard nexus-n3-plugin-catalog layout."
    )


if __name__ == "__main__":
    raise SystemExit(main())
