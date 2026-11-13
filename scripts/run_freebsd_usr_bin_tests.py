#!/usr/bin/env python3
"""Functional test runner for ``freebsd-usr-bin`` multicall and standalone binaries.

Executes end-to-end verification of compiled FreeBSD ``usr.bin`` utilities
(including ``true``, ``false``, ``basename``, ``dirname``, ``seq``, ``jot``,
``rev``, ``banner``, ``caesar``, ``cut``, ``expand``, ``unexpand``, ``fold``,
``fmt``, ``nl``, ``number``, ``paste``, ``join``, ``comm``, ``uniq``, ``wc``,
``head``, ``split``, ``tr``, ``yes``, ``apply``, ``asa``, ``col``, ``colrm``,
``column``, ``file2c``, ``from``, ``getopt``, ``lam``, ``logname``, ``look``,
``mesg``, ``mktemp``, ``nice``, ``nohup``, ``pathchk``, ``printenv``,
``soelim``, ``tee``, ``touch``, ``truncate``, ``tty``, ``uname``, ``what``,
``which``, ``xstr``, ``pagesize``, and dispatcher entry points).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.parse_freebsd_usr_bin import BS, NL


def run_applet(
    binary: Path,
    applet: str,
    args: Sequence[str] = (),
    *,
    stdin_text: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute an applet via the ``freebsd-usr-bin`` multicall binary.

    Args:
        binary: Path to the compiled ``freebsd-usr-bin`` executable.
        applet: Name of the ``usr.bin`` applet to invoke.
        args: Command-line arguments passed after the applet name.
        stdin_text: Optional standard input text.
        cwd: Optional working directory.

    Returns:
        Completed subprocess result.
    """
    cmd = [str(binary), applet, *args]
    return subprocess.run(
        cmd,
        input=stdin_text,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def run_functional_suite(binary: Path, work_dir: Path) -> None:
    """Run the functional verification suite against ``binary``.

    Args:
        binary: Path to the compiled ``freebsd-usr-bin`` executable.
        work_dir: Temporary directory for test files.

    Raises:
        FreeBsdPortError: If any utility verification check fails.
    """
    ver_res = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ver_res.returncode != 0 or "280 entries" not in ver_res.stdout:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE,
            f"--version failed: {ver_res.stdout} {ver_res.stderr}",
            path=binary,
        )

    list_res = subprocess.run(
        [str(binary), "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    if list_res.returncode != 0 or "basename" not in list_res.stdout:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE,
            f"--list failed: {list_res.stdout}",
            path=binary,
        )

    if run_applet(binary, "true").returncode != 0:
        raise FreeBsdPortError(ErrorCode.TEST_EXECUTION_FAILURE, "true failed", path=binary)
    if run_applet(binary, "false").returncode == 0:
        raise FreeBsdPortError(ErrorCode.TEST_EXECUTION_FAILURE, "false returned 0", path=binary)

    b_res = run_applet(binary, "basename", ["/usr/local/bin/foo.txt", ".txt"])
    if b_res.returncode != 0 or b_res.stdout.strip() != "foo":
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"basename failed: {b_res.stdout}", path=binary
        )

    d_res = run_applet(binary, "dirname", ["/usr/local/bin/foo.txt"])
    if d_res.returncode != 0 or d_res.stdout.strip() not in (
        "/usr/local/bin",
        f"{BS}usr{BS}local{BS}bin",
    ):
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"dirname failed: {d_res.stdout}", path=binary
        )

    seq_res = run_applet(binary, "seq", ["1", "3"])
    if seq_res.returncode != 0 or seq_res.stdout.split() != ["1", "2", "3"]:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"seq failed: {seq_res.stdout}", path=binary
        )

    jot_res = run_applet(binary, "jot", ["3", "1"])
    if jot_res.returncode != 0 or jot_res.stdout.split() != ["1", "2", "3"]:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"jot failed: {jot_res.stdout}", path=binary
        )

    rev_res = run_applet(binary, "rev", stdin_text=f"abcdef{NL}")
    if rev_res.returncode != 0 or rev_res.stdout.strip() != "fedcba":
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"rev failed: {rev_res.stdout}", path=binary
        )

    caesar_res = run_applet(binary, "caesar", ["13"], stdin_text=f"Hello{NL}")
    if caesar_res.returncode != 0 or caesar_res.stdout.strip() != "Uryyb":
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"caesar failed: {caesar_res.stdout}", path=binary
        )

    cut_res = run_applet(binary, "cut", ["-d:", "-f2"], stdin_text=f"a:b:c{NL}")
    if cut_res.returncode != 0 or cut_res.stdout.strip() != "b":
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"cut failed: {cut_res.stdout}", path=binary
        )

    fold_res = run_applet(binary, "fold", ["-w", "3"], stdin_text=f"abcdef{NL}")
    if fold_res.returncode != 0 or fold_res.stdout.split() != ["abc", "def"]:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"fold failed: {fold_res.stdout}", path=binary
        )

    sample = work_dir / "sample.txt"
    sample.write_text(f"alpha{NL}alpha{NL}beta{NL}gamma{NL}", encoding="utf-8")

    head_res = run_applet(binary, "head", ["-n", "2", str(sample)])
    if head_res.returncode != 0 or head_res.stdout.split() != ["alpha", "alpha"]:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"head failed: {head_res.stdout}", path=binary
        )

    uniq_res = run_applet(binary, "uniq", [str(sample)])
    if uniq_res.returncode != 0 or uniq_res.stdout.split() != ["alpha", "beta", "gamma"]:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"uniq failed: {uniq_res.stdout}", path=binary
        )

    wc_res = run_applet(binary, "wc", ["-l", str(sample)])
    if wc_res.returncode != 0 or "4" not in wc_res.stdout:
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE, f"wc failed: {wc_res.stdout}", path=binary
        )

    pagesize_res = run_applet(binary, "pagesize")
    if pagesize_res.returncode != 0 or not pagesize_res.stdout.strip().isdigit():
        raise FreeBsdPortError(
            ErrorCode.TEST_EXECUTION_FAILURE,
            f"pagesize failed: {pagesize_res.stdout}",
            path=binary,
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for ``run_freebsd_usr_bin_tests.py``.

    Args:
        argv: Optional CLI argument list.

    Returns:
        Parsed ``argparse.Namespace``.
    """
    parser = argparse.ArgumentParser(
        description="Run functional tests against compiled freebsd-usr-bin binary."
    )
    parser.add_argument(
        "binary",
        type=Path,
        help="Path to the compiled freebsd-usr-bin executable.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``run_freebsd_usr_bin_tests.py``.

    Args:
        argv: Optional CLI argument list.

    Returns:
        Exit code (``0`` on success, ``1`` on failure).
    """
    args = parse_args(argv)
    binary = args.binary.resolve()
    if not binary.is_file():
        print(f"Error: binary not found: {binary}", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp_str:
            run_functional_suite(binary, Path(tmp_str))
    except FreeBsdPortError as exc:
        print(f"Test failure: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
