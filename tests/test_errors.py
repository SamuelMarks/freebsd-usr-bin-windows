"""Unit tests for ``scripts.errors``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.errors import (
    ErrorCode,
    FreeBsdPortError,
    write_bytes_if_changed,
    write_text_if_changed,
)


def _raise_sample_error() -> None:
    """Raise a sample ``FreeBsdPortError`` for ``pytest.raises`` verification.

    Raises:
        FreeBsdPortError: Always raised with ``ErrorCode.PATCH_HUNK_MISMATCH``.
    """
    raise FreeBsdPortError(ErrorCode.PATCH_HUNK_MISMATCH, "context mismatch")


def test_error_code_members_and_formatting() -> None:
    """Verify all ``ErrorCode`` members and ``FreeBsdPortError`` formatting branches."""
    expected_codes = {
        "SOURCE_TREE_NOT_FOUND",
        "MAKEFILE_PARSE_ERROR",
        "UNRESOLVED_SOURCES",
        "PATCH_APPLY_ERROR",
        "PATCH_HUNK_MISMATCH",
        "UPSTREAM_TREE_DIRTY",
        "CODEGEN_FAILURE",
        "CMAKE_EMIT_ERROR",
        "PACKAGE_ASSET_LIMIT_EXCEEDED",
        "TEST_EXECUTION_FAILURE",
    }
    assert {member.value for member in ErrorCode} == expected_codes

    err_no_path = FreeBsdPortError(ErrorCode.CODEGEN_FAILURE, "failed to emit header")
    assert err_no_path.code is ErrorCode.CODEGEN_FAILURE
    assert err_no_path.message == "failed to emit header"
    assert err_no_path.path is None
    assert str(err_no_path) == "[CODEGEN_FAILURE] failed to emit header"

    sample_path = Path("/tmp/freebsd-src/usr.bin")
    err_with_path = FreeBsdPortError(
        ErrorCode.SOURCE_TREE_NOT_FOUND,
        "missing usr.bin directory",
        path=sample_path,
    )
    assert err_with_path.code is ErrorCode.SOURCE_TREE_NOT_FOUND
    assert err_with_path.path == sample_path
    assert str(err_with_path) == f"[SOURCE_TREE_NOT_FOUND] missing usr.bin directory: {sample_path}"

    with pytest.raises(FreeBsdPortError, match="PATCH_HUNK_MISMATCH"):
        _raise_sample_error()


def test_write_if_changed_helpers_preserve_mtime(tmp_path: Path) -> None:
    """Verify ``write_text_if_changed`` and ``write_bytes_if_changed`` across all branches.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    txt_file = tmp_path / "nested" / "header.h"
    assert write_text_if_changed(txt_file, "#define FOO 1\n") is True
    os.utime(txt_file, (1_700_000_000, 1_700_000_000))
    assert write_text_if_changed(txt_file, "#define FOO 1\n") is False
    assert int(txt_file.stat().st_mtime) == 1_700_000_000
    assert write_text_if_changed(txt_file, "#define FOO 2\n") is True
    assert txt_file.read_text(encoding="utf-8") == "#define FOO 2\n"

    bin_file = tmp_path / "nested_bin" / "blob.bin"
    assert write_bytes_if_changed(bin_file, b"\x00\x01") is True
    os.utime(bin_file, (1_700_000_000, 1_700_000_000))
    assert write_bytes_if_changed(bin_file, b"\x00\x01") is False
    assert int(bin_file.stat().st_mtime) == 1_700_000_000
    assert write_bytes_if_changed(bin_file, b"\x00\x02") is True
    assert bin_file.read_bytes() == b"\x00\x02"
