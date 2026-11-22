"""Unit and standalone CMake build tests for ``scripts.per_binary_cmake``."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.parse_freebsd_usr_bin import BinarySpec
from scripts.per_binary_cmake import (
    LF,
    emit_all_per_binary_cmake,
    generate_per_binary_cmake,
    render_per_binary_cmakelists,
)
from scripts.script_applets import emit_all_script_applets
from scripts.stage_and_patch import sanitized_git_env


def test_render_per_binary_cmakelists_variants_and_errors(tmp_path: Path) -> None:
    """Verify C, C++, Yacc/Lex, Section 3 DLL, and alias link ``CMakeLists.txt`` generation.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    empty_spec = BinarySpec(
        prog="empty",
        subdir="empty",
        tier=1,
        is_cxx=False,
        sources=(),
        yacc_sources=(),
        lex_sources=(),
        generated_headers=(),
        include_dirs=(),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    with pytest.raises(FreeBsdPortError) as exc_info:
        render_per_binary_cmakelists(empty_spec, tmp_path, tmp_path, tmp_path / "gen")
    assert exc_info.value.code is ErrorCode.CMAKE_EMIT_ERROR

    rich_c = tmp_path / "ar.c"
    rich_y = tmp_path / "acpyacc.y"
    rich_l = tmp_path / "acplex.l"
    for p in (rich_c, rich_y, rich_l):
        p.write_text(f"int x;{LF}", encoding="utf-8")

    rich_spec = BinarySpec(
        prog="ar",
        subdir="ar",
        tier=1,
        is_cxx=True,
        sources=(str(rich_c),),
        yacc_sources=(str(rich_y),),
        lex_sources=(str(rich_l),),
        generated_headers=("y.tab.h",),
        include_dirs=(str(tmp_path),),
        compile_defs=("BSD_AR=1", "MAGIC='\"/usr/share/misc/magic\"'", r"RAW\ESC"),
        raw_libs=("archive", "elftc"),
        section3_targets=("fbsd_libarchive", "fbsd_libelftc"),
        links=("ranlib",),
        scripts=(),
    )
    cm_file = generate_per_binary_cmake(rich_spec, tmp_path, tmp_path, tmp_path / "gen")
    text = cm_file.read_text(encoding="utf-8")
    assert "LANGUAGES C CXX" in text
    assert "freebsd_compile_yacc_lex(" in text
    assert 'set(FREEBSD_REQUIRED_SECTION3_LIBS "fbsd_libarchive;fbsd_libelftc")' in text
    assert 'set(FREEBSD_GEN_INC "' in text
    assert "add_compile_definitions(_CRT_SECURE_NO_WARNINGS _CRT_RAND_S)" in text
    assert 'set(BUILD_TESTING OFF CACHE BOOL "" FORCE)' in text
    assert "option(FREEBSD_AUTO_WIN_MSVC_PREFER_LOCAL" in text
    assert (
        "set(FETCHCONTENT_UPDATES_DISCONNECTED_AUTO_WIN_MSVC "
        'OFF CACHE BOOL "Always fetch latest master for auto_win_msvc" FORCE)'
    ) in text
    assert (
        'file(REMOVE "${CMAKE_BINARY_DIR}/CMakeFiles/fc-stamp/auto_win_msvc/update.stamp")' in text
    )
    assert "GIT_TAG master" in text
    assert "GIT_REMOTE_UPDATE_STRATEGY CHECKOUT" in text
    assert "GIT_SHALLOW_FILE" in text
    assert "unset(ENV{${_fbsd_git_env}})" in text
    assert not re.search(r"\bGIT_SHALLOW\b", text)
    assert '"stack=8192,eliminate"' in text
    assert '"stack=524288,eliminate"' in text
    assert "TARGET_RUNTIME_DLLS" in text
    assert "ranlib${CMAKE_EXECUTABLE_SUFFIX}" in text
    assert "BSD_AR=1" in text
    assert "fbsd_strdefs_ar.h" in text

    # Also cover yacc-only (no lex) and lex-only (no yacc) branches
    yacc_only = BinarySpec(
        prog="find",
        subdir="find",
        tier=1,
        is_cxx=False,
        sources=(),
        yacc_sources=(str(rich_y),),
        lex_sources=(),
        generated_headers=(),
        include_dirs=(),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    lex_only = BinarySpec(
        prog="colldef",
        subdir="colldef",
        tier=1,
        is_cxx=False,
        sources=(),
        yacc_sources=(),
        lex_sources=(str(rich_l),),
        generated_headers=(),
        include_dirs=(),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    y_txt = render_per_binary_cmakelists(yacc_only, tmp_path, tmp_path, tmp_path / "gen")
    l_txt = render_per_binary_cmakelists(lex_only, tmp_path, tmp_path, tmp_path / "gen")
    assert "YACC_SOURCES" in y_txt and "LEX_SOURCES" not in y_txt
    assert "OUT_HEADERS_VAR _FBSD_FIND_CODEGEN_HEADERS" in y_txt
    assert (
        "add_executable(${_FBSD_TARGET} ${_FBSD_FIND_ACTIVE_SOURCES} ${_FBSD_FIND_CODEGEN_HEADERS})"
        in y_txt
    )
    assert "LEX_SOURCES" in l_txt and "YACC_SOURCES" not in l_txt
    assert "add_executable(${_FBSD_TARGET} ${_FBSD_COLLDEF_ACTIVE_SOURCES})" in l_txt
    assert "/Zc:__cplusplus" in y_txt
    assert "/wd4716" in y_txt
    assert "/Zc:__STDC__" not in y_txt

    vac_spec = BinarySpec(
        prog="vacation",
        subdir="vacation",
        tier=1,
        is_cxx=False,
        sources=(str(rich_c),),
        yacc_sources=(),
        lex_sources=(),
        generated_headers=(),
        include_dirs=(),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    vac_txt = render_per_binary_cmakelists(vac_spec, tmp_path, tmp_path, tmp_path / "gen")
    assert "/Zc:__STDC__" in vac_txt


def test_standalone_per_binary_cmake_configure_build_and_ctest(tmp_path: Path) -> None:
    """Configure, build, and CTest an emitted ``per_binary/pagesize/CMakeLists.txt`` standalone.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    gen_dir = tmp_path / "freebsd_generated"
    dispatched = emit_all_script_applets(gen_dir)
    pagesize_c = dispatched["dispatchers/pagesize_main.c"]

    pagesize_spec = BinarySpec(
        prog="pagesize",
        subdir="pagesize",
        tier=6,
        is_cxx=False,
        sources=(str(pagesize_c),),
        yacc_sources=(),
        lex_sources=(),
        generated_headers=(),
        include_dirs=(str(pagesize_c.parent),),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    repo_root = Path(__file__).resolve().parent.parent
    index_cmake, cm_files = emit_all_per_binary_cmake(
        [pagesize_spec],
        repo_root=repo_root,
        freebsd_src=tmp_path,
        generated_dir=gen_dir,
    )
    assert index_cmake.is_file()
    assert len(cm_files) == 1
    assert "add_subdirectory(" in index_cmake.read_text(encoding="utf-8")

    cmake_bin = shutil.which("cmake")
    ctest_bin = shutil.which("ctest")
    assert cmake_bin is not None and ctest_bin is not None

    standalone_build = tmp_path / "build_pagesize_standalone"
    cfg = subprocess.run(
        [
            cmake_bin,
            "-S",
            str(cm_files[0].parent),
            "-B",
            str(standalone_build),
            "-DFREEBSD_USE_AUTO_WIN_MSVC=OFF",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cfg.returncode == 0, f"Standalone cmake configure failed: {cfg.stderr}"

    bld = subprocess.run(
        [cmake_bin, "--build", str(standalone_build)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bld.returncode == 0, f"Standalone cmake build failed: {bld.stderr}"

    tst = subprocess.run(
        [ctest_bin, "--test-dir", str(standalone_build), "--output-on-failure"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tst.returncode == 0, f"Standalone ctest failed: {tst.stderr}"

    built_bin = standalone_build / "bin" / "pagesize"
    run_res = subprocess.run([str(built_bin)], capture_output=True, text=True, check=False)
    assert run_res.returncode == 0 and run_res.stdout.strip().isdigit()


def test_auto_win_msvc_unpinned_tracks_latest_master(tmp_path: Path) -> None:
    """Verify FetchContent always tracks latest ``master`` across fast-forwards and force-pushes.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    cmake_bin = shutil.which("cmake")
    git_bin = shutil.which("git")
    assert cmake_bin is not None and git_bin is not None

    clean_env = sanitized_git_env()
    cmake_poison_env = {
        **clean_env,
        "GIT_DIR": str(tmp_path / "poison.git"),
        "GIT_INDEX_FILE": str(tmp_path / "poison.index"),
    }

    remote = tmp_path / "awm_remote.git"
    work = tmp_path / "awm_work"
    subprocess.run(
        [git_bin, "init", "--bare", "-b", "master", str(remote)],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    subprocess.run(
        [git_bin, "clone", str(remote), str(work)],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    subprocess.run(
        [git_bin, "-C", str(work), "config", "user.email", "t@example.com"],
        check=True,
        env=clean_env,
    )
    subprocess.run(
        [git_bin, "-C", str(work), "config", "user.name", "Test"],
        check=True,
        env=clean_env,
    )

    def write_awm_cmakelists(target_dir: Path, rev_label: str) -> None:
        """Write a synthetic ``auto-win-msvc`` ``CMakeLists.txt`` reporting ``rev_label``.

        Args:
            target_dir: Directory to write ``CMakeLists.txt`` into.
            rev_label: Revision tag emitted via ``message(STATUS ...)``.
        """
        (target_dir / "CMakeLists.txt").write_text(
            LF.join(
                [
                    "cmake_minimum_required(VERSION 3.24)",
                    "project(auto_win_msvc LANGUAGES NONE)",
                    f'message(STATUS "SYNTH_AWM_REV={rev_label}")',
                    "",
                ]
            ),
            encoding="utf-8",
        )

    write_awm_cmakelists(work, "r1")
    subprocess.run([git_bin, "-C", str(work), "add", "."], check=True, env=clean_env)
    subprocess.run(
        [git_bin, "-C", str(work), "commit", "-m", "r1"],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    subprocess.run(
        [git_bin, "-C", str(work), "push", "origin", "master"],
        check=True,
        capture_output=True,
        env=clean_env,
    )

    synth_repo = tmp_path / "workspace" / "freebsd-usr-bin-windows"
    synth_repo.mkdir(parents=True)
    sibling_awm = tmp_path / "workspace" / "auto-win-msvc"
    sibling_awm.mkdir(parents=True)
    write_awm_cmakelists(sibling_awm, "local")

    gen_dir = tmp_path / "gen"
    dispatched = emit_all_script_applets(gen_dir)
    pagesize_c = dispatched["dispatchers/pagesize_main.c"]
    pagesize_spec = BinarySpec(
        prog="pagesize",
        subdir="pagesize",
        tier=6,
        is_cxx=False,
        sources=(str(pagesize_c),),
        yacc_sources=(),
        lex_sources=(),
        generated_headers=(),
        include_dirs=(str(pagesize_c.parent),),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    cm_file = generate_per_binary_cmake(pagesize_spec, synth_repo, tmp_path, gen_dir)
    patched_cm = cm_file.read_text(encoding="utf-8").replace(
        "https://github.com/SamuelMarks/auto-win-msvc.git",
        remote.resolve().as_posix(),
    )
    cm_file.write_text(patched_cm, encoding="utf-8")

    bld_dir = tmp_path / "bld_awm_master"
    r_local = subprocess.run(
        [cmake_bin, "-S", str(cm_file.parent), "-B", str(bld_dir)],
        capture_output=True,
        text=True,
        check=False,
        env=cmake_poison_env,
    )
    assert r_local.returncode == 0 and "SYNTH_AWM_REV=local" in r_local.stdout

    r_r1 = subprocess.run(
        [
            cmake_bin,
            "-S",
            str(cm_file.parent),
            "-B",
            str(bld_dir),
            "-DFREEBSD_AUTO_WIN_MSVC_PREFER_LOCAL=OFF",
            "-DCMAKE_POLICY_DEFAULT_CMP0168=NEW",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=cmake_poison_env,
    )
    assert r_r1.returncode == 0 and "SYNTH_AWM_REV=r1" in r_r1.stdout

    write_awm_cmakelists(work, "r2")
    subprocess.run(
        [git_bin, "-C", str(work), "commit", "-am", "r2"],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    subprocess.run(
        [git_bin, "-C", str(work), "push", "origin", "master"],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    r_r2 = subprocess.run(
        [
            cmake_bin,
            "-S",
            str(cm_file.parent),
            "-B",
            str(bld_dir),
            "-DCMAKE_POLICY_DEFAULT_CMP0168=NEW",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=cmake_poison_env,
    )
    assert r_r2.returncode == 0 and "SYNTH_AWM_REV=r2" in r_r2.stdout

    write_awm_cmakelists(work, "r3")
    subprocess.run(
        [git_bin, "-C", str(work), "commit", "--amend", "-am", "r3"],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    subprocess.run(
        [git_bin, "-C", str(work), "push", "--force", "origin", "master"],
        check=True,
        capture_output=True,
        env=clean_env,
    )
    r_r3 = subprocess.run(
        [
            cmake_bin,
            "-S",
            str(cm_file.parent),
            "-B",
            str(bld_dir),
            "-DCMAKE_POLICY_DEFAULT_CMP0168=NEW",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=cmake_poison_env,
    )
    assert r_r3.returncode == 0 and "SYNTH_AWM_REV=r3" in r_r3.stdout
