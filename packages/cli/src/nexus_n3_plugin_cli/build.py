from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from nexus_n3_plugin_cli.plugin_env import resolve_plugin_python


@dataclass(frozen=True)
class DependencyTarget:
    """Bundle target metadata and optional pip download settings."""

    target_id: str | None = None
    platform: str | None = None
    python_version: str | None = None
    implementation: str | None = None
    abi: str | None = None

    @classmethod
    def from_preset(cls, target_id: str) -> "DependencyTarget":
        normalized = target_id.strip().lower()
        presets = {
            "rpi": cls(
                target_id="rpi",
                platform="manylinux2014_aarch64",
                python_version="3.12",
                implementation="cp",
                abi="cp312",
            ),
            "jetson": cls(
                target_id="jetson",
                platform="manylinux2014_aarch64",
                python_version="3.12",
                implementation="cp",
                abi="cp312",
            ),
            "win": cls(
                target_id="win",
                platform="win_amd64",
                python_version="3.12",
                implementation="cp",
                abi="cp312",
            ),
            "local": cls(
                target_id="local",
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
                implementation=_normalize_python_implementation(sys.implementation.name),
                abi=_current_abi_tag(),
            ),
        }
        try:
            return presets[normalized]
        except KeyError as exc:
            raise ValueError(f"Unsupported target preset: {target_id}") from exc

    def append_pip_args(self, cmd: list[str]) -> None:
        if self.platform:
            cmd.extend(["--platform", self.platform])
        if self.python_version:
            cmd.extend(["--python-version", self.python_version])
        if self.implementation:
            cmd.extend(["--implementation", self.implementation])
        if self.abi:
            cmd.extend(["--abi", self.abi])

    def bundle_suffix(self) -> str:
        return f"-{self.target_id}" if self.target_id else ""

    def manifest_target(self) -> dict:
        payload = {
            "id": self.target_id or "unspecified",
            "platform": self.platform,
            "python_version": self.python_version,
            "implementation": self.implementation,
            "abi": self.abi,
            "build_os": platform.system().lower(),
            "build_machine": platform.machine().lower(),
        }
        return {key: value for key, value in payload.items() if value}


def _load_plugin_manifest(plugin_root: Path) -> dict:
    manifest_path = plugin_root / "plugin.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Not a plugin source repo: missing plugin.json in {plugin_root}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    required = [
        "plugin_id",
        "plugin_type",
        "display_name",
        "version",
        "package_name",
        "python_package",
        "entry_point",
        "sdk_version",
        "min_nexus_n3_core_version",
    ]
    missing = [key for key in required if key not in manifest]

    if missing:
        raise ValueError(f"Invalid plugin.json; missing fields: {', '.join(missing)}")

    return manifest


def build_plugin_bundle(
    plugin_root: Path,
    output_dir: Path,
    force: bool = False,
    *,
    sdk_root: Path | None = None,
    include_sdk: bool = True,
    include_dependencies: bool = True,
    dependency_target: DependencyTarget | None = None,
    extra_artifacts: list[Path] | None = None,
    dependency_wheelhouses: list[Path] | None = None,
) -> Path:
    """Build a Phase 1 .rsnxplugin archive from a plugin source repo."""
    _ = force
    plugin_root = plugin_root.resolve()
    output_dir = output_dir.resolve()
    plugin_python = resolve_plugin_python(plugin_root)
    extra_artifacts = [artifact.resolve() for artifact in (extra_artifacts or [])]
    dependency_wheelhouses = [wheelhouse.resolve() for wheelhouse in (dependency_wheelhouses or [])]

    legacy_manifest = _load_plugin_manifest(plugin_root)

    if not plugin_root.joinpath("pyproject.toml").is_file():
        raise FileNotFoundError(f"Missing pyproject.toml in {plugin_root}")

    build_root = Path(tempfile.mkdtemp(prefix="nexus-n3-plugin-build-"))
    try:
        plugin_wheel = _build_local_wheel(
            plugin_root,
            build_root / "plugin-dist",
            plugin_python,
        )

        artifacts: list[Path] = [plugin_wheel]

        local_wheelhouse = build_root / "local-wheelhouse"
        local_wheelhouse.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin_wheel, local_wheelhouse / plugin_wheel.name)

        if include_sdk:
            resolved_sdk_root = _resolve_sdk_root(sdk_root)
            if resolved_sdk_root is not None:
                sdk_wheel = _build_local_wheel(
                    resolved_sdk_root,
                    build_root / "sdk-dist",
                    plugin_python,
                )
                artifacts.append(sdk_wheel)
                shutil.copy2(sdk_wheel, local_wheelhouse / sdk_wheel.name)

        existing_names = {artifact.name for artifact in artifacts}

        if include_dependencies:
            dependency_wheels = _download_runtime_wheels(
                [str(plugin_wheel)],
                build_root / "dependency-dist",
                python_bin=plugin_python,
                extra_find_links=[local_wheelhouse, *dependency_wheelhouses],
                dependency_target=dependency_target,
            )

            for wheel in dependency_wheels:
                if wheel.name not in existing_names:
                    artifacts.append(wheel)
                    existing_names.add(wheel.name)

        artifacts.extend(extra_artifacts)

        target_suffix = dependency_target.bundle_suffix() if dependency_target is not None else ""
        bundle_name = (
            f"{legacy_manifest['package_name']}-{legacy_manifest['version']}{target_suffix}.rsnxplugin"
        )
        bundle_path = output_dir / bundle_name

        if bundle_path.exists():
            bundle_path.unlink()

        archive_root = build_root / "archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        artifacts_dir = archive_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        copied_artifacts: list[Path] = []
        for artifact in artifacts:
            target = artifacts_dir / artifact.name
            shutil.copy2(artifact, target)
            copied_artifacts.append(target)

        _copy_optional_metadata(plugin_root, legacy_manifest, archive_root)
        manifest = _build_phase1_manifest(
            plugin_root,
            legacy_manifest,
            copied_artifacts,
            dependency_target=dependency_target,
        )
        (archive_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        checksums = _compute_checksums(archive_root)
        (archive_root / "checksums.json").write_text(
            json.dumps(checksums, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(archive_root.rglob("*")):
                if file_path.is_dir():
                    continue
                archive.write(file_path, file_path.relative_to(archive_root).as_posix())

        return bundle_path
    finally:
        shutil.rmtree(build_root, ignore_errors=True)


def _resolve_sdk_root(sdk_root: Path | None) -> Path | None:
    if sdk_root is not None:
        resolved = sdk_root.resolve()
        return resolved if resolved.joinpath("setup.py").is_file() else None

    candidate = Path(__file__).resolve().parents[4] / "packages" / "sdk"
    if candidate.joinpath("setup.py").is_file():
        return candidate
    return None


def _build_local_wheel(
    project_root: Path,
    output_dir: Path,
    python_bin: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            str(python_bin),
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(output_dir),
        ],
        cwd=project_root,
        check=True,
    )

    wheels = sorted(output_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"Expected exactly one wheel in {output_dir}, found {len(wheels)}")
    return wheels[0]

def _download_runtime_wheels(
    requirements: list[str],
    output_dir: Path,
    *,
    python_bin: Path,
    extra_find_links: list[Path] | None = None,
    dependency_target: DependencyTarget | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_bin),
        "-m",
        "pip",
        "download",
        "--dest",
        str(output_dir),
        "--only-binary",
        ":all:",
    ]
    for link_dir in extra_find_links or []:
        cmd.extend(["--find-links", str(link_dir)])

    if dependency_target is not None:
        dependency_target.append_pip_args(cmd)

    cmd.extend(requirements)

    subprocess.run(cmd, check=True)

    return sorted(output_dir.glob("*.whl"))

def _copy_optional_metadata(plugin_root: Path, legacy_manifest: dict, archive_root: Path) -> None:
    metadata_dir = archive_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    package_dir = plugin_root / "src" / legacy_manifest["python_package"]

    spec_path = legacy_manifest.get("spec_path")
    if spec_path:
        source = package_dir / Path(spec_path).name
        if source.exists():
            shutil.copy2(source, metadata_dir / "sensor_spec.yaml")

    config_path = legacy_manifest.get("config_path")
    if config_path:
        source = package_dir / Path(config_path).name
        if source.exists():
            shutil.copy2(source, metadata_dir / "algorithm_config.yaml")


def _build_phase1_manifest(
    plugin_root: Path,
    legacy_manifest: dict,
    artifacts: list[Path],
    *,
    dependency_target: DependencyTarget | None = None,
) -> dict:
    entry_module, entry_callable = legacy_manifest["entry_point"].split(":", 1)
    plugin_type = legacy_manifest["plugin_type"]
    capabilities = _load_capabilities(plugin_root, legacy_manifest)
    spec_path = legacy_manifest.get("spec_path")
    config_path = legacy_manifest.get("config_path")

    manifest = {
        "schema_version": 1,
        "plugin_id": legacy_manifest["plugin_id"],
        "plugin_type": plugin_type,
        "display_name": legacy_manifest["display_name"],
        "version": legacy_manifest["version"],
        "sdk_version": legacy_manifest["sdk_version"],
        "min_nexus_n3_core_version": legacy_manifest["min_nexus_n3_core_version"],
        "runtime_protocol": {"name": "nexus-n3-local-jsonrpc", "version": 1},
        "entrypoint": {"module": entry_module, "callable": entry_callable},
        "artifacts": [
            {
                "type": "wheel",
                "path": f"artifacts/{artifact.name}",
                "sha256": _sha256_file(artifact),
            }
            for artifact in artifacts
        ],
        "spec": {
            "type": "sensor_yaml" if plugin_type == "sensor" else "algorithm_config",
            "path": spec_path or config_path or "",
        },
        "capabilities": capabilities,
        "inputs": [],
        "outputs": [],
        "adapter_requirements": _adapter_requirements(capabilities),
        "permissions": {"network": False, "filesystem_write": False},
        "healthcheck": {
            "command": "import_entrypoint",
            "module": entry_module,
            "callable": entry_callable,
            "timeout_seconds": 10,
        },
    }
    if dependency_target is not None:
        manifest["target"] = dependency_target.manifest_target()
    if plugin_type == "algorithm":
        manifest["capabilities"].update(
            {
                "algorithm_name": legacy_manifest.get("algorithm_name"),
                "supports_intermediate": legacy_manifest.get("supports_intermediate", False),
                "supports_consolidation": legacy_manifest.get("supports_consolidation", False),
                "executor_entry_points": legacy_manifest.get("executor_entry_points", {}),
            }
        )
    return manifest


def _load_capabilities(plugin_root: Path, legacy_manifest: dict) -> dict:
    package_dir = plugin_root / "src" / legacy_manifest["python_package"]
    spec_path = legacy_manifest.get("spec_path")
    if spec_path:
        source = package_dir / Path(spec_path).name
        if source.exists():
            payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
            return {
                "capabilities": payload.get("capabilities", []),
                "events": payload.get("events", []),
                "data_streams": sorted((payload.get("data_streams") or {}).keys()),
                "adapter": payload.get("sensor", {}).get("adapter"),
                "attributes": sorted((payload.get("attributes") or {}).keys()),
            }

    config_path = legacy_manifest.get("config_path")
    if config_path:
        source = package_dir / Path(config_path).name
        if source.exists():
            payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
            return {
                "config_sections": sorted(payload.keys()),
            }

    return {}


def _adapter_requirements(capabilities: dict) -> dict:
    adapter = capabilities.get("adapter")
    if not adapter:
        return {}
    return {"family": adapter, "supported_backends": []}


def _compute_checksums(archive_root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for file_path in sorted(archive_root.rglob("*")):
        if file_path.is_dir():
            continue
        rel = file_path.relative_to(archive_root).as_posix()
        checksums[rel] = _sha256_file(file_path)
    return checksums


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_python_implementation(name: str) -> str:
    normalized = name.strip().lower()
    if normalized == "cpython":
        return "cp"
    return normalized


def _current_abi_tag() -> str | None:
    version = f"{sys.version_info.major}{sys.version_info.minor}"
    implementation = _normalize_python_implementation(sys.implementation.name)
    if implementation == "cp":
        return f"cp{version}"
    return None
