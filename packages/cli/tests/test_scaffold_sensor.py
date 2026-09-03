from pathlib import Path

from nexus_n3_plugin_cli.scaffold.sensor import scaffold_sensor_plugin


def test_sensor_scaffold_includes_parser_module(tmp_path: Path) -> None:
    plugin_root = scaffold_sensor_plugin(
        plugin_id="example",
        display_name=None,
        output_dir=tmp_path,
        adapter="BLE",
        sample_type="imu",
        package_name=None,
        manufacturer_id=0,
        force=False,
    )

    parser_module = plugin_root / "src" / "nexus_n3_sensor_example" / "parser.py"

    assert parser_module.is_file()
    assert "def parse_packet(packet: bytes):" in parser_module.read_text(encoding="utf-8")
