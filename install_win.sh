#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${NEXUS_N3_PLUGIN_TOOLING_VENV:-$SCRIPT_DIR/.venv}"
PYTHON_BIN="${PYTHON:-python}"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  echo "Set PYTHON=/path/to/python.exe and rerun this script." >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "Using existing virtual environment: $VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
VENV_PIP="$VENV_DIR/Scripts/pip.exe"
VENV_CLI="$VENV_DIR/Scripts/nexus-n3-plugin.exe"

USER_BIN_DIR="${NEXUS_N3_PLUGIN_TOOLING_BIN_DIR:-$HOME/.local/bin}"
USER_CLI_LINK="$USER_BIN_DIR/nexus-n3-plugin"

if [[ ! -x "$VENV_PYTHON" || ! -x "$VENV_PIP" ]]; then
  echo "Invalid virtual environment at: $VENV_DIR" >&2
  echo "Remove it and rerun this script." >&2
  exit 1
fi

echo "Installing base Python build tooling"
"$VENV_PYTHON" -m pip install --upgrade \
  pip \
  "setuptools>=61.0" \
  wheel \
  "build>=1.2"

echo "Installing nexus-n3-plugin-sdk in editable mode"
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR/packages/sdk"

echo "Installing nexus-n3-plugin-cli in editable mode"
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR/packages/cli"

echo "Validating CLI"
"$VENV_CLI" --help >/dev/null

echo "Installing Git Bash PATH wrapper"
mkdir -p "$USER_BIN_DIR"

cat >"$USER_CLI_LINK" <<EOF
#!/usr/bin/env bash
exec "$VENV_CLI" "\$@"
EOF

chmod 755 "$USER_CLI_LINK"

cat <<EOF

Nexus N3 plugin tooling is installed.

Use the shared CLI from Git Bash:

  nexus-n3-plugin --help

  nexus-n3-plugin init sensor my-sensor-plugin
  nexus-n3-plugin init algorithm my-algorithm-plugin

Or call the virtual-environment executable directly:

  "$VENV_CLI" --help

If "$USER_BIN_DIR" is not on PATH, add this to ~/.bashrc:

  export PATH="$USER_BIN_DIR:\$PATH"

Then reload the shell:

  source ~/.bashrc

EOF