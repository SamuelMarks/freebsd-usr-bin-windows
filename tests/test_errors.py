"""Unit tests for ``scripts.errors``."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError


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
