"""Pieces of the desktop shell that can be tested without Windows: icon, startup entry, app state."""

from types import SimpleNamespace

from core import startup
from core.app_control import AppControl
from core.icon import MODE_COLORS, draw_icon, save_ico


def test_icon_colours_and_pause():
    move = draw_icon(MODE_COLORS["move"], 64)
    scroll = draw_icon(MODE_COLORS["scroll"], 64)
    paused = draw_icon(MODE_COLORS["paused"], 64, paused=True)
    assert move.size == (64, 64) and move.mode == "RGBA"
    assert move.tobytes() != scroll.tobytes() != paused.tobytes()


def test_save_ico(tmp_path):
    path = save_ico(tmp_path / "a" / "airmouse.ico")
    assert path.exists() and path.stat().st_size > 1000


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, root, path, reserved=0, access=0):
        return path

    def CreateKey(self, root, path):
        return path

    def CloseKey(self, key):
        pass

    def QueryValueEx(self, key, name):
        if (key, name) not in self.values:
            raise OSError("missing")
        return self.values[(key, name)], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[(key, name)] = value

    def DeleteValue(self, key, name):
        if (key, name) not in self.values:
            raise OSError("missing")
        del self.values[(key, name)]


def test_start_with_windows_entry():
    reg = FakeWinreg()
    assert not startup.is_enabled(reg)
    startup.enable('"pythonw.exe" "main.py"', reg)
    assert startup.is_enabled(reg)
    assert reg.values[(startup.RUN_KEY, "AirMouse")] == '"pythonw.exe" "main.py"'
    startup.disable(reg)
    assert not startup.is_enabled(reg)
    startup.disable(reg)  # already off: no error


def test_launch_command_points_at_main_py(tmp_path):
    command = startup.launch_command(app_dir=tmp_path, python=str(tmp_path / "python.exe"))
    assert command.endswith(f'"{tmp_path / "main.py"}"')


def test_app_control_status_and_toggles():
    control = AppControl()
    assert control.status_key() == "classic"
    control.processor = SimpleNamespace(
        status=SimpleNamespace(mode=SimpleNamespace(value="scroll")),
        attention_available=True,
        attention_on=True,
        toggle_attention=lambda: setattr(control.processor, "attention_on", False),
    )
    assert control.status_key() == "scroll" and control.status_text() == "SCROLL"
    control.toggle_attention()
    assert not control.attention_on
    control.toggle_pause()
    assert control.status_key() == "paused" and control.status_text() == "Paused"
