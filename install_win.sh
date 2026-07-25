#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${NEXUS_N3_PLUGIN_TOOLING_VENV:-$SCRIPT_DIR/.venv}"
PYTHON_BIN="${PYTHON:-python}"

USER_BIN_DIR="${NEXUS_N3_PLUGIN_TOOLING_BIN_DIR:-$HOME/.local/bin}"
USER_CLI_LINK="$USER_BIN_DIR/nexus-n3-plugin"
BASHRC_FILE="$HOME/.bashrc"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1

echo "Nexus N3 plugin tooling Windows installer"
echo "Repository: $SCRIPT_DIR"
echo "Virtual environment: $VENV_DIR"
echo

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  echo "Install Python or set PYTHON to the Python executable and rerun." >&2
  exit 1
fi

echo "Using Python:"
"$PYTHON_BIN" --version
echo

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "Using existing virtual environment: $VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
VENV_CLI="$VENV_DIR/Scripts/nexus-n3-plugin.exe"

if [[ ! -f "$VENV_PYTHON" ]]; then
  echo "Invalid Windows virtual environment at: $VENV_DIR" >&2
  echo "Expected Python executable: $VENV_PYTHON" >&2
  echo >&2
  echo "Remove the existing .venv directory and rerun this script." >&2
  exit 1
fi

echo
echo "Installing base Python build tooling"
"$VENV_PYTHON" -m pip install --upgrade \
  pip \
  "setuptools>=61.0" \
  wheel \
  "build>=1.2"

echo
echo "Installing nexus-n3-plugin-sdk in editable mode"
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR/packages/sdk"

echo
echo "Installing nexus-n3-plugin-cli in editable mode"
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR/packages/cli"

if [[ ! -f "$VENV_CLI" ]]; then
  echo "CLI executable was not created: $VENV_CLI" >&2
  exit 1
fi

echo
echo "Validating virtual-environment CLI"
"$VENV_CLI" --help >/dev/null

echo
echo "Installing Git Bash CLI wrapper"
mkdir -p "$USER_BIN_DIR"

cat >"$USER_CLI_LINK" <<EOF
#!/usr/bin/env bash
exec "$VENV_CLI" "\$@"
EOF

chmod 755 "$USER_CLI_LINK"

echo
echo "Configuring Git Bash PATH"

touch "$BASHRC_FILE"

PATH_LINE="export PATH=\"$USER_BIN_DIR:\$PATH\""

if grep -Fqx "$PATH_LINE" "$BASHRC_FILE"; then
  echo "$USER_BIN_DIR is already configured in $BASHRC_FILE"
else
  {
    echo
    echo "# Nexus N3 plugin tooling"
    echo "$PATH_LINE"
  } >>"$BASHRC_FILE"

  echo "Added $USER_BIN_DIR to $BASHRC_FILE"
fi

# Make the command available within this installer process.
case ":$PATH:" in
  *":$USER_BIN_DIR:"*)
    ;;
  *)
    export PATH="$USER_BIN_DIR:$PATH"
    ;;
esac

hash -r

echo
echo "Validating shared CLI wrapper"
"$USER_CLI_LINK" --help >/dev/null

cat <<EOF

Nexus N3 plugin tooling is installed successfully.

CLI wrapper:

  $USER_CLI_LINK

Reload the current Git Bash session:

  source "$BASHRC_FILE"

Then verify the command:

  nexus-n3-plugin --help

Example commands:

  nexus-n3-plugin init sensor my-sensor-plugin
  nexus-n3-plugin init algorithm my-algorithm-plugin

You can also call the virtual-environment executable directly:

  "$VENV_CLI" --help

EOF
