from __future__ import annotations

import sys
from pathlib import Path

import pytest

CLI_SRC = Path(__file__).resolve().parents[1] / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from nexus_n3_plugin_cli.main import _discover_catalog_plugins, build_parser
from nexus_n3_plugin_cli.plugin_env import plugin_venv_is_prepared, resolve_venv_python


def test_resolve_venv_python_accepts_windows_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python_bin = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_bin.parent.mkdir(parents=True)
    python_bin.touch()
    monkeypatch.setattr(sys, "platform", "win32")

    assert resolve_venv_python(tmp_path / ".venv") == python_bin


def test_resolve_venv_python_accepts_posix_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python_bin = tmp_path / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.touch()
    monkeypatch.setattr(sys, "platform", "linux")

    assert resolve_venv_python(tmp_path / ".venv") == python_bin


def test_prepare_command_defaults_to_current_plugin() -> None:
    args = build_parser().parse_args(["prepare"])

    assert args.command == "prepare"
    assert args.plugin_root == "."


def test_incomplete_plugin_environment_is_not_prepared(tmp_path: Path) -> None:
    assert plugin_venv_is_prepared(tmp_path) is False


def test_build_accepts_catalog_root() -> None:
    args = build_parser().parse_args(
        ["build", "--catalog-root", "catalog", "--target", "win"]
    )

    assert args.catalog_root == "catalog"
    assert args.plugin_root is None
    assert args.target == "win"


def test_discover_catalog_plugins_returns_both_families(tmp_path: Path) -> None:
    sensor = tmp_path / "sensors" / "sensor-one"
    algorithm = tmp_path / "algorithms" / "algorithm-one"
    ignored = tmp_path / "sensors" / "not-a-plugin"
    for plugin_root in (sensor, algorithm):
        plugin_root.mkdir(parents=True)
        plugin_root.joinpath("plugin.json").touch()
        plugin_root.joinpath("pyproject.toml").touch()
    ignored.mkdir(parents=True)

    assert _discover_catalog_plugins(tmp_path) == [
        ("sensors", sensor),
        ("algorithms", algorithm),
    ]
