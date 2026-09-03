"""Sensor plugin scaffolding helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SensorPluginTemplate:
    """Normalized metadata used to render a sensor plugin scaffold."""

    plugin_id: str
    repo_name: str
    package_name: str
    class_name: str
    spec_name: str
    display_name: str
    sensor_type_key: str
    adapter: str
    manufacturer_id: int
    sample_class_name: str
    sample_type: str


def scaffold_sensor_plugin(
    plugin_id: str,
    display_name: str | None,
    output_dir: Path,
    adapter: str,
    sample_type: str,
    package_name: str | None,
    manufacturer_id: int,
    force: bool,
) -> Path:
    """Create a new standalone sensor plugin repository."""
    output_dir = _resolve_output_dir(output_dir, "sensors")
    normalized_id = _normalize_plugin_id(plugin_id)
    template = _build_template(
        plugin_id=normalized_id,
        display_name=display_name,
        adapter=adapter,
        sample_type=sample_type,
        package_name=package_name,
        manufacturer_id=manufacturer_id,
    )
    target_dir = output_dir / template.repo_name
    _prepare_target_dir(target_dir, force=force)

    _write_text(target_dir / "README.md", _render_readme(template))
    _write_text(target_dir / "pyproject.toml", _render_pyproject(template))
    plugin_manifest = _render_plugin_manifest(template)
    _write_text(target_dir / "plugin.json", plugin_manifest)

    package_root = target_dir / "src" / template.package_name
    _write_text(package_root / "__init__.py", _render_package_init(template))
    _write_text(package_root / "plugin.json", plugin_manifest)
    _write_text(package_root / "sensor.py", _render_sensor_module(template))
    _write_text(package_root / "parser.py", _render_parser_module(template))
    _write_text(package_root / "samples.py", _render_samples_module(template))
    _write_text(package_root / template.spec_name, _render_spec(template))

    tests_root = target_dir / "tests"
    _write_text(tests_root / "test_import.py", _render_test_import(template))
    _write_text(tests_root / "test_spec.py", _render_test_spec(template))
    _write_text(tests_root / "test_manifest.py", _render_test_manifest(template))

    _write_text(
        target_dir / ".gitignore",
        ".venv/\n__pycache__/\n*.egg-info/\ndist/\nbuild/\n.pytest_cache/\n",
    )
    return target_dir


def _normalize_plugin_id(plugin_id: str) -> str:
    value = plugin_id.strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in value:
        value = value.replace("--", "-")
    if not value:
        raise ValueError("plugin_id must not be empty")
    return value


def _build_template(
    plugin_id: str,
    display_name: str | None,
    adapter: str,
    sample_type: str,
    package_name: str | None,
    manufacturer_id: int,
) -> SensorPluginTemplate:
    repo_name = f"nexus-n3-sensor-{plugin_id}"
    package = package_name or f"nexus_n3_sensor_{plugin_id.replace('-', '_')}"
    display = display_name or " ".join(part.capitalize() for part in plugin_id.split("-"))
    base_name = "".join(part.capitalize() for part in plugin_id.split("-"))
    class_name = base_name if base_name.endswith("Sensor") else base_name + "Sensor"
    spec_base_name = base_name.removesuffix("Sensor") or base_name
    spec_name = spec_base_name + "Spec.yaml"
    sensor_type_key = plugin_id.replace("-", "_")
    sample_class_name = "".join(part.capitalize() for part in sample_type.split("_")) + "Sample"

    return SensorPluginTemplate(
        plugin_id=plugin_id,
        repo_name=repo_name,
        package_name=package,
        class_name=class_name,
        spec_name=spec_name,
        display_name=display,
        sensor_type_key=sensor_type_key,
        adapter=adapter,
        manufacturer_id=manufacturer_id,
        sample_class_name=sample_class_name,
        sample_type=sample_type,
    )


def _prepare_target_dir(target_dir: Path, force: bool) -> None:
    if target_dir.exists():
        if any(target_dir.iterdir()):
            raise FileExistsError(f"Target directory already exists and is not empty: {target_dir}")
        if not force:
            raise FileExistsError(
                f"Target directory already exists: {target_dir}. Use --force only for an empty directory."
            )
    else:
        target_dir.mkdir(parents=True, exist_ok=False)


def _resolve_output_dir(output_dir: Path, plugin_family: str) -> Path:
    """Place plugins under a grouped workspace when targeting the shared plugin catalog."""
    if output_dir.name == "nexus-n3-plugin-catalog":
        return output_dir / plugin_family
    return output_dir


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _render_readme(template: SensorPluginTemplate) -> str:
    return f"""# {template.display_name} Sensor Plugin

Standalone Nexus N3 sensor plugin for `{template.display_name}`.

## Development

Install the SDK and CLI from the local tooling repo, then build this plugin:

```bash
python -m build
```

## Notes

- Generated by `nexus-n3-plugin init sensor`
- Depends on `nexus-n3-plugin-sdk`
"""


def _render_pyproject(template: SensorPluginTemplate) -> str:
    dist_name = template.repo_name
    entry_name = template.plugin_id.replace("-", "_")
    return f"""[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{dist_name}"
version = "0.1.0"
description = "{template.display_name} sensor plugin for Nexus N3 OS"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "nexus-n3-plugin-sdk>=0.1.0",
]

[project.entry-points."nexus_n3.sensors"]
{entry_name} = "{template.package_name}.sensor:{template.class_name}"

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
{template.package_name} = ["*.yaml", "plugin.json"]
"""


def _render_plugin_manifest(template: SensorPluginTemplate) -> str:
    manifest = {
        "plugin_id": template.plugin_id,
        "plugin_type": "sensor",
        "display_name": template.display_name,
        "version": "0.1.0",
        "package_name": template.repo_name,
        "python_package": template.package_name,
        "entry_point": f"{template.package_name}.sensor:{template.class_name}",
        "spec_path": f"{template.package_name}/{template.spec_name}",
        "sdk_version": "0.1.0",
        "min_nexus_n3_core_version": "0.0.0",
        "supports_consumed_input": False,
    }
    return json.dumps(manifest, indent=2) + "\n"


def _render_package_init(template: SensorPluginTemplate) -> str:
    return f'''"""Package for the {template.display_name} sensor plugin."""\n\nfrom .sensor import {template.class_name}\n\n__all__ = ["{template.class_name}"]\n'''


def _render_sensor_module(template: SensorPluginTemplate) -> str:
    transport_assignment = ""
    if template.adapter.upper() == "BLE":
        transport_assignment = '\n        self.transport_spec = spec.get("transport", {}).get(self.adapter, {})'
    return f'''"""Sensor implementation for {template.display_name}."""\n\nimport logging\n\nfrom nexus_n3_plugin_sdk import SensorBase, SensorType\n\nfrom .samples import {template.sample_class_name}\n\n\nclass {template.class_name}(SensorBase):\n    """Generated sensor plugin skeleton."""\n\n    sensor_type = SensorType("{template.display_name}", {template.manufacturer_id})\n    SAMPLE_CLASS = {template.sample_class_name}\n    SPEC_PATH = "{template.spec_name}"\n\n    def __init__(self, sensor):\n        self.logger = logging.getLogger(self.sensor_type.local_name)\n        spec = self.load_raw_spec()\n        super().__init__(self.sensor_type, spec){transport_assignment}\n\n    def consume_input(self, source_plugin_id: str, payload) -> bool:\n        """Accept forwarded input from another plugin when this plugin needs it."""\n        return False\n\n    async def setup(self, adapter, enable_battery: bool = False, enable_button: bool = False):\n        """Configure the sensor after connect."""\n        return\n\n    async def start_stream(self, adapter):\n        """Start streaming sensor data."""\n        raise NotImplementedError("Implement start_stream() for this sensor plugin")\n\n    async def stop_stream(self, adapter):\n        """Stop streaming sensor data."""\n        raise NotImplementedError("Implement stop_stream() for this sensor plugin")\n'''


def _render_parser_module(template: SensorPluginTemplate) -> str:
    return f'''"""Packet parsing helpers for the {template.display_name} sensor plugin."""\n\nfrom __future__ import annotations\n\n\ndef parse_packet(packet: bytes):\n    """Decode a raw sensor packet into one or more sample objects."""\n    raise NotImplementedError("Implement packet parsing for the {template.display_name} sensor")\n'''


def _render_samples_module(template: SensorPluginTemplate) -> str:
    if template.sample_type == "imu":
        return '''"""Sample model aliases for this sensor plugin."""\n\nfrom nexus_n3_plugin_sdk.samples import IMUSample\n\n__all__ = ["IMUSample"]\n'''
    return f'''"""Sample models for {template.display_name}."""\n\nfrom dataclasses import dataclass\nfrom typing import Any, ClassVar, List, Optional\n\nfrom nexus_n3_plugin_sdk.samples import SensorSample\n\n\n@dataclass(frozen=True)\nclass {template.sample_class_name}(SensorSample):\n    """Generated sample skeleton."""\n\n    sample_type: ClassVar[str] = "{template.sample_type}"\n\n    value: Optional[float] = None\n\n    @classmethod\n    def csv_header(cls) -> List[str]:\n        return ["timestamp", "value"]\n\n    def to_csv_row(self) -> List[Any]:\n        return [self.timestamp, self.value]\n'''


def _render_spec(template: SensorPluginTemplate) -> str:
    transport_block = ""
    if template.adapter.upper() == "BLE":
        transport_block = "\ntransport:\n  BLE:\n    services: {}\n"
    return f'''sensor:\n  name: "{template.display_name}"\n  type: "{template.sensor_type_key}"\n  adapter: "{template.adapter}"\n\ncapabilities:\n  - streaming\n\nevents:\n  - on_data\n  - on_error\n\nattributes:\n  SAMPLING_RATE:\n    default: 1\n    supported: [1]\n    unit: "Hz"\n\nlocations:\n  supported:\n    - DEFAULT\n\ncomputations: []{transport_block}'''


def _render_test_import(template: SensorPluginTemplate) -> str:
    return f'''from {template.package_name}.sensor import {template.class_name}\nfrom nexus_n3_plugin_sdk import SensorBase\n\n\ndef test_sensor_class_is_a_sensor_base_subclass() -> None:\n    assert issubclass({template.class_name}, SensorBase)\n'''


def _render_test_spec(template: SensorPluginTemplate) -> str:
    return f'''from {template.package_name}.sensor import {template.class_name}\n\n\ndef test_sensor_spec_loads() -> None:\n    spec = {template.class_name}.load_raw_spec()\n    assert spec["sensor"]["name"] == "{template.display_name}"\n    assert spec["sensor"]["adapter"] == "{template.adapter}"\n'''


def _render_test_manifest(template: SensorPluginTemplate) -> str:
    return f'''import json\nfrom pathlib import Path\n\n\ndef test_plugin_manifest_exists() -> None:\n    plugin_root = Path(__file__).resolve().parents[1]\n    root_manifest = json.loads((plugin_root / "plugin.json").read_text(encoding="utf-8"))\n    packaged_manifest = json.loads((plugin_root / "src" / "{template.package_name}" / "plugin.json").read_text(encoding="utf-8"))\n    assert packaged_manifest == root_manifest\n    assert root_manifest["plugin_type"] == "sensor"\n    assert root_manifest["entry_point"] == "{template.package_name}.sensor:{template.class_name}"\n'''
