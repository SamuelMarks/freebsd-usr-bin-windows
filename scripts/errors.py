"""Strongly typed domain error codes and exception hierarchy for ``freebsd-usr-bin-windows``.

Provides a single unified ``ErrorCode`` enumeration and ``FreeBsdPortError``
exception class used across all build-manifest, code-generation, source-staging,
CMake-emission, release-packaging, and test-runner scripts.
"""

from __future__ import annotations

import enum
from pathlib import Path


class ErrorCode(enum.Enum):
    """Canonical error codes for ``freebsd-usr-bin-windows`` Python tooling.

    Attributes:
        SOURCE_TREE_NOT_FOUND: Upstream ``freebsd-src`` or required path is missing.
        MAKEFILE_PARSE_ERROR: FreeBSD ``Makefile`` syntax or directive could not be parsed.
        UNRESOLVED_SOURCES: Expected C/C++ source files for a target could not be resolved.
        PATCH_APPLY_ERROR: Unified diff ``.patch`` file is malformed or unsafe.
        PATCH_HUNK_MISMATCH: Unified diff hunk context did not match upstream file content.
        UPSTREAM_TREE_DIRTY: ``../freebsd-src`` has uncommitted modifications or untracked files.
        CODEGEN_FAILURE: Build-time C/header/coverage code generation failed.
        CMAKE_EMIT_ERROR: Out-of-tree ``CMakeLists.txt`` emission failed validation.
        PACKAGE_ASSET_LIMIT_EXCEEDED: Release asset count exceeded GitHub Releases' safe ceiling.
        TEST_EXECUTION_FAILURE: Functional binary or coverage verification check failed.
    """

    SOURCE_TREE_NOT_FOUND = "SOURCE_TREE_NOT_FOUND"
    MAKEFILE_PARSE_ERROR = "MAKEFILE_PARSE_ERROR"
    UNRESOLVED_SOURCES = "UNRESOLVED_SOURCES"
    PATCH_APPLY_ERROR = "PATCH_APPLY_ERROR"
    PATCH_HUNK_MISMATCH = "PATCH_HUNK_MISMATCH"
    UPSTREAM_TREE_DIRTY = "UPSTREAM_TREE_DIRTY"
    CODEGEN_FAILURE = "CODEGEN_FAILURE"
    CMAKE_EMIT_ERROR = "CMAKE_EMIT_ERROR"
    PACKAGE_ASSET_LIMIT_EXCEEDED = "PACKAGE_ASSET_LIMIT_EXCEEDED"
    TEST_EXECUTION_FAILURE = "TEST_EXECUTION_FAILURE"


class FreeBsdPortError(Exception):
    """Domain exception carrying a structured ``ErrorCode`` and optional filesystem path.

    Attributes:
        code: Typed ``ErrorCode`` categorizing the failure.
        message: Human-readable diagnostic description.
        path: Optional filesystem ``Path`` associated with the error.
    """

    code: ErrorCode
    message: str
    path: Path | None

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        path: Path | None = None,
    ) -> None:
        """Initialize a ``FreeBsdPortError``.

        Args:
            code: Typed ``ErrorCode`` categorizing the failure.
            message: Human-readable diagnostic description.
            path: Optional filesystem ``Path`` associated with the error.
        """
        self.code = code
        self.message = message
        self.path = path
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the canonical string representation of this error.

        Returns:
            Deterministic diagnostic string including error code and optional path.
        """
        if self.path is not None:
            return f"[{self.code.value}] {self.message}: {self.path}"
        return f"[{self.code.value}] {self.message}"

    def __str__(self) -> str:
        """Return the deterministic string representation of this error.

        Returns:
            Formatted error string.
        """
        return self._format_message()
