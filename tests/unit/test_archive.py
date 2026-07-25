import hashlib

from core.archive import sha256_file


def test_sha256_file_matches_known_digest(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello world")
    assert sha256_file(p) == hashlib.sha256(b"hello world").hexdigest()


def test_sha256_file_correctness_across_multiple_chunks(tmp_path):
    p = tmp_path / "big.bin"
    payload = b"x" * (1024 * 1024 * 3 + 17)  # spans several 1 MiB chunk reads
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
