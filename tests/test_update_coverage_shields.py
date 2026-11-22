"""Unit tests for ``scripts.update_coverage_shields``."""

from __future__ import annotations

import ast
import re
import runpy
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.update_coverage_shields import (
    DOC_BADGE_ALT,
    DOC_BADGE_LABEL,
    TEST_BADGE_ALT,
    TEST_BADGE_LABEL,
    build_shield_markdown,
    compute_doc_coverage,
    compute_test_coverage,
    format_percentage,
    get_shield_color,
    main,
    parse_args,
    update_or_insert_shield,
)


def test_get_shield_color_and_format_percentage() -> None:
    """Verify color thresholds and percentage formatting branches."""
    assert get_shield_color(100.0) == "brightgreen"
    assert get_shield_color(95.0) == "brightgreen"
    assert get_shield_color(92.5) == "green"
    assert get_shield_color(85.0) == "yellowgreen"
    assert get_shield_color(75.0) == "yellow"
    assert get_shield_color(65.0) == "orange"
    assert get_shield_color(50.0) == "red"

    assert format_percentage(100.0) == "100"
    assert format_percentage(99.99) == "100"
    assert format_percentage(98.5) == "98.5"
    assert format_percentage(0.0) == "0"

    assert (
        build_shield_markdown(DOC_BADGE_ALT, DOC_BADGE_LABEL, 100.0)
        == "![Doc Coverage](https://img.shields.io/badge/doc%20coverage-100%25-brightgreen)"
    )


def test_update_or_insert_shield_branches() -> None:
    """Verify shield insertion and update across Markdown heading styles."""
    nl = chr(10)
    readme_with_badges = nl.join(
        [
            "Title",
            "=====",
            "",
            "[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://example.com)",
            "[![CI](https://example.com/badge.svg)](https://example.com)",
            "",
            "Body paragraph.",
            "",
        ]
    )
    updated1, changed1 = update_or_insert_shield(
        readme_with_badges, DOC_BADGE_ALT, DOC_BADGE_LABEL, 100.0
    )
    assert changed1 is True
    assert "![Doc Coverage](https://img.shields.io/badge/doc%20coverage-100%25-brightgreen)" in (
        updated1
    )
    assert updated1.endswith(nl)

    updated2, changed2 = update_or_insert_shield(updated1, DOC_BADGE_ALT, DOC_BADGE_LABEL, 100.0)
    assert changed2 is False
    assert updated2 == updated1

    updated3, changed3 = update_or_insert_shield(updated1, DOC_BADGE_ALT, DOC_BADGE_LABEL, 85.4)
    assert changed3 is True
    assert "85.4%25-yellowgreen" in updated3

    setext_readme = f"Project{nl}======={nl}Hello"
    updated4, changed4 = update_or_insert_shield(
        setext_readme, TEST_BADGE_ALT, TEST_BADGE_LABEL, 100.0
    )
    assert changed4 is True
    assert not updated4.endswith(nl)
    assert updated4.splitlines()[2].startswith("![Test Coverage]")

    atx_readme = f"# Project{nl}Hello{nl}"
    updated5, changed5 = update_or_insert_shield(
        atx_readme, TEST_BADGE_ALT, TEST_BADGE_LABEL, 100.0
    )
    assert changed5 is True
    assert updated5.splitlines()[1].startswith("![Test Coverage]")

    plain_readme = f"Plain text only{nl}"
    updated6, changed6 = update_or_insert_shield(
        plain_readme, DOC_BADGE_ALT, DOC_BADGE_LABEL, 100.0
    )
    assert changed6 is True
    assert updated6.splitlines()[0].startswith("![Doc Coverage]")


def test_compute_doc_and_test_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify subprocess parsing and fallback branches for doc and test coverage.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.
    """
    nl = chr(10)
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "outer.index"))

    def fake_interrogate_ok(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Return a simulated successful interrogate CompletedProcess.

        Args:
            cmd: Subprocess command list.
            cwd: Optional working directory for the subprocess.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            Simulated CompletedProcess with 100% actual coverage.
        """
        _ = (cwd, capture_output, text, check)
        assert env is not None and "GIT_INDEX_FILE" not in env
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=f"RESULT: PASSED (minimum: 100.0%, actual: 100.0%){nl}",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_interrogate_ok)
    assert compute_doc_coverage(tmp_path) == 100.0

    def fake_interrogate_bad(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Return a simulated malformed interrogate CompletedProcess.

        Args:
            cmd: Subprocess command list.
            cwd: Optional working directory for the subprocess.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            Simulated CompletedProcess with unparseable output.
        """
        _ = (cwd, capture_output, text, check, env)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="unexpected output",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_interrogate_bad)
    with pytest.raises(FreeBsdPortError, match="Unable to parse interrogate output"):
        compute_doc_coverage(tmp_path)

    cov_file = tmp_path / ".coverage"
    cov_file.write_text("dummy", encoding="utf-8")

    def fake_cov_report_ok(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Return a simulated successful coverage report CompletedProcess.

        Args:
            cmd: Subprocess command list.
            cwd: Optional working directory for the subprocess.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            Simulated CompletedProcess with TOTAL 100%.
        """
        _ = (cwd, capture_output, text, check)
        assert env is not None and "GIT_INDEX_FILE" not in env
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=f"Name Stmts Miss Cover{nl}TOTAL 100 0 100%{nl}",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_cov_report_ok)
    assert compute_test_coverage(tmp_path) == 100.0

    calls: list[list[str]] = []

    def fake_cov_then_pytest(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate coverage report without TOTAL line followed by pytest output.

        Args:
            cmd: Subprocess command list.
            cwd: Optional working directory for the subprocess.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            Simulated CompletedProcess for coverage or pytest.
        """
        _ = (cwd, capture_output, text, check)
        assert env is not None and "GIT_INDEX_FILE" not in env
        calls.append(cmd)
        if "coverage" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="No total line here", stderr=""
            )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=f"TOTAL 200 5 97.5%{nl}",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_cov_then_pytest)
    assert compute_test_coverage(tmp_path) == 97.5
    assert len(calls) == 2

    def fake_cov_fail_then_pytest(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate failing coverage report followed by successful pytest run.

        Args:
            cmd: Subprocess command list.
            cwd: Optional working directory for the subprocess.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            Simulated CompletedProcess for coverage failure or pytest success.
        """
        _ = (cwd, capture_output, text, check, env)
        if "coverage" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="err")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=f"TOTAL 50 0 100%{nl}",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_cov_fail_then_pytest)
    assert compute_test_coverage(tmp_path) == 100.0

    cov_file.unlink()

    def fake_pytest_bad(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate malformed pytest output.

        Args:
            cmd: Subprocess command list.
            cwd: Optional working directory for the subprocess.
            capture_output: Whether stdout/stderr capture was requested.
            text: Whether text mode decoding was requested.
            check: Whether non-zero exit status checking was requested.
            env: Sanitized environment mapping passed to ``subprocess.run``.

        Returns:
            Simulated CompletedProcess lacking a TOTAL line.
        """
        _ = (cwd, capture_output, text, check, env)
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="no coverage table", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_pytest_bad)
    with pytest.raises(FreeBsdPortError, match="Unable to parse coverage output"):
        compute_test_coverage(tmp_path)


def test_cli_main_and_entry_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify CLI argument parsing, main execution paths, and ``__main__`` invocation.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.
        capsys: Pytest stdout/stderr capture fixture.
    """
    nl = chr(10)
    parsed = parse_args(["--doc", "--readme", "README.md"])
    assert parsed.doc is True
    assert parsed.test is False
    assert parsed.readme == Path("README.md")

    rc_missing = main(["--repo-root", str(tmp_path), "--readme", "MISSING.md"])
    assert rc_missing == 1
    assert "README file not found" in capsys.readouterr().err

    readme = tmp_path / "README.md"
    readme.write_text(
        nl.join(
            [
                "FreeBSD usr.bin Windows",
                "=======================",
                "",
                "[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://example.com)",
                "",
                "Text.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("scripts.update_coverage_shields.compute_doc_coverage", lambda _r: 100.0)
    monkeypatch.setattr("scripts.update_coverage_shields.compute_test_coverage", lambda _r: 100.0)

    rc_both = main(["--repo-root", str(tmp_path), "--readme", str(readme)])
    assert rc_both == 0
    text_after = readme.read_text(encoding="utf-8")
    assert "![Doc Coverage]" in text_after
    assert "![Test Coverage]" in text_after

    rc_noop = main(["--repo-root", str(tmp_path)])
    assert rc_noop == 0

    assert main(["--repo-root", str(tmp_path), "--doc"]) == 0
    assert main(["--repo-root", str(tmp_path), "--test"]) == 0

    def raise_err(_r: Path) -> float:
        """Raise a simulated FreeBsdPortError during coverage calculation.

        Args:
            _r: Ignored repository root path.

        Raises:
            FreeBsdPortError: Always raised to test error handling.
        """
        raise FreeBsdPortError(ErrorCode.CODEGEN_FAILURE, "simulated failure")

    monkeypatch.setattr("scripts.update_coverage_shields.compute_doc_coverage", raise_err)
    rc_err = main(["--repo-root", str(tmp_path), "--doc"])
    assert rc_err == 1
    assert "simulated failure" in capsys.readouterr().err

    old_argv = sys.argv
    sys.argv = [
        "update_coverage_shields.py",
        "--repo-root",
        str(tmp_path),
        "--readme",
        "NONEXISTENT.md",
    ]
    try:
        script_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "update_coverage_shields.py"
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(script_path), run_name="__main__")
        assert exc_info.value.code == 1
    finally:
        sys.argv = old_argv
    capsys.readouterr()


def test_ast_doc_and_strong_typing_hygiene() -> None:
    """Enforce 100% module, class, field, function, and arg docstrings plus no weak types."""
    repo_root = Path(__file__).resolve().parent.parent
    py_files = sorted([*(repo_root / "scripts").glob("*.py"), *(repo_root / "tests").glob("*.py")])
    weak_type_names = {"Any", "object"}

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        assert ast.get_docstring(tree), f"{py_file}: missing module docstring"

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls_doc = ast.get_docstring(node) or ""
                assert cls_doc, f"{py_file}:{node.lineno}: class {node.name} missing docstring"
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        field_name = stmt.target.id
                        assert re.search(rf"\b{re.escape(field_name)}\b\s*:", cls_doc), (
                            f"{py_file}:{node.lineno}: class {node.name} missing field {field_name}"
                        )
            elif isinstance(node, ast.FunctionDef):
                fn_doc = ast.get_docstring(node) or ""
                assert fn_doc, f"{py_file}:{node.lineno}: {node.name} missing docstring"
                arg_nodes = [
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                    *filter(None, (node.args.vararg, node.args.kwarg)),
                ]
                for arg_node in arg_nodes:
                    if arg_node.arg != "self":
                        assert re.search(rf"\b{re.escape(arg_node.arg)}\b\s*:", fn_doc), (
                            f"{py_file}:{node.lineno}: {node.name} missing arg {arg_node.arg}"
                        )
            elif isinstance(node, ast.Name):
                assert node.id not in weak_type_names, (
                    f"{py_file}:{node.lineno}: forbidden weak type {node.id}"
                )
