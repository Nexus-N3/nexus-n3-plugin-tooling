from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

CLI_SRC = Path(__file__).resolve().parents[1] / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from nexus_n3_plugin_cli.build import DependencyTarget, build_plugin_bundle


def test_build_sensor_reference_bundle_includes_phase1_files(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[4]
    plugin_root = repo_root / "nexus-n3-plugin-catalog" / "sensors" / "nexus-n3-sensor-movella-dot"

    bundle_path = build_plugin_bundle(
        plugin_root=plugin_root,
        output_dir=tmp_path,
        force=True,
        include_dependencies=False,
        dependency_target=DependencyTarget.from_preset("rpi"),
    )

    assert bundle_path.suffix == ".rsnxplugin"
    assert bundle_path.name.endswith("-rpi.rsnxplugin")
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "checksums.json" in names
        assert "metadata/sensor_spec.yaml" in names
        assert any(name.startswith("artifacts/nexus_n3_sensor_movella_dot-0.1.0") for name in names)
        assert any(name.startswith("artifacts/nexus_n3_plugin_sdk-0.1.0") for name in names)
        assert not any("pyyaml" in name.lower() for name in names)

        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["plugin_id"] == "movella-dot"
        assert manifest["spec"]["type"] == "sensor_yaml"
        assert manifest["entrypoint"]["module"] == "nexus_n3_sensor_movella_dot.sensor"
        assert manifest["target"]["id"] == "rpi"
        assert manifest["target"]["platform"] == "manylinux_2_28_aarch64"


def test_build_algorithm_reference_bundle_includes_phase1_files(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[4]
    plugin_root = (
        repo_root
        / "nexus-n3-plugin-catalog"
        / "algorithms"
        / "nexus-n3-algorithm-standard-loading-intensity"
    )

    bundle_path = build_plugin_bundle(
        plugin_root=plugin_root,
        output_dir=tmp_path,
        force=True,
        include_dependencies=False,
        dependency_target=DependencyTarget.from_preset("rpi"),
    )

    assert bundle_path.suffix == ".rsnxplugin"
    assert bundle_path.name.endswith("-rpi.rsnxplugin")
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "checksums.json" in names
        assert "metadata/algorithm_config.yaml" in names
        assert any(name.startswith("artifacts/nexus_n3_algorithm_standard_loading_intensity-0.1.2") for name in names)
        assert any(name.startswith("artifacts/nexus_n3_plugin_sdk-0.1.0") for name in names)

        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["plugin_id"] == "standard-loading-intensity"
        assert manifest["spec"]["type"] == "algorithm_config"
        assert manifest["capabilities"]["supports_intermediate"] is True
        assert manifest["capabilities"]["supports_consolidation"] is True
        assert manifest["target"]["id"] == "rpi"


def test_build_bundle_includes_extra_artifacts(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[4]
    plugin_root = repo_root / "nexus-n3-plugin-catalog" / "sensors" / "nexus-n3-sensor-movella-dot"
    extra_wheel = tmp_path / "numpy-0.0.0-py3-none-any.whl"
    extra_wheel.write_bytes(b"placeholder wheel content")

    bundle_path = build_plugin_bundle(
        plugin_root=plugin_root,
        output_dir=tmp_path,
        force=True,
        include_dependencies=False,
        extra_artifacts=[extra_wheel],
    )

    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        assert f"artifacts/{extra_wheel.name}" in names


def test_dependency_target_appends_pip_args() -> None:
    cmd = ["python", "-m", "pip", "download"]

    DependencyTarget(
        target_id="rpi",
        platform="manylinux2014_aarch64",
        python_version="3.12",
        implementation="cp",
        abi="cp312",
    ).append_pip_args(cmd)

    assert cmd[-8:] == [
        "--platform",
        "manylinux2014_aarch64",
        "--python-version",
        "3.12",
        "--implementation",
        "cp",
        "--abi",
        "cp312",
    ]


def test_dependency_target_from_preset_rpi() -> None:
    target = DependencyTarget.from_preset("rpi")

    assert target.target_id == "rpi"
    assert target.platform == "manylinux_2_28_aarch64"
    assert target.python_version == "3.12"
    assert target.implementation == "cp"
    assert target.abi == "cp312"
