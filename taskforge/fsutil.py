"""File helpers that behave the same on Windows, macOS and Linux.

Everything TaskForge writes may end up inside a Linux container (shell scripts, patches, tests, Dockerfiles),
so it must be UTF-8 with LF line endings. Python's default text mode on Windows writes CRLF and uses the
legacy code page, which breaks `#!/bin/bash` scripts and `git apply`.
"""
from __future__ import annotations

from pathlib import Path


def write_lf(path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def copy_lf(src, dst) -> None:
    """Copy a text file, normalising CRLF to LF."""
    data = Path(src).read_bytes().replace(b"\r\n", b"\n")
    p = Path(dst)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
