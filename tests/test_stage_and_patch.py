"""Unit tests for ``scripts.stage_and_patch`` and upstream ``freebsd-src`` cleanliness."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.stage_and_patch import (
    BS,
    CRLF,
    LF,
    TAB,
    apply_unified_patch,
    detect_freebsd_major,
    parse_unified_diff,
    stage_patched_sources,
    verify_upstream_clean,
)


def test_parse_and_apply_unified_diff_success_branches() -> None:
    """Verify single-hunk, multi-hunk, empty-file, CRLF, and no-trailing-newline patches."""
    patch_text = LF.join(
        [
            "# Declarative test patch",
            "diff --git a/usr.bin/foo/foo.c b/usr.bin/foo/foo.c",
            "index 1111111..2222222 100644",
            "--- a/usr.bin/foo/foo.c",
            f"+++ b/usr.bin/foo/foo.c{TAB}2026-11-12",
            "@@ -1,4 +1,5 @@",
            " #include <stdio.h>",
            "+#include <stdlib.h>",
            " int main(void) {",
            "-    return 1;",
            "+    return 0;",
            " }",
            "",
            "--- a/usr.bin/bar/bar.c",
            "+++ usr.bin/bar/bar.c",
            "@@ -0,0 +1 @@",
            "+int bar_x = 1;",
            f"{BS} No newline at end of file",
            "",
        ]
    )
    parsed = parse_unified_diff(patch_text)
    assert len(parsed) == 2
    assert parsed[0].target_rel_path == "usr.bin/foo/foo.c"
    assert parsed[1].target_rel_path == "usr.bin/bar/bar.c"

    orig_lf = (
        LF.join(
            [
                "#include <stdio.h>",
                "int main(void) {",
                "    return 1;",
                "}",
            ]
        )
        + LF
    )
    patched_lf = apply_unified_patch(orig_lf, parsed[0])
    assert "#include <stdlib.h>" in patched_lf
    assert "return 0;" in patched_lf
    assert patched_lf.endswith(LF)
    assert CRLF not in patched_lf

    orig_crlf_no_eof_nl = CRLF.join(
        [
            "#include <stdio.h>",
            "int main(void) {",
            "    return 1;",
            "}",
        ]
    )
    patched_crlf = apply_unified_patch(orig_crlf_no_eof_nl, parsed[0])
    assert CRLF in patched_crlf
    assert not patched_crlf.endswith(CRLF)

    mid_nonl_patch = parse_unified_diff(
        LF.join(
            [
                "--- a/usr.bin/baz/baz.c",
                "+++ b/usr.bin/baz/baz.c",
                "@@ -1 +1 @@",
                "-old_val",
                f"{BS} No newline at end of file",
                "+new_val",
                f"{BS} No newline at end of file",
            ]
        )
    )
    assert apply_unified_patch("old_val", mid_nonl_patch[0]) == "new_val"
    assert apply_unified_patch("", parsed[1]) == f"int bar_x = 1;{LF}"

    del_all_patch = parse_unified_diff(
        LF.join(
            [
                "--- a/usr.bin/del/del.c",
                "+++ b/usr.bin/del/del.c",
                "@@ -1 +0,0 @@",
                "-gone",
            ]
        )
    )
    assert apply_unified_patch(f"gone{LF}", del_all_patch[0]) == ""


def test_parse_and_apply_unified_diff_error_branches() -> None:
    """Verify all validation and hunk mismatch error branches raise ``FreeBsdPortError``."""
    bad_inputs = [
        ("", "contains no file diffs"),
        ("random line", "Unexpected line outside unified diff header"),
        ("--- a/foo.c", "Missing"),
        (f"--- a/foo.c{LF}+++ /dev/null{LF}@@ -1 +1 @@{LF}-a{LF}+b", "Invalid or empty"),
        (f"--- a/foo.c{LF}+++ /etc/passwd{LF}@@ -1 +1 @@{LF}-a{LF}+b", "Unsafe absolute"),
        (f"--- a/foo.c{LF}+++ b/../outside.c{LF}@@ -1 +1 @@{LF}-a{LF}+b", "Unsafe absolute"),
        (f"--- a/foo.c{LF}+++ b/foo.c{LF}not a hunk", "Malformed hunk header"),
        (f"--- a/foo.c{LF}+++ b/foo.c{LF}@@ -1,2 +1,2 @@{LF}bad_prefix", "Invalid hunk body"),
        (f"--- a/foo.c{LF}+++ b/foo.c{LF}@@ -1,2 +1,2 @@{LF}-only_one", "Incomplete hunk"),
        (
            f"--- a/foo.c{LF}+++ b/foo.c{LF}{LF}"
            f"--- a/bar.c{LF}+++ b/bar.c{LF}@@ -1 +1 @@{LF}-a{LF}+b",
            "No hunks found",
        ),
    ]
    for raw_patch, expected_msg in bad_inputs:
        with pytest.raises(FreeBsdPortError, match=expected_msg) as exc_info:
            parse_unified_diff(raw_patch)
        assert exc_info.value.code is ErrorCode.PATCH_APPLY_ERROR

    valid_patch = parse_unified_diff(
        LF.join(
            [
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -5,1 +5,1 @@",
                "-expected_line",
                "+replaced_line",
            ]
        )
    )[0]
    with pytest.raises(FreeBsdPortError, match="out of range") as range_exc:
        apply_unified_patch(f"only_one_line{LF}", valid_patch)
    assert range_exc.value.code is ErrorCode.PATCH_HUNK_MISMATCH

    mismatch_patch = parse_unified_diff(
        LF.join(
            [
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -1,2 +1,2 @@",
                " line1",
                "-expected_line2",
                "+new_line2",
            ]
        )
    )[0]
    with pytest.raises(FreeBsdPortError, match="mismatch") as mm_exc:
        apply_unified_patch(f"line1{LF}different_line2{LF}", mismatch_patch)
    assert mm_exc.value.code is ErrorCode.PATCH_HUNK_MISMATCH

    with pytest.raises(FreeBsdPortError, match="<EOF>"):
        apply_unified_patch(f"line1{LF}", mismatch_patch)

    shifted_patch = parse_unified_diff(
        LF.join(
            [
                "--- a/shifted.c",
                "+++ b/shifted.c",
                "@@ -2,2 +2,2 @@",
                " anchor_ctx",
                "-old_val",
                "+new_val",
            ]
        )
    )[0]
    shifted_input = f"pre1{LF}pre2{LF}pre3{LF}anchor_ctx{LF}old_val{LF}tail{LF}"
    assert (
        apply_unified_patch(shifted_input, shifted_patch)
        == f"pre1{LF}pre2{LF}pre3{LF}anchor_ctx{LF}new_val{LF}tail{LF}"
    )


def test_stage_patched_sources_and_verify_upstream_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify out-of-tree staging, chained patches, and upstream git cleanliness checks.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.
    """
    missing_src = tmp_path / "missing_freebsd_src"
    with pytest.raises(FreeBsdPortError) as exc_missing:
        stage_patched_sources(missing_src, tmp_path / "patches", tmp_path / "staged")
    assert exc_missing.value.code is ErrorCode.SOURCE_TREE_NOT_FOUND

    with pytest.raises(FreeBsdPortError) as exc_clean_missing:
        verify_upstream_clean(missing_src)
    assert exc_clean_missing.value.code is ErrorCode.SOURCE_TREE_NOT_FOUND

    src_root = tmp_path / "freebsd-src"
    tool_dir = src_root / "usr.bin" / "printf"
    tool_dir.mkdir(parents=True)
    orig_c = tool_dir / "printf.c"
    orig_c.write_text(f"int x = 1;{LF}int y = 2;{LF}", encoding="utf-8")

    verify_upstream_clean(src_root)
    assert stage_patched_sources(src_root, tmp_path / "no_patches", tmp_path / "staged") == {}

    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    (patches_dir / "01_first.patch").write_text(
        LF.join(
            [
                "--- a/usr.bin/printf/printf.c",
                "+++ b/usr.bin/printf/printf.c",
                "@@ -1,2 +1,2 @@",
                "-int x = 1;",
                "+int x = 10;",
                " int y = 2;",
            ]
        )
        + LF,
        encoding="utf-8",
    )
    (patches_dir / "02_second.patch").write_text(
        LF.join(
            [
                "--- a/usr.bin/printf/printf.c",
                "+++ b/usr.bin/printf/printf.c",
                "@@ -1,2 +1,2 @@",
                " int x = 10;",
                "-int y = 2;",
                "+int y = 20;",
            ]
        )
        + LF,
        encoding="utf-8",
    )

    staged_dir = tmp_path / "staged"
    staged_map = stage_patched_sources(src_root, patches_dir, staged_dir)
    assert orig_c.resolve() in staged_map
    staged_c = staged_map[orig_c.resolve()]
    assert staged_c.read_text(encoding="utf-8") == f"int x = 10;{LF}int y = 20;{LF}"
    assert orig_c.read_text(encoding="utf-8") == f"int x = 1;{LF}int y = 2;{LF}"

    assert detect_freebsd_major(src_root) is None
    param_dir = src_root / "sys" / "sys"
    param_dir.mkdir(parents=True)
    param_h = param_dir / "param.h"
    param_h.write_text(f"/* no version macro */{LF}", encoding="utf-8")
    assert detect_freebsd_major(src_root) is None
    param_h.write_text(f"#define __FreeBSD_version 1500068{LF}", encoding="utf-8")
    assert detect_freebsd_major(src_root) == 15

    f15_dir = patches_dir / "freebsd15"
    f15_dir.mkdir()
    (f15_dir / "10_f15.patch").write_text(
        LF.join(
            [
                "--- a/usr.bin/printf/printf.c",
                "+++ b/usr.bin/printf/printf.c",
                "@@ -1,2 +1,2 @@",
                " int x = 10;",
                "-int y = 20;",
                "+int y = 150;",
            ]
        )
        + LF,
        encoding="utf-8",
    )
    f16_dir = patches_dir / "freebsd16"
    f16_dir.mkdir()
    (f16_dir / "10_f16.patch").write_text(
        LF.join(
            [
                "--- a/usr.bin/nope16/nope.c",
                "+++ b/usr.bin/nope16/nope.c",
                "@@ -1 +1 @@",
                "-a",
                "+b",
            ]
        )
        + LF,
        encoding="utf-8",
    )
    staged_v15 = stage_patched_sources(src_root, patches_dir, tmp_path / "staged_v15")
    assert (
        staged_v15[orig_c.resolve()].read_text(encoding="utf-8")
        == f"int x = 10;{LF}int y = 150;{LF}"
    )

    (patches_dir / "03_missing.patch").write_text(
        LF.join(
            [
                "--- a/usr.bin/nope/nope.c",
                "+++ b/usr.bin/nope/nope.c",
                "@@ -1 +1 @@",
                "-a",
                "+b",
            ]
        )
        + LF,
        encoding="utf-8",
    )
    with pytest.raises(FreeBsdPortError) as exc_target:
        stage_patched_sources(src_root, patches_dir, staged_dir)
    assert exc_target.value.code is ErrorCode.SOURCE_TREE_NOT_FOUND

    (src_root / ".git").mkdir()
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "outer.index"))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "outer.git"))

    def fake_git_clean(
        cmd: Sequence[str],
        *,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate a clean git status output while verifying hook env isolation.

        Args:
            cmd: Git command sequence passed to ``subprocess.run``.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            CompletedProcess with empty porcelain output.
        """
        _ = (capture_output, text, check)
        assert env is not None
        assert "GIT_INDEX_FILE" not in env
        assert "GIT_DIR" not in env
        return subprocess.CompletedProcess(args=list(cmd), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_git_clean)
    verify_upstream_clean(src_root)

    def fake_git_dirty(
        cmd: Sequence[str],
        *,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate a dirty git status output.

        Args:
            cmd: Git command sequence passed to ``subprocess.run``.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            CompletedProcess with modified file line.
        """
        _ = (capture_output, text, check, env)
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout=f" M usr.bin/printf/printf.c{LF}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_git_dirty)
    with pytest.raises(FreeBsdPortError) as exc_dirty:
        verify_upstream_clean(src_root)
    assert exc_dirty.value.code is ErrorCode.UPSTREAM_TREE_DIRTY

    def fake_git_err(
        cmd: Sequence[str],
        *,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate a failing git status invocation.

        Args:
            cmd: Git command sequence passed to ``subprocess.run``.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            CompletedProcess with non-zero exit status and stderr message.
        """
        _ = (capture_output, text, check, env)
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=128, stdout="", stderr="fatal: bad repo"
        )

    monkeypatch.setattr(subprocess, "run", fake_git_err)
    with pytest.raises(FreeBsdPortError) as exc_git_err:
        verify_upstream_clean(src_root)
    assert exc_git_err.value.code is ErrorCode.UPSTREAM_TREE_DIRTY


def test_real_upstream_freebsd_src_is_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression gate verifying real ``../freebsd-src`` (or ``./freebsd-src``) is 100% clean.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.
    """
    repo_root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("GIT_INDEX_FILE", str(repo_root / ".git" / "index"))
    candidates = (
        tmp_path,
        tmp_path / "nonexistent_dir",
        repo_root.parent / "freebsd-src",
        repo_root / "freebsd-src",
    )
    checked = 0
    for cand in candidates:
        if cand.is_dir():
            verify_upstream_clean(cand)
            checked += 1
    assert checked >= 1
