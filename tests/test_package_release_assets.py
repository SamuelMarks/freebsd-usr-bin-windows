"""Unit tests for ``scripts.package_release_assets``."""

from __future__ import annotations

import runpy
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.package_release_assets import (
    LF,
    ReleaseConfig,
    _locate_bin_subdir,
    _locate_lib_subdir,
    main,
    package_release_assets,
)


def test_package_release_assets_full_matrix_and_sdk(tmp_path: Path) -> None:
    """Verify Windows X64/X86/ARM64 + DOS suite, SDK, per-binary zips, and SHA256SUMS.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "LICENSE-MIT").write_text(f"MIT{LF}", encoding="utf-8")

    # X64 build with bin/Release, lib/Release, Section 3 headers, and pre-built .msi
    win_x64 = tmp_path / "build_x64"
    (win_x64 / "bin" / "Release").mkdir(parents=True)
    (win_x64 / "lib" / "Release").mkdir(parents=True)
    s3_inc = win_x64 / "freebsd_generated" / "section3" / "include" / "sys"
    s3_inc.mkdir(parents=True)
    (s3_inc / "sbuf.h").write_text(f"struct sbuf;{LF}", encoding="utf-8")
    (win_x64 / "bin" / "Release" / "freebsd-usr-bin.exe").write_bytes(b"MC64")
    (win_x64 / "bin" / "Release" / "printf.exe").write_bytes(b"PF64")
    (win_x64 / "bin" / "Release" / "fbsd_xo.dll").write_bytes(b"DLL64")
    (win_x64 / "lib" / "Release" / "fbsd_xo.lib").write_bytes(b"LIB64")
    (win_x64 / "lib" / "Release" / "subdir_ignored").mkdir()
    (win_x64 / "freebsd-usr-bin-15.0.0-X64.msi").write_bytes(b"MSI64")
    (win_x64 / "freebsd-usr-bin-15.0.0-X64.zip").write_bytes(b"PREBUILTZIP64")

    # ARM64 build with flat bin/ and duplicate sbuf.h to cover seen_arc deduplication
    win_arm64 = tmp_path / "build_arm64"
    (win_arm64 / "bin").mkdir(parents=True)
    (win_arm64 / "bin" / "printf.exe").write_bytes(b"PFARM")
    (win_arm64 / "bin" / "subdir_in_bin").mkdir()
    s3_inc_arm = win_arm64 / "freebsd_generated" / "section3" / "include" / "sys"
    s3_inc_arm.mkdir(parents=True)
    (s3_inc_arm / "sbuf.h").write_text(f"struct sbuf;{LF}", encoding="utf-8")

    # DOS build with flat root executables + DOS32A.EXE
    dos_dir = tmp_path / "build_dos"
    dos_dir.mkdir()
    (dos_dir / "freebsd-usr-bin.exe").write_bytes(b"MCDOS")
    (dos_dir / "printf.exe").write_bytes(b"PFDOS")
    (dos_dir / "DOS32A.EXE").write_bytes(b"EXTENDER")

    # Per-binary CMakeLists directory
    pb_dir = tmp_path / "per_binary"
    (pb_dir / "printf").mkdir(parents=True)
    (pb_dir / "printf" / "CMakeLists.txt").write_text(f"# printf cmake{LF}", encoding="utf-8")

    out_dir = tmp_path / "release_out"
    rc = main(
        [
            "--version",
            "v15.0.0",
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(out_dir),
            "--win-x64",
            str(win_x64),
            "--win-x86",
            str(tmp_path / "missing_x86"),
            "--win-arm64",
            str(win_arm64),
            "--dos-dir",
            str(dos_dir),
            "--per-binary-cmake-dir",
            str(pb_dir),
        ]
    )
    assert rc == 0

    names = {p.name for p in out_dir.iterdir()}
    assert "freebsd-usr-bin-15.0.0-X64.msi" in names
    assert "freebsd-usr-bin-15.0.0-X64.zip" in names
    assert "freebsd-usr-bin-15.0.0-X64.exe" in names
    assert "freebsd-usr-bin-15.0.0-dos32.zip" in names
    assert "freebsd-usr-bin-15.0.0-section3-sdk.zip" in names
    assert "printf-15.0.0-windows.zip" in names
    assert "printf-15.0.0-dos32.zip" in names
    assert "SHA256SUMS.txt" in names

    with zipfile.ZipFile(out_dir / "printf-15.0.0-windows.zip") as zf:
        z_members = set(zf.namelist())
        assert "x64/printf.exe" in z_members
        assert "x64/fbsd_xo.dll" in z_members
        assert "arm64/printf.exe" in z_members
        assert "CMakeLists.txt" in z_members
        assert "LICENSE-MIT" in z_members

    with zipfile.ZipFile(out_dir / "printf-15.0.0-dos32.zip") as zf_dos:
        dos_members = set(zf_dos.namelist())
        assert "printf.exe" in dos_members
        assert "DOS32A.EXE" in dos_members


def test_package_release_assets_edge_cases_and_limit_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify empty inputs, helper fallbacks, CLI error exit, and ``__main__`` execution.

    Args:
        tmp_path: Pytest temporary directory fixture.
        capsys: Pytest stdout/stderr capture fixture.
    """
    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir()
    assert _locate_bin_subdir(empty_repo) == empty_repo
    assert _locate_lib_subdir(empty_repo) is None

    # Empty build inputs (no SDK, no binaries, file-not-dir bin_dir)
    weird_win = tmp_path / "weird_win"
    weird_win.mkdir()
    (weird_win / "printf_no_cmakelists.exe").write_bytes(b"X")
    weird_dos = tmp_path / "weird_dos"
    weird_dos.mkdir()
    (weird_dos / "printf.exe").write_bytes(b"D")

    cfg_min = ReleaseConfig(
        version="15.0.0",
        repo_root=empty_repo,
        output_dir=tmp_path / "out_min",
        windows_dirs={"X64": weird_win},
        dos_dir=weird_dos,
        per_binary_cmake_dir=tmp_path / "no_pb",
    )
    assets_min = package_release_assets(cfg_min)
    assert any(p.name == "SHA256SUMS.txt" for p in assets_min)

    # Also test completely empty config (no windows_dirs, no dos_dir)
    cfg_empty = ReleaseConfig(
        version="15.0.0",
        repo_root=empty_repo,
        output_dir=tmp_path / "out_empty",
        windows_dirs={},
        dos_dir=None,
    )
    assets_empty = package_release_assets(cfg_empty)
    assert len(assets_empty) == 1

    # Cover case where bin_dir does not exist inside a non-existent symlink/file build_root
    fake_file = tmp_path / "not_a_dir"
    fake_file.write_text("x", encoding="utf-8")
    cfg_nodir = ReleaseConfig(
        version="15.0.0",
        repo_root=empty_repo,
        output_dir=tmp_path / "out_nodir",
        windows_dirs={"X64": fake_file},
        dos_dir=fake_file,
    )
    assert len(package_release_assets(cfg_nodir)) == 1

    assert (
        main(["--repo-root", str(empty_repo), "--output-dir", str(tmp_path / "out_no_flags")]) == 0
    )

    # Exceeding max_assets raises PACKAGE_ASSET_LIMIT_EXCEEDED
    cfg_limit = ReleaseConfig(
        version="15.0.0",
        repo_root=empty_repo,
        output_dir=tmp_path / "out_limit",
        windows_dirs={"X64": weird_win},
        max_assets=1,
    )
    with pytest.raises(FreeBsdPortError) as exc_lim:
        package_release_assets(cfg_limit)
    assert exc_lim.value.code is ErrorCode.PACKAGE_ASSET_LIMIT_EXCEEDED

    # CLI failure via __main__
    old_argv = sys.argv
    sys.argv = [
        "package_release_assets.py",
        "--repo-root",
        str(empty_repo),
        "--output-dir",
        str(tmp_path / "out_cli_err"),
        "--win-x64",
        str(weird_win),
        "--max-assets",
        "1",
    ]
    try:
        script_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "package_release_assets.py"
        )
        with pytest.raises(SystemExit) as sys_exc:
            runpy.run_path(str(script_path), run_name="__main__")
        assert sys_exc.value.code == 1
    finally:
        sys.argv = old_argv
    assert "PACKAGE_ASSET_LIMIT_EXCEEDED" in capsys.readouterr().err
