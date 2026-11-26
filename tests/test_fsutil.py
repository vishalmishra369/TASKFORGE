from taskforge.fsutil import copy_lf, write_lf


def test_write_lf_never_writes_cr_and_creates_parents(tmp_path):
    write_lf(tmp_path / "a/b/c.sh", "#!/bin/bash\nset -e\n")
    assert (tmp_path / "a/b/c.sh").read_bytes() == b"#!/bin/bash\nset -e\n"


def test_write_lf_utf8(tmp_path):
    write_lf(tmp_path / "u.txt", "caf\u00e9 \u2713\n")
    assert (tmp_path / "u.txt").read_bytes() == "caf\u00e9 \u2713\n".encode("utf-8")


def test_copy_lf_normalises_crlf(tmp_path):
    (tmp_path / "src.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    copy_lf(tmp_path / "src.py", tmp_path / "out/dst.py")
    assert (tmp_path / "out/dst.py").read_bytes() == b"a = 1\nb = 2\n"
