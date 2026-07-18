import sys
from unittest.mock import patch


def _fresh_utils():
    sys.modules.pop("utils", None)
    import core.utils as utils
    return utils


def test_get_base_dir_not_frozen():
    u = _fresh_utils()
    result = u.get_base_dir()
    assert (result / "src").exists()


def test_get_base_dir_frozen(tmp_path):
    sys.modules.pop("utils", None)
    fake_exe = tmp_path / "app.exe"
    fake_exe.touch()
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", str(fake_exe)):
        import core.utils as utils
        result = utils.get_base_dir()
    assert result == tmp_path


def test_get_path_absolute_passthrough(tmp_path):
    from core.utils import get_path
    result = get_path(str(tmp_path))
    assert result == tmp_path.resolve()


def test_get_path_relative_uses_base():
    from core.utils import get_path, BASE_DIR
    result = get_path("config/config.json")
    assert result == (BASE_DIR / "config" / "config.json").resolve()


def test_get_path_accepts_path_object(tmp_path):
    from core.utils import get_path
    result = get_path(tmp_path)
    assert result == tmp_path.resolve()
