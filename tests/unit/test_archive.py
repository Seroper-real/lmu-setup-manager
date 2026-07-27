import hashlib

import pytest

from core.archive import sha256_file


@pytest.mark.parametrize("payload", [
    pytest.param(b"hello world", id="small_single_chunk"),
    pytest.param(b"x" * (1024 * 1024 * 3 + 17), id="spans_multiple_chunk_reads"),
])
def test_sha256_file_matches_known_digest(tmp_path, payload):
    p = tmp_path / "a.bin"
    p.write_bytes(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_differs_for_different_content(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"version one")
    b.write_bytes(b"version two")
    assert sha256_file(a) != sha256_file(b)


def test_sha256_file_same_content_different_names_matches(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "renamed.bin"
    a.write_bytes(b"identical content")
    b.write_bytes(b"identical content")
    assert sha256_file(a) == sha256_file(b)
