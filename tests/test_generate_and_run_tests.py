"""Unit tests for ``GenerateFreeBsdHeaders.cmake`` and ``scripts.run_freebsd_usr_bin_tests``."""

from __future__ import annotations

import runpy
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from scripts.errors import FreeBsdPortError
from scripts.parse_freebsd_usr_bin import BS, DQUOTE, NL
from scripts.run_freebsd_usr_bin_tests import (
    main as runner_main,
)
from scripts.run_freebsd_usr_bin_tests import (
    parse_args as runner_parse_args,
)
from scripts.run_freebsd_usr_bin_tests import (
    run_applet,
    run_functional_suite,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CMAKE_GENERATOR = REPO_ROOT / "cmake" / "GenerateFreeBsdHeaders.cmake"
CR = chr(13)


def run_cmake_script(
    script_path: Path,
    *args: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a CMake script in ``cmake -P`` script mode.

    Args:
        script_path: Path to the ``.cmake`` script to execute.
        *args: Optional ``-DVAR=VALUE`` definitions passed before ``-P``.
        cwd: Optional working directory for the CMake process.

    Returns:
        CompletedProcess containing stdout, stderr, and return code.
    """
    return subprocess.run(
        ["cmake", *args, "-P", str(script_path)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cmake_generate_headers_synthetic_and_functions(tmp_path: Path) -> None:
    """Verify ``GenerateFreeBsdHeaders.cmake`` across synthetic trees, functions, and errors.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    synth_src = tmp_path / "freebsd-src"
    usr_bin = synth_src / "usr.bin"
    usr_bin.mkdir(parents=True)
    (usr_bin / "Makefile").write_text(f"# top-level Makefile{NL}", encoding="utf-8")

    # 1. Direct native applet with main(void) and adjacent static identifiers
    base_dir = usr_bin / "basename"
    base_dir.mkdir()
    (base_dir / "Makefile").write_text(f"PROG= basename{NL}", encoding="utf-8")
    (base_dir / "basename.c").write_text(
        NL.join(
            [
                "static void usage(void) {}",
                "static int cflag;",
                "int main(void) { cflag = cflag|cflag; usage(); return cflag; }",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # 2. Direct native applet with main(int argc, const char **argv __unused) and ?=
    log_dir = usr_bin / "logname"
    log_dir.mkdir()
    (log_dir / "Makefile").write_text(
        NL.join(
            [
                "PROG?= logname",
                "PROG?= ignored_override",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (log_dir / "logname.c").write_text(
        f"int main(int argc __unused, const char **argv __unused) {{ return argc; }}{NL}",
        encoding="utf-8",
    )

    # 3. Contrib/complex Makefile testing modifiers (:H, :H:H, :T, :tl, :tu, :U),
    #    quoted .include paths (absolute, mk_dir-relative, CURDIR-relative), +=, !=, CRLF
    tar_dir = usr_bin / "tar"
    (tar_dir / "sub").mkdir(parents=True)
    (tar_dir / "Makefile.inc").write_text(
        NL.join(
            [
                "EMPTY_VAR=",
                "EMPTY_VAR?= bsdtar",
                "MIXED= FooBar",
                "LOWER_VAR= ${MIXED:tl}",
                "UPPER_VAR= ${MIXED:tu}",
                "PARENT_DIR= ${.CURDIR:H}",
                "BASE_NAME= ${.CURDIR:T}",
                "SHELL_CMD!= echo ignored",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tar_dir / "cur_only.mk").write_text(f"PROG= ${{EMPTY_VAR}}{NL}", encoding="utf-8")
    (tar_dir / "sub" / "extra.mk").write_text(
        f".sinclude {DQUOTE}cur_only.mk{DQUOTE}{NL}",
        encoding="utf-8",
    )
    crlf = f"{CR}{NL}"
    (tar_dir / "Makefile").write_text(
        crlf.join(
            [
                "# comment with ; semicolon",
                f".include {DQUOTE}${{.CURDIR:H:H}}/usr.bin/tar/sub/extra.mk{DQUOTE}",
                f".-include {DQUOTE}sub/extra.mk{DQUOTE}",
                f"LINKS= ${{BINDIR}}/bsdtar {BS}",
                "    ${BINDIR}/tar",
                "LINKS+= ${BINDIR}/bsdtar ${BINDIR}/${UNDEF_ALIAS:Ugtar}",
                "LINKS+= ${BINDIR}/bsdtar ${STILL_UNDEF}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # 4. PROG_CXX, PROGS, directory without Makefile, and pagesize script applet
    cxx_dir = usr_bin / "cxxtool"
    cxx_dir.mkdir()
    (cxx_dir / "Makefile").write_text(f"PROG_CXX= cxxtool{NL}", encoding="utf-8")

    multi_dir = usr_bin / "multi"
    multi_dir.mkdir()
    (multi_dir / "Makefile").write_text(f"PROGS= first_prog second_prog{NL}", encoding="utf-8")

    nomk_dir = usr_bin / "nomake"
    nomk_dir.mkdir()

    pg_dir = usr_bin / "pagesize"
    pg_dir.mkdir()
    (pg_dir / "Makefile").write_text(f"SCRIPTS= pagesize.sh{NL}", encoding="utf-8")

    out_dir = tmp_path / "gen"
    res = run_cmake_script(
        CMAKE_GENERATOR,
        f"-DFREEBSD_SRC_DIR={synth_src}",
        f"-DOUT_DIR={out_dir}",
    )
    assert res.returncode == 0, res.stderr

    assert (out_dir / "include" / "osreldate.h").is_file()
    assert (out_dir / "include" / "pathnames.h").is_file()
    assert (out_dir / "include" / "libxo" / "xo.h").is_file()
    assert (out_dir / "include" / "freebsd_compat_preinclude.h").is_file()
    mutex_shim = out_dir / "include" / "bits" / "struct_mutex.h"
    rwlock_shim = out_dir / "include" / "bits" / "struct_rwlock.h"
    assert mutex_shim.is_file() and 'push_macro("__unused")' in mutex_shim.read_text(
        encoding="utf-8"
    )
    assert rwlock_shim.is_file() and 'push_macro("__unused")' in rwlock_shim.read_text(
        encoding="utf-8"
    )

    compat_c = (out_dir / "src" / "freebsd_libcompat.c").read_text(encoding="utf-8")
    assert "xo_emit" in compat_c
    assert "fbsd_fgetwln" in compat_c
    assert "fbsd_wcwidth" in compat_c

    base_wrapped = (out_dir / "applets" / "fbsd_basename.c").read_text(encoding="utf-8")
    assert "fbsd_basename_usage" in base_wrapped
    assert "fbsd_basename_cflag|fbsd_basename_cflag" in base_wrapped
    assert "int fbsd_basename_main(int argc, char *argv[])" in base_wrapped

    log_wrapped = (out_dir / "applets" / "fbsd_logname.c").read_text(encoding="utf-8")
    assert "fbsd_logname_main(int argc __unused, const char **argv __unused)" in log_wrapped

    pg_stub = (out_dir / "applets" / "fbsd_pagesize.c").read_text(encoding="utf-8")
    assert "4096UL" in pg_stub and "_SC_PAGESIZE" in pg_stub

    mc_main = (out_dir / "src" / "freebsd_multicall_main.c").read_text(encoding="utf-8")
    for expected_entry in ("basename", "bsdtar", "gtar", "cxxtool", "first_prog", "pagesize"):
        assert f'{{ "{expected_entry}", ' in mc_main

    targets_cmake = (out_dir / "freebsd_usr_bin_targets.cmake").read_text(encoding="utf-8")
    assert "set(FREEBSD_USR_BIN_TOTAL_ENTRIES 8)" in targets_cmake
    assert "set(FREEBSD_USR_BIN_UTILITY_COUNT 7)" in targets_cmake
    assert (out_dir / "enabled_sources.cmake").is_file()

    # Default OUT_DIR when omitted in script mode
    default_cwd = tmp_path / "default_out_cwd"
    default_cwd.mkdir()
    res_def_out = run_cmake_script(
        CMAKE_GENERATOR,
        f"-DFREEBSD_SRC_DIR={synth_src}",
        cwd=default_cwd,
    )
    assert res_def_out.returncode == 0, res_def_out.stderr
    assert (default_cwd / "build" / "freebsd_generated" / "enabled_sources.cmake").is_file()

    # Default FREEBSD_SRC_DIR when omitted in script mode
    res_def_src = run_cmake_script(CMAKE_GENERATOR, f"-DOUT_DIR={tmp_path / 'def_src_out'}")
    has_real_src = (REPO_ROOT.parent / "freebsd-src" / "usr.bin").is_dir()
    assert (res_def_src.returncode == 0) is has_real_src

    # Direct function invocations with OUT_HEADERS_VAR and OUT_FILE_VAR
    fn_test_cmake = tmp_path / "call_functions.cmake"
    cmake_gen_posix = CMAKE_GENERATOR.as_posix()
    fn_out_posix = (tmp_path / "fn_out").as_posix()
    fn_test_cmake.write_text(
        NL.join(
            [
                f"include({DQUOTE}{cmake_gen_posix}{DQUOTE})",
                (
                    f"freebsd_emit_compat_headers("
                    f"INC_DIR {DQUOTE}{fn_out_posix}/inc{DQUOTE} OUT_HEADERS_VAR _hdrs)"
                ),
                "list(LENGTH _hdrs _hdr_len)",
                "if(NOT _hdr_len EQUAL 4)",
                f"    message(FATAL_ERROR {DQUOTE}Expected 4 headers{DQUOTE})",
                "endif()",
                (
                    f"freebsd_emit_libcompat_c("
                    f"SRC_DIR {DQUOTE}{fn_out_posix}/src{DQUOTE} OUT_FILE_VAR _cfile)"
                ),
                f"if(NOT EXISTS {DQUOTE}${{_cfile}}{DQUOTE})",
                f"    message(FATAL_ERROR {DQUOTE}Missing libcompat.c{DQUOTE})",
                "endif()",
                (
                    f"freebsd_generate_all("
                    f"FREEBSD_SRC_DIR {DQUOTE}{synth_src.as_posix()}{DQUOTE} "
                    f"OUT_DIR {DQUOTE}{fn_out_posix}/skip_mc{DQUOTE} SKIP_MULTICALL)"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    res_fn = run_cmake_script(fn_test_cmake)
    assert res_fn.returncode == 0, res_fn.stderr
    assert (
        (tmp_path / "fn_out" / "skip_mc" / "enabled_sources.cmake")
        .read_text(encoding="utf-8")
        .endswith(f"set(FREEBSD_MULTICALL_SOURCES){NL}")
    )
    # Re-run to exercise unchanged SHA-256 stamp and freebsd_write_var_if_different branches
    res_fn_idem = run_cmake_script(fn_test_cmake)
    assert res_fn_idem.returncode == 0, res_fn_idem.stderr

    # Script-mode and function-mode validation error branches
    res_missing_usr_bin = run_cmake_script(
        CMAKE_GENERATOR,
        f"-DFREEBSD_SRC_DIR={tmp_path / 'missing_src'}",
        f"-DOUT_DIR={tmp_path / 'err_out'}",
    )
    assert res_missing_usr_bin.returncode != 0
    assert "FreeBSD usr.bin directory not found" in res_missing_usr_bin.stderr

    res_empty_src = run_cmake_script(CMAKE_GENERATOR, "-DFREEBSD_SRC_DIR=")
    assert res_empty_src.returncode != 0
    assert "FREEBSD_SRC_DIR is required" in res_empty_src.stderr

    res_empty_out = run_cmake_script(
        CMAKE_GENERATOR,
        f"-DFREEBSD_SRC_DIR={synth_src}",
        "-DOUT_DIR=",
    )
    assert res_empty_out.returncode != 0
    assert "OUT_DIR is required" in res_empty_out.stderr

    error_cases = (
        ("freebsd_emit_compat_headers()", "INC_DIR is required"),
        ("freebsd_emit_libcompat_c()", "SRC_DIR is required"),
        (
            f"set(_in {DQUOTE}int main(void){{return 0;}}{DQUOTE}){NL}"
            f"freebsd_transform_applet_source(_in {DQUOTE}{DQUOTE} _out)",
            "APPLET_ID is required",
        ),
        (
            "freebsd_emit_multicall_applets_and_dispatcher()",
            "FREEBSD_SRC_DIR is required",
        ),
        (
            f"freebsd_emit_multicall_applets_and_dispatcher("
            f"FREEBSD_SRC_DIR {DQUOTE}{synth_src.as_posix()}{DQUOTE})",
            "OUT_DIR is required",
        ),
        (
            f"freebsd_emit_multicall_applets_and_dispatcher("
            f"FREEBSD_SRC_DIR {DQUOTE}{(tmp_path / 'nope').as_posix()}{DQUOTE} "
            f"OUT_DIR {DQUOTE}{(tmp_path / 'o').as_posix()}{DQUOTE})",
            "FreeBSD usr.bin directory not found",
        ),
    )
    for idx, (call_snippet, expected_err) in enumerate(error_cases):
        err_script = tmp_path / f"err_{idx}.cmake"
        err_script.write_text(
            f"include({DQUOTE}{cmake_gen_posix}{DQUOTE}){NL}{call_snippet}{NL}",
            encoding="utf-8",
        )
        err_res = run_cmake_script(err_script)
        assert err_res.returncode != 0
        assert expected_err in err_res.stderr


def test_run_freebsd_usr_bin_tests_all_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify ``run_applet``, ``run_functional_suite``, and CLI ``main`` across all branches.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.
        capsys: Pytest stdout/stderr capture fixture.
    """
    fake_bin = tmp_path / "freebsd-usr-bin"
    fake_bin.write_text(f"#!/bin/sh{NL}", encoding="utf-8")

    # Missing binary returns 1
    assert runner_main([str(tmp_path / "no_such_bin")]) == 1
    assert "binary not found" in capsys.readouterr().err

    parsed = runner_parse_args([str(fake_bin)])
    assert parsed.binary == fake_bin

    def make_responder(
        fail_key: str = "",
    ) -> Callable[..., subprocess.CompletedProcess[str]]:
        """Create a subprocess.run responder that optionally fails on ``fail_key``.

        Args:
            fail_key: Applet or flag name to simulate failure on.

        Returns:
            Callable replacement for ``subprocess.run``.
        """

        def responder(
            cmd: Sequence[str],
            *,
            input: str | None = None,
            cwd: Path | None = None,
            capture_output: bool = False,
            text: bool = False,
            check: bool = False,
        ) -> subprocess.CompletedProcess[str]:
            """Simulate multicall binary responses for each applet.

            Args:
                cmd: Command sequence passed to ``subprocess.run``.
                input: Optional standard input string passed to the process.
                cwd: Optional working directory for the simulated process.
                capture_output: Whether stdout and stderr capture was requested.
                text: Whether text mode decoding was requested.
                check: Whether non-zero exit status checking was requested.

            Returns:
                Simulated ``CompletedProcess``.
            """
            _ = (input, cwd, capture_output, text, check)
            cmd_list = list(cmd)
            sub = cmd_list[1]
            if sub == fail_key:
                rc = 0 if sub == "false" else 1
                return subprocess.CompletedProcess(cmd_list, rc, stdout="bad", stderr="err")
            if sub == "--version":
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"freebsd-usr-bin 15.0.0 (280 entries){NL}", stderr=""
                )
            if sub == "--list":
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"basename{NL}true{NL}", stderr=""
                )
            if sub == "true":
                return subprocess.CompletedProcess(cmd_list, 0, stdout="", stderr="")
            if sub == "false":
                return subprocess.CompletedProcess(cmd_list, 1, stdout="", stderr="")
            if sub == "basename":
                return subprocess.CompletedProcess(cmd_list, 0, stdout=f"foo{NL}", stderr="")
            if sub == "dirname":
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"/usr/local/bin{NL}", stderr=""
                )
            if sub in ("seq", "jot"):
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"1{NL}2{NL}3{NL}", stderr=""
                )
            if sub == "rev":
                return subprocess.CompletedProcess(cmd_list, 0, stdout=f"fedcba{NL}", stderr="")
            if sub == "caesar":
                return subprocess.CompletedProcess(cmd_list, 0, stdout=f"Uryyb{NL}", stderr="")
            if sub == "cut":
                return subprocess.CompletedProcess(cmd_list, 0, stdout=f"b{NL}", stderr="")
            if sub == "fold":
                return subprocess.CompletedProcess(cmd_list, 0, stdout=f"abc{NL}def{NL}", stderr="")
            if sub == "head":
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"alpha{NL}alpha{NL}", stderr=""
                )
            if sub == "uniq":
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"alpha{NL}beta{NL}gamma{NL}", stderr=""
                )
            if sub == "wc":
                return subprocess.CompletedProcess(
                    cmd_list, 0, stdout=f"  4 sample.txt{NL}", stderr=""
                )
            return subprocess.CompletedProcess(cmd_list, 0, stdout=f"4096{NL}", stderr="")

        return responder

    monkeypatch.setattr(subprocess, "run", make_responder(""))
    assert run_applet(fake_bin, "true").returncode == 0
    assert runner_main([str(fake_bin)]) == 0

    for key in (
        "--version",
        "--list",
        "true",
        "false",
        "basename",
        "dirname",
        "seq",
        "jot",
        "rev",
        "caesar",
        "cut",
        "fold",
        "head",
        "uniq",
        "wc",
        "pagesize",
    ):
        monkeypatch.setattr(subprocess, "run", make_responder(key))
        with pytest.raises(FreeBsdPortError):
            run_functional_suite(fake_bin, tmp_path)

    monkeypatch.setattr(subprocess, "run", make_responder("true"))
    assert runner_main([str(fake_bin)]) == 1
    assert "Test failure:" in capsys.readouterr().err

    old_argv = sys.argv
    sys.argv = ["run_freebsd_usr_bin_tests.py", str(tmp_path / "missing_bin")]
    try:
        script_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_freebsd_usr_bin_tests.py"
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(script_path), run_name="__main__")
        assert exc_info.value.code == 1
    finally:
        sys.argv = old_argv
    capsys.readouterr()
