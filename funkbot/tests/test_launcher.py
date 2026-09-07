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


# ------------------------------------------------------------------ health cost

def test_quick_health_does_not_run_the_test_suite():
    """The UI polls status every 20s; running pytest there pinned a core."""
    import time

    import verify

    started = time.time()
    report = verify.health()
    assert time.time() - started < 2.0
    assert "tests" not in report          # syntax + imports only
    assert report.startswith("HEALTHY")


def test_full_health_is_cached(monkeypatch):
    """Never call health(full=True) for real from inside this suite — it shells
    out to pytest, which re-enters the suite and hangs. Stub the checks."""
    import verify

    calls = []

    def fake_checks(*a, **k):
        calls.append(1)
        return True, "[PASS] stub"

    monkeypatch.setattr(verify, "run_checks", fake_checks)
    verify._LAST_FULL.clear()
    verify.health(full=True)
    verify.health(full=True)
    assert len(calls) == 1                       # second call served from cache
    verify._LAST_FULL.clear()


def test_a_check_running_inside_a_check_does_not_re_enter_pytest(monkeypatch):
    """A self-edit made from inside the suite must not shell out to pytest again."""
    import verify

    monkeypatch.setenv(verify.IN_CHECK, "1")
    ran = []
    monkeypatch.setattr(verify.subprocess, "run",
                        lambda cmd, **k: ran.append(cmd) or type(
                            "P", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    verify.run_checks()
    assert not any("pytest" in " ".join(c) for c in ran)


# ------------------------------------------------------------------ data dir

def test_portable_build_keeps_data_beside_the_exe(monkeypatch, tmp_path):
    import launcher

    monkeypatch.setattr(launcher, "BUNDLED", True)
    monkeypatch.setattr(launcher, "BESIDE_EXE", str(tmp_path))
    assert launcher.default_data_dir() == str(tmp_path / "data")


def test_read_only_install_falls_back_to_per_user_data(monkeypatch, tmp_path):
    """Installed under Program Files the exe directory is not writable;
    silently failing to save memory there would be worse than relocating."""
    import launcher

    monkeypatch.setattr(launcher, "BUNDLED", True)
    monkeypatch.setattr(launcher, "BESIDE_EXE", "C:\\Program Files\\FunkBot")
    monkeypatch.setattr(launcher, "_writable", lambda path: False)
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert launcher.default_data_dir() == str(tmp_path / "FunkBot" / "data")


def test_source_runs_are_unaffected(monkeypatch, tmp_path):
    import launcher

    monkeypatch.setattr(launcher, "BUNDLED", False)
    monkeypatch.setattr(launcher, "BESIDE_EXE", str(tmp_path))
    monkeypatch.setattr(launcher, "_writable", lambda path: False)
    assert launcher.default_data_dir() == str(tmp_path / "data")


# ------------------------------------------------------------------ packaged builds

def test_packaged_health_is_not_reported_as_broken(monkeypatch):
    """A frozen build has no source tree to compile; that is not a fault."""
    import verify

    monkeypatch.setattr(verify, "PACKAGED", True)
    report = verify.health()
    assert report.startswith("PACKAGED")
    assert "BROKEN" not in report


def test_packaged_build_refuses_to_self_edit(monkeypatch):
    import verify

    monkeypatch.setattr(verify, "PACKAGED", True)
    out = verify.safe_self_edit("x", lambda: "should not run")
    assert "packaged build" in out


def test_packaged_selfmod_write_reports_instead_of_pretending(monkeypatch):
    import selfmod

    monkeypatch.setattr(selfmod, "PACKAGED", True)
    assert "CANNOT EDIT" in selfmod.write_own_file("probe.py", "x = 1\n")


def test_checks_use_the_running_interpreter_not_a_bare_name():
    """Hardcoding "python3" made every check fail on Windows, where that name
    hits the Microsoft Store stub and reports "Python was not found"."""
    import sys

    import verify

    for name, cmd in verify.CHECKS:
        assert cmd[0] == sys.executable, f"{name} check must re-invoke sys.executable"
