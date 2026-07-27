from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def resolve_venv_python(venv_dir: Path) -> Path:
    """Return the Python executable for a virtual environment on any host OS."""
    venv_dir = venv_dir.resolve()
    candidates = (
        [venv_dir / "Scripts" / "python.exe", venv_dir / "bin" / "python"]
        if sys.platform == "win32"
        else [venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"]
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    expected = "\n".join(f"  {candidate}" for candidate in candidates)
    raise FileNotFoundError(
        "Virtual environment Python executable not found.\n\n"
        f"Expected one of:\n{expected}\n\n"
        "Recreate or repair the virtual environment."
    )


def resolve_venv_site_packages(venv_dir: Path) -> Path:
    """Ask a virtual environment where its platform-specific site-packages lives."""
    python_bin = resolve_venv_python(venv_dir)
    completed = subprocess.run(
        [
            str(python_bin),
            "-c",
            "import sysconfig; print(sysconfig.get_path('purelib'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    site_packages = Path(completed.stdout.strip()).resolve()

    if not site_packages.is_dir():
        raise FileNotFoundError(
            "Virtual environment site-packages directory not found.\n\n"
            f"Python reported:\n  {site_packages}\n\n"
            "Recreate or repair the virtual environment."
        )

    return site_packages


def resolve_plugin_site_packages(plugin_root: Path) -> Path:
    """Return the plugin venv site-packages directory."""
    return resolve_venv_site_packages(plugin_root.resolve() / ".venv")


def resolve_plugin_python(plugin_root: Path) -> Path:
    """Return the plugin-local Python executable from an existing plugin venv."""
    plugin_root = plugin_root.resolve()
    try:
        return resolve_venv_python(plugin_root / ".venv")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Plugin virtual environment not found or invalid.\n\n"
            f"Plugin root:\n  {plugin_root}\n\n"
            "Prepare it with:\n"
            f"  nexus-n3-plugin prepare --plugin-root \"{plugin_root}\"\n"
        ) from exc


def plugin_venv_is_prepared(plugin_root: Path) -> bool:
    """Return whether a plugin environment has the packages required to build."""
    try:
        site_packages = resolve_plugin_site_packages(plugin_root)
    except FileNotFoundError:
        return False

    required_distributions = (
        "build",
        "setuptools",
        "wheel",
        "nexus_n3_plugin_sdk",
    )
    return all(
        any(site_packages.glob(f"{distribution}-*.dist-info"))
        for distribution in required_distributions
    )


def prepare_plugin_venv(plugin_root: Path, sdk_root: Path | None = None) -> Path:
    plugin_root = plugin_root.resolve()
    if not plugin_root.joinpath("pyproject.toml").is_file() or not plugin_root.joinpath(
        "plugin.json"
    ).is_file():
        raise FileNotFoundError(
            "Not a plugin source repository; expected pyproject.toml and plugin.json in:\n"
            f"  {plugin_root}"
        )

    resolved_sdk_root = (sdk_root.resolve() if sdk_root is not None else _default_sdk_root())
    if resolved_sdk_root is None or not resolved_sdk_root.joinpath("setup.py").is_file():
        raise FileNotFoundError(
            "Local nexus-n3-plugin-sdk source not found.\n\n"
            "Install the tooling from its source checkout or pass:\n"
            "  --sdk-root /path/to/nexus-n3-plugin-tooling/packages/sdk"
        )

    venv_dir = plugin_root / ".venv"

    if not venv_dir.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    python_bin = resolve_plugin_python(plugin_root)

    if not python_bin.exists():
        raise RuntimeError(f"Plugin venv is invalid: {venv_dir}")

    subprocess.run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools>=61.0",
            "wheel",
            "build>=1.2",
        ],
        check=True,
    )

    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-e", str(resolved_sdk_root)],
        check=True,
    )

    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-e", str(plugin_root)],
        check=True,
    )

    return python_bin


def _default_sdk_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[4] / "packages" / "sdk"
    if candidate.joinpath("setup.py").is_file():
        return candidate
    return None
