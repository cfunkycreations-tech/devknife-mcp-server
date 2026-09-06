"""The launcher and the icon builder — the double-click path."""

from __future__ import annotations

import pathlib
import socket
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import launcher      # noqa: E402
import make_icon     # noqa: E402


def test_port_probe_detects_a_listening_socket():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert launcher._port_open("127.0.0.1", port) is True
    assert launcher._port_open("127.0.0.1", port) is False


def test_model_probe_reports_down_when_nothing_is_listening():
    assert launcher._model_up("http://127.0.0.1:9/v1") is False


def test_arg_parsing():
    saved = sys.argv
    try:
        sys.argv = ["launcher.py", "--port", "9123"]
        assert launcher._arg("--port", "8800") == "9123"
        assert launcher._arg("--missing", "fallback") == "fallback"
    finally:
        sys.argv = saved


def test_icon_is_a_valid_ico_wrapping_a_png(tmp_path):
    png = make_icon.write_png(make_icon.render(), tmp_path / "i.png")
    make_icon.write_ico(png, tmp_path / "i.ico")

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    blob = (tmp_path / "i.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", blob[:6])
    assert (reserved, kind, count) == (0, 1, 1)
    # ICONDIRENTRY is the 16 bytes after the 6-byte ICONDIR; its last two
    # dwords are the payload size and its offset.
    size, offset = struct.unpack("<II", blob[14:22])
    assert blob[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"
    assert size == len(png)
