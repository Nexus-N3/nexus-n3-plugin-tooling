# Nexus N3 Plugin Tooling

Developer tooling for creating, preparing, testing, and packaging Nexus N3 plugins.

This repository provides the shared SDK and CLI used to author Nexus N3 sensor and algorithm plugins.

Repository:

```text
https://github.com/Nexus-N3/nexus-n3-plugin-tooling
```

## Overview

This repository provides:

* `nexus-n3-plugin-sdk`: shared authoring contracts for Nexus N3 plugins
* `nexus-n3-plugin-cli`: the `nexus-n3-plugin` command-line tool
* scaffolding for sensor and algorithm plugins
* isolated per-plugin environment creation
* local source-tree validation
* Phase 1 `.rsnxplugin` bundle packaging compatible with `nexus-n3-core`
* a focused sensor-plugin harness for source-tree development checks
* CSV capture output from harness test runs for offline inspection

The main idea is simple:

```text
Install the plugin tooling once.
Use nexus-n3-plugin to create plugins.
Each plugin gets its own isolated .venv.
Build and test commands use the plugin's own .venv.
The CLI is not installed into every plugin .venv.
```

## Status

This project is in early development.

The current implemented scope is:

* plugin scaffolding
* local source-tree validation
* Phase 1 `.rsnxplugin` bundle packaging for `nexus-n3-core`

Live isolated plugin runtime execution still belongs to `nexus-n3-core`.

`nexus-n3-plugin-tooling` owns the developer-side workflow for creating and building plugins.

`nexus-n3-core` owns plugin installation, cataloging, runtime discovery, and runtime execution.

## Environment Model

Nexus N3 plugin development uses three separate environments.

### 1. Tooling Environment

The tooling environment belongs to this repository.

Example location:

```text
nexus-n3-plugin-tooling/.venv
```

It contains:

* the `nexus-n3-plugin` CLI
* the plugin SDK source
* scaffold/build/test orchestration code

It is used to:

* scaffold plugins
* create plugin environments
* launch plugin builds
* run plugin validation commands

The tooling environment is installed once.

### 2. Plugin Environment

Each plugin owns its own isolated Python environment.

Example location:

```text
nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot/.venv
```

It contains:

* the plugin package
* the plugin's runtime dependencies
* the plugin's build dependencies
* the Nexus N3 plugin SDK dependency required by the plugin

It is used to:

* develop the plugin
* test the plugin
* build the plugin wheel
* collect dependencies for `.rsnxplugin` bundles

Each plugin gets its own `.venv` to avoid dependency conflicts between plugins.

The `nexus-n3-plugin` CLI should not be installed into every plugin `.venv`.

### 3. Runtime Environment

The runtime environment belongs to `nexus-n3-core`.

Example location:

```text
nexus-n3-core/.venv
```

It contains:

* `nexus-n3-core`
* installed `.rsnxplugin` bundles
* plugin discovery and runtime execution code

It is used to:

* install plugin bundles
* discover installed plugins
* run plugins inside Nexus N3 OS

## Recommended Workspace Layout

Recommended layout:

```text
<workspace>/
  nexus-n3-plugin-tooling/
  nexus-n3-core/
  nexus-n3-plugin-catalog/
    sensors/
    algorithms/
    plugin-builds/
      sensors/
      algorithms/
```

Example:

```text
nexus-n3-project/
  nexus-n3-plugin-tooling/
  nexus-n3-core/
  nexus-n3-plugin-catalog/
    sensors/
      nexus-n3-sensor-movella-dot/
        .venv/
    algorithms/
      nexus-n3-algorithm-standard-loading-intensity/
        .venv/
    plugin-builds/
      sensors/
      algorithms/
```

Directory conventions:

* sensor plugin repositories live under `nexus-n3-plugin-catalog/sensors/`
* algorithm plugin repositories live under `nexus-n3-plugin-catalog/algorithms/`
* built sensor bundles go under `nexus-n3-plugin-catalog/plugin-builds/sensors/`
* built algorithm bundles go under `nexus-n3-plugin-catalog/plugin-builds/algorithms/`

## Requirements

* Python 3.10 or newer
* Python `venv` support
* `pip`
* `git`

## Install The Tooling

Clone this repository and run the installer:

```bash
git clone https://github.com/Nexus-N3/nexus-n3-plugin-tooling.git
cd nexus-n3-plugin-tooling
./install.sh

on windows
./install_win.sh

```
on windows if the nexus-n3-plugin command is not available reload the Git Bash configuration:

```bash
source ~/.bashrc
```

The installer creates or reuses `.venv` inside the tooling repository.

It installs the SDK and CLI in editable mode and validates that `nexus-n3-plugin` can start.

## Prepare Plugins From A Catalog Checkout

Plugin `.venv` directories are local development artifacts and are not
committed to the catalog. After cloning the catalog, prepare an individual
plugin with:

```bash
nexus-n3-plugin prepare \
  --plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot
```

The command creates the plugin environment and installs its build tooling, the
local Nexus N3 plugin SDK, and the plugin itself. It supports native Windows
and POSIX virtual-environment layouts.

The `build` command also prepares a plugin automatically when its `.venv` is
missing. To build every sensor and algorithm in the catalog:

```bash
nexus-n3-plugin build \
  --catalog-root /path/to/nexus-n3-plugin-catalog \
  --output-dir /path/to/nexus-n3-plugin-catalog/plugin-builds \
  --target win
```

Bundles are written below `plugin-builds/sensors/` and
`plugin-builds/algorithms/`.

Activate the tooling environment:

```bash
# Linux, macOS, or WSL
source .venv/bin/activate

# Native Windows from Git Bash
source .venv/Scripts/activate

nexus-n3-plugin --help
```

Alternatively, add the tooling environment to your `PATH`:

```bash
export PATH="/path/to/nexus-n3-plugin-tooling/.venv/bin:$PATH"
nexus-n3-plugin --help
```

To install into a different tooling virtual environment path:

```bash
NEXUS_N3_PLUGIN_TOOLING_VENV=/path/to/venv ./install.sh
```

To choose a specific Python executable:

```bash
PYTHON=/path/to/python3 ./install.sh
```

## Install Or Refresh The Tooling

When the SDK or CLI changes, rerun the installer from the tooling repository:

```bash
cd /path/to/nexus-n3-plugin-tooling
./install.sh
```

This refreshes the tooling `.venv`, reinstalls the SDK and CLI in editable
mode, and validates that `nexus-n3-plugin` still starts.

## Current Workflow

The intended workflow is:

```text
1. Install nexus-n3-plugin-tooling once.

2. Use nexus-n3-plugin init to scaffold a plugin.

3. The init command creates the plugin source tree and the plugin's isolated .venv.

4. Edit the plugin code as needed.

5. Build a .rsnxplugin bundle using nexus-n3-plugin build.

6. Install the bundle into nexus-n3-core.

7. Run nexus-n3-core, which discovers installed plugins from the configured plugin root.
```

The tooling CLI is shared.

The plugin `.venv` is isolated.

The runtime consumes the final bundle.

## Current Sensor Harness Flow

Use this flow while developing a sensor plugin:

```text
1. Install or refresh nexus-n3-plugin-tooling with ./install.sh.
2. Scaffold a plugin with nexus-n3-plugin init.
3. Implement the plugin inside its own source repository and .venv.
4. Run the sensor harness against the plugin source tree.
5. Inspect the captured CSV output.
6. Build the final .rsnxplugin bundle once the harness run is satisfactory.
```

## One-Time Workspace Setup

Create the shared development directories:

```bash
mkdir -p /path/to/nexus-n3-plugin-catalog/sensors
mkdir -p /path/to/nexus-n3-plugin-catalog/algorithms
mkdir -p /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors
mkdir -p /path/to/nexus-n3-plugin-catalog/plugin-builds/algorithms
```

## Test The Current Movesense Plugin Against The Harness

Assuming a workspace layout like:

```text
<workspace>/
  nexus-n3-plugin-tooling/
  nexus-n3-plugin-catalog/
    sensors/
      nexus-n3-sensor-movesense/
```

refresh the tooling first:

```bash
cd /path/to/nexus-n3-plugin-tooling
./install.sh
```

Then run the Movesense harness from the workspace root or from the tooling
repository:

```bash
nexus-n3-plugin test sensor \
  --plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movesense \
  --adapter-backend nexus_ble_gateway \
  --gateway-serial-port /dev/serial/by-id/your_gateway_port \
  --duration 15 \
  --fail-on-no-data
```

If you want direct host BLE instead of the gateway backend:

```bash
nexus-n3-plugin test sensor \
  --plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movesense \
  --adapter-backend bleak \
  --duration 15 \
  --fail-on-no-data
```

Optional useful flags:

* `--identify` to call the plugin identify path after connect
* `--sensor-count N` to instantiate more than one expected sensor
* `--attribute KEY=VALUE` to override sensor attributes during the run
* `--output-dir /path/to/capture-dir` to control where captured files are written

By default the harness writes captured output under the plugin repository:

```text
nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movesense/
  plugin-test/
    ecg.csv
    hr.csv
    temp.csv
    errors.log
```

These CSV files are intended for developer inspection after the run. The
developer can analyze them with spreadsheets, Python, plotting tools, or any
other preferred workflow.

The `test sensor` command is provided by the shared tooling CLI. It launches
the harness in the tooling environment and adds the plugin `.venv`
site-packages for plugin-side dependencies. This keeps the CLI and harness out
of plugin environments while still using plugin-local dependencies during the
test run.

By default, `nexus-n3-plugin test sensor` does not reinstall the SDK or rebuild
the plugin. It is intended for source-mode testing before bundle creation. Use
`--refresh-env` only when you explicitly want to resync the plugin `.venv`.

This command is not currently a built-bundle validation command. Validation of
the final `.rsnxplugin` can be done locally with `nexus-n3-plugin test
sensor-bundle` or after installation into `nexus-n3-core`.

Built bundle example:

```bash
nexus-n3-plugin test sensor-bundle \
  --bundle-path /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors/nexus-n3-sensor-movella-dot-0.1.0.rsnxplugin \
  --adapter-backend bleak \
  --duration 15 \
  --fail-on-no-data
```

By default built-bundle capture files are written under:

```text
/path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot/
  plugin-test/
```

Algorithm plugin example:

```bash
nexus-n3-plugin test algorithm \
  --plugin-root /path/to/nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-standard-loading-intensity \
  --sensor-plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movesense \
  --adapter-backend nexus_ble_gateway \
  --gateway-serial-port /dev/serial/by-id/your_gateway_port \
  --duration 15 \
  --fail-on-no-results
```

The algorithm harness uses the selected sensor plugin to generate source-mode
samples, feeds those samples through a reduced compute-manager flow, prints
compute events in the terminal, and writes JSONL outputs under:

```text
nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-standard-loading-intensity/
  plugin-test/
    sensor-data/
      <sample-type>.csv
      errors.log
    computed/
      real_time.jsonl
      intermediate.jsonl
      consolidated.jsonl
```

The harness is intended to mirror `nexus-n3-core` compute-result behavior:

- sensor samples flow into a compute-manager style path
- emitted compute results are split by `stage`
- `real_time` outputs are sensor-level compute results
- `intermediate` and `consolidated` outputs are algorithm-stage aggregates
- algorithm payload bodies are not normalized across plugins

This is deliberate. Different algorithms emit different result content. The
shared contract is the compute-result routing envelope, especially `stage`, not
a single shared payload schema for all algorithms.

Built algorithm bundle example with a built sensor bundle:

```bash
nexus-n3-plugin test algorithm-bundle \
  --bundle-path /path/to/nexus-n3-plugin-catalog/plugin-builds/algorithms/nexus-n3-algorithm-standard-loading-intensity-0.1.0.rsnxplugin \
  --sensor-bundle-path /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors/nexus-n3-sensor-movesense-0.1.2.rsnxplugin \
  --adapter-backend nexus_ble_gateway \
  --gateway-serial-port /dev/serial/by-id/your_gateway_port \
  --duration 15 \
  --fail-on-no-results
```

`test algorithm` accepts either:

- `--sensor-plugin-root /path/to/source-plugin`
- `--sensor-bundle-path /path/to/built-sensor.rsnxplugin`

`test algorithm-bundle` accepts the same sensor input choices while loading the
algorithm itself from `--bundle-path`.

## Scaffold A Sensor Plugin

Run the command from anywhere using the shared tooling CLI:

```bash
nexus-n3-plugin init sensor movella-dot --output-dir /path/to/nexus-n3-plugin-catalog
```

When `--output-dir` points at the shared `nexus-n3-plugin-catalog` workspace, sensor plugins are placed under:

```text
nexus-n3-plugin-catalog/sensors/
```

Example with additional metadata:

```bash
nexus-n3-plugin init sensor movella-dot \
  --output-dir /path/to/nexus-n3-plugin-catalog \
  --manufacturer-id 2182 \
  --sample-type imu
```

This creates the plugin source tree and its isolated `.venv`.

Example output:

```text
nexus-n3-plugin-catalog/
  sensors/
    nexus-n3-sensor-movella-dot/
      .venv/
      pyproject.toml
      plugin.json
      src/
        nexus_n3_sensor_movella_dot/
          plugin.json
          parser.py
          sensor.py
          samples.py
      tests/
      specs/
```

Canonical sensor naming:

```text
repo name:
  nexus-n3-sensor-<plugin-id>

Python package:
  nexus_n3_sensor_<plugin_id>
```

`--package-name` remains available as an override, but the default convention is the expected layout for new sensor plugins.

## Scaffold An Algorithm Plugin

Run the command from anywhere using the shared tooling CLI:

```bash
nexus-n3-plugin init algorithm standard-loading-intensity --output-dir /path/to/nexus-n3-plugin-catalog
```

When `--output-dir` points at the shared `nexus-n3-plugin-catalog` workspace, algorithm plugins are placed under:

```text
nexus-n3-plugin-catalog/algorithms/
```

Intermediate and consolidation executor files are always scaffolded.

By default, their schedules are disabled and the generated executor classes are no-op placeholders.

Use these flags when you want the scaffold to enable those stages in `plugin.json` and `config.yaml` and provide example implementations:

```bash
nexus-n3-plugin init algorithm generic-data-summary \
  --output-dir /path/to/nexus-n3-plugin-catalog \
  --with-intermediate \
  --with-consolidation
```

This creates the plugin source tree and its isolated `.venv`.

Example output:

```text
nexus-n3-plugin-catalog/
  algorithms/
    nexus-n3-algorithm-generic-data-summary/
      .venv/
      pyproject.toml
      plugin.json
      src/
        nexus_n3_algorithm_generic_data_summary/
          plugin.json
          core.py
          core_schema.py
          processing.py
          config.yaml
          intermediate_executor.py
          consolidation_executor.py
      tests/
```

Canonical algorithm naming:

```text
repo name:
  nexus-n3-algorithm-<plugin-id>

Python package:
  nexus_n3_algorithm_<plugin_id>
```

## What `init` Does

The `init` command is responsible for creating a usable plugin development repository.

It should:

```text
1. Create the plugin directory.

2. Write the standard plugin source layout.

3. Write pyproject.toml.

4. Write plugin.json.

5. Write package-level plugin metadata.

6. Write starter tests.

7. Create <plugin-root>/.venv.

8. Install or upgrade pip.

9. Install setuptools, wheel, and build.

10. Install the local Nexus N3 plugin SDK into the plugin .venv.

11. Install the generated plugin package into the plugin .venv.
```

The plugin `.venv` belongs to the plugin.

The tooling `.venv` belongs to the shared CLI.

The CLI should not need to be installed into the plugin `.venv`.

## Plugin Dependencies

Each plugin declares and owns its own dependencies.

Those dependencies should be installed into the plugin's own `.venv`.

For example, an algorithm plugin may need:

```bash
cd /path/to/nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-example
source .venv/bin/activate
python -m pip install numpy scipy
```

A sensor plugin may need different dependencies:

```bash
cd /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-example
source .venv/bin/activate
python -m pip install pydantic
```

Only install the dependencies required by that plugin.

Do not use a shared plugin development environment for multiple plugins.

## Build A Plugin Bundle

The build command produces a Phase 1 `.rsnxplugin` ZIP bundle compatible with the `nexus_n3.plugins` installer in `nexus-n3-core`.

If a bundle with the same filename already exists in the output directory, it
is replaced automatically.

Basic usage:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/plugin \
  --output-dir /path/to/plugin-builds
```

Sensor example:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot \
  --output-dir /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors
```

nexus-n3-plugin build \
  --plugin-root /home/mike/Desktop/apps/dev/nexus-n3-project/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movesense \
  --output-dir /home/mike/Desktop/apps/dev/nexus-n3-project/nexus-n3-plugin-catalog/plugin-builds/sensors

Algorithm example:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-standard-loading-intensity \
  --output-dir /path/to/nexus-n3-plugin-catalog/plugin-builds/algorithms
```

The build command should use the plugin's own environment:

```text
<plugin-root>/.venv
```

It should not depend on whichever virtual environment is active in the shell.

Conceptually:

```text
nexus-n3-plugin build
  -> locate plugin root
  -> locate plugin .venv
  -> use the platform-specific Python in <plugin-root>/.venv
  -> build the plugin wheel
  -> include the SDK wheel
  -> collect bundle artifacts
  -> write .rsnxplugin
```

If the plugin environment is missing or incomplete, the CLI prepares it before
building. Preparation can also be run explicitly:

```bash
nexus-n3-plugin prepare --plugin-root /path/to/plugin
```

## Build Output

Example output:

```text
/path/to/nexus-n3-plugin-catalog/plugin-builds/sensors/
  nexus-n3-sensor-movella-dot-0.1.0.rsnxplugin
```

The `.rsnxplugin` archive is a normal ZIP container.

It contains:

```text
manifest.json
checksums.json
artifacts/
  plugin wheel
  SDK wheel
metadata/
  optional copied metadata
```

Depending on the plugin type, metadata may include:

* sensor spec files
* algorithm config files
* other plugin-declared metadata

## Dependency Bundling

Each plugin `.venv` is the source of truth for that plugin's dependency set.

This avoids dependency conflicts between plugins.

A plugin with one version of a dependency and another plugin with a different version should be able to build independently because each has its own environment.

The bundle process should support two modes.

### Source Bundle / Runtime-Resolved Dependencies

The bundle includes:

```text
- plugin wheel
- SDK wheel
- manifest
- checksums
- metadata
```

Third-party dependencies are expected to be resolved by the target runtime environment.

### Dependency-Complete Bundle

The bundle includes:

```text
- plugin wheel
- SDK wheel
- third-party dependency wheels
- manifest
- checksums
- metadata
```

This is preferred for offline or controlled deployments.

Expected command:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/plugin \
  --output-dir /path/to/plugin-builds \
  --include-dependencies
```

When the build host and deploy host differ, target the deployment runtime
explicitly. For a Raspberry Pi 5 deployment using Python 3.12:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/plugin \
  --output-dir /path/to/plugin-builds \
  --include-dependencies \
  --target-platform manylinux2014_aarch64 \
  --target-python-version 3.12 \
  --target-implementation cp \
  --target-abi cp312
```

Manual artifact inclusion should remain supported:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/plugin \
  --output-dir /path/to/plugin-builds \
  --artifact /path/to/dist/numpy.whl \
  --artifact /path/to/dist/scipy.whl
```

## SDK Handling

Generated plugins use `nexus-n3-plugin-sdk` contracts for base classes and shared types.

During `init`, the plugin `.venv` should install the SDK from the local tooling checkout.

During bundle creation, the CLI should include an SDK wheel when it can resolve the SDK source.

If needed, point explicitly at the SDK source:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/plugin \
  --output-dir /path/to/plugin-builds \
  --sdk-root /path/to/nexus-n3-plugin-tooling/packages/sdk
```

Use `--no-sdk` only when you intentionally do not want the SDK wheel included.

## Install A Built Bundle Into Nexus N3 OS

After building a bundle, install it from `nexus-n3-core`:

```bash
cd /path/to/nexus-n3-core

python -m nexus_n3.plugins install \
  /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors/nexus-n3-sensor-movella-dot-0.1.0.rsnxplugin
```

For local development against `nexus-n3-plugin-catalog`, `nexus-n3-core` also provides:

```bash
python -m nexus_n3.plugins install-dev \
  --nexus-n3-plugin-catalog-root /path/to/nexus-n3-plugin-catalog \
  --plugin movella-dot
```

List local development plugins:

```bash
python -m nexus_n3.plugins install-dev-list
```

`nexus-n3-plugin-tooling` builds bundles.

`nexus-n3-core` installs and runs bundles.

## Generated Plugin Contract

Generated plugins use:

* a `pyproject.toml` build definition
* a root-level `plugin.json` manifest for source review
* a packaged `src/<package>/plugin.json` manifest included in the built wheel
* a `src/` package layout
* `nexus-n3-plugin-sdk` contracts for base classes and shared types
* Python entry points for future runtime discovery

Current entry point groups are:

```text
nexus_n3.sensors
nexus_n3.algorithms
```

## Algorithm Plugin Contract

Algorithm plugins may include:

* core processing code
* schema definitions
* processing helpers
* intermediate executor
* consolidation executor
* plugin config

Executor file presence is not the capability contract.

Runtime support for intermediate and consolidation stages is declared by:

```text
plugin.json
config.yaml
```

For example:

```text
plugin.json:
  supports_intermediate
  supports_consolidation

config.yaml:
  schedules.intermediate.enabled
  schedules.consolidated.enabled
```

`nexus-n3-core` should use those declarations when deciding whether to schedule or load optional executor stages.

## Sensor Plugin Contract

Sensor plugins may declare and implement a `consume_input` hook when they accept forwarded data from another sensor plugin through the runtime.

Algorithm plugins already receive per-sensor data through their existing sample pipeline.

Sensor plugins should not need to depend directly on BLE backends such as `bleak` for normal packaging.

Runtime BLE operations belong to `nexus-n3-core` in deployment and to the CLI harness adapter layer during source-mode plugin testing.

## Test A Sensor Plugin

To validate a sensor plugin while developing it, without booting the full server:

```bash
nexus-n3-plugin test sensor \
  --plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-example
```

The harness should use the plugin's own `.venv`.

The harness:

```text
- loads the plugin from src/
- resolves the manifest entry point
- instantiates the sensor class
- uses the SDK sensor manager with the selected BLE adapter backend
- exercises discovery, connection, streaming, stop, and disconnect
- captures emitted data to CSV for developer inspection
- probes the optional consume_input hook
```

If the plugin `.venv` is missing, the plugin should be recreated or the environment should be repaired.

The normal path is for `nexus-n3-plugin init` to create the `.venv`.

## Reference Plugin Examples

Current reference migration plugins:

```text
Sensor:
  nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot

Algorithm:
  nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-standard-loading-intensity
```

Build sensor example:

```bash
nexus-n3-plugin build \
  --plugin-root ./nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot \
  --output-dir ./nexus-n3-plugin-catalog/plugin-builds/sensors
```

Build algorithm example:

```bash
nexus-n3-plugin build \
  --plugin-root ./nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-standard-loading-intensity \
  --output-dir ./nexus-n3-plugin-catalog/plugin-builds/algorithms
```

Expected outputs:

```text
nexus-n3-plugin-catalog/plugin-builds/sensors/
  nexus-n3-sensor-movella-dot-0.1.0.rsnxplugin

nexus-n3-plugin-catalog/plugin-builds/algorithms/
  nexus-n3-algorithm-standard-loading-intensity-0.1.0.rsnxplugin
```

## Developer Commands Summary

Install tooling once:

```bash
cd /path/to/nexus-n3-plugin-tooling
./install.sh
source .venv/bin/activate
```

Scaffold a sensor plugin:

```bash
nexus-n3-plugin init sensor movella-dot --output-dir /path/to/nexus-n3-plugin-catalog
```

Scaffold an algorithm plugin:

```bash
nexus-n3-plugin init algorithm standard-loading-intensity --output-dir /path/to/nexus-n3-plugin-catalog
```

Build a sensor plugin:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/nexus-n3-plugin-catalog/sensors/nexus-n3-sensor-movella-dot \
  --output-dir /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors
```

Build an algorithm plugin:

```bash
nexus-n3-plugin build \
  --plugin-root /path/to/nexus-n3-plugin-catalog/algorithms/nexus-n3-algorithm-standard-loading-intensity \
  --output-dir /path/to/nexus-n3-plugin-catalog/plugin-builds/algorithms
```

Install bundle into Nexus N3 OS:

```bash
cd /path/to/nexus-n3-core

python -m nexus_n3.plugins install \
  /path/to/nexus-n3-plugin-catalog/plugin-builds/sensors/nexus-n3-sensor-movella-dot-0.1.0.rsnxplugin
```

## Important Design Rule

Do not require this:

```bash
cd /path/to/plugin
source .venv/bin/activate
pip install -e /path/to/nexus-n3-plugin-tooling/packages/cli
```

The plugin `.venv` is for the plugin and its dependencies.

The tooling `.venv` is for the shared CLI.

The CLI should call into the plugin `.venv` when it needs to build or test the plugin.

## Development Notes

The SDK and CLI packages currently use `setup.py` because editable local installs are the main development workflow.

Scaffolded plugin projects use `pyproject.toml`.

The build path should avoid relying on the caller's active Python environment.

Preferred behavior:

```text
nexus-n3-plugin build
  uses the platform-specific Python in <plugin-root>/.venv
```

Avoid this behavior:

```text
nexus-n3-plugin build
  uses whichever python happens to be active in the shell
```

This makes the build process more predictable and keeps plugin dependencies isolated.

## Files Not To Commit

Do not commit local runtime artifacts.

Examples:

```text
.venv/
__pycache__/
*.pyc
build/
dist/
*.egg-info/
plugin-build/
*.rsnxplugin
```

These should be covered by `.gitignore`.

## Security

This repository should not contain:

* device credentials
* cloud connection strings
* SAS tokens
* API keys
* private keys
* site-specific configuration
* customer-specific deployment configuration

If a generated plugin needs deployment credentials or runtime configuration, provide those through the target runtime environment rather than committing them to the plugin source repository.

## Ownership Boundary

```text
nexus-n3-plugin-tooling
  creates, prepares, validates, and builds plugins

plugin repositories
  contain plugin code, manifests, configs, tests, and isolated dependencies

nexus-n3-core
  installs, catalogs, discovers, and runs plugins
```

This boundary should stay clear.

The tooling should make plugin development easy.

The plugin environment should keep dependencies isolated.

The runtime should consume built bundles.
