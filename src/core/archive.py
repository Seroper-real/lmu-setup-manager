import hashlib
import logging
import os
import zipfile
from pathlib import Path
import patoolib
import patoolib.util
from core.utils import get_path

log = logging.getLogger("TrackTitanDownloader")

# patool logs through its own private "patool" logger (see patoolib.log.init_logging),
# not this app's logger, so verbosity=-1 below cannot silence it: that parameter only
# gates util.py's subprocess-command logging, not mime.py's format-detection message.
# On Windows there is normally no `file` executable, so every extraction would log
# "could not find a 'file' executable, falling back to guess mime type by file
# extension" at INFO - harmless, but noisy on every setup. Extension-based detection
# is already patool's fallback and works fine for the .zip/.rar/.7z we handle, so we
# just raise patool's own logger above INFO to drop that specific message.
logging.getLogger("patool").setLevel(logging.WARNING)

if os.name == "nt":
    # patool spawns each extraction tool (unzip/unrar/7z, ...) via
    # subprocess.run and only passes creationflags=CREATE_NO_WINDOW when
    # patoolib.util.run_under_pythonw() is True, i.e. only when the
    # interpreter itself is pythonw.exe. This app's exe is a normal
    # python.exe-style PyInstaller entry point, so every setup extraction
    # flashed a console window open and closed. Force the same no-window
    # behavior unconditionally instead of depending on the entry point.
    patoolib.util.run_under_pythonw = lambda: True

# Archive extensions we recurse into when unpacking nested archives.
ARCHIVE_EXTENSIONS: set[str] = {'.zip', '.rar', '.7z', '.tar', '.gz'}

# Sidecar file embedded in share packages carrying the full TrackTitan API JSON.
METADATA_FILENAME: str = ".metadata.json"


def sha256_file(path: str | Path) -> str:
    """Hex digest of a file's content, read in chunks so large archives don't
    need to be loaded fully into memory."""
    digest = hashlib.sha256()
    with open(get_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_zip_member(zip_path: str | Path, member_name: str) -> bytes:
    """Read a single member from a zip by name, falling back to basename match."""
    with zipfile.ZipFile(get_path(zip_path)) as zf:
        names = zf.namelist()
        if member_name in names:
            return zf.read(member_name)
        for n in names:
            if n.rsplit("/", 1)[-1] == member_name:
                return zf.read(n)
        raise KeyError(f"{member_name} not found in {zip_path}")


def find_files_recursive(base_dir: str | Path, extensions: set[str]) -> list[Path]:
    base_dir = get_path(base_dir)
    extensions = {e.lower() for e in extensions}

    return [
        p for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    ]


def unzip_recursive(zip_path: str | Path, dest_dir: str | Path) -> None:
    zip_path = get_path(zip_path)
    dest_dir = get_path(dest_dir)

    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    dest_dir.mkdir(parents=True, exist_ok=True)

    patoolib.extract_archive(archive=str(zip_path), outdir=str(dest_dir), verbosity=-1)

    archives: list[Path] = find_files_recursive(dest_dir, ARCHIVE_EXTENSIONS)

    for n, archive in enumerate(archives, start=1):
        new_dest_dir = dest_dir / f"ex-{n}"
        new_zip_path = zip_path / archive
        unzip_recursive(new_zip_path, new_dest_dir)
