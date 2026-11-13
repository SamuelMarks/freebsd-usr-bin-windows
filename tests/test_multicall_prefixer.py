"""Unit and C compilation tests for ``scripts.multicall_prefixer``."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.multicall_prefixer import (
    BS,
    LF,
    discover_external_symbols,
    generate_multicall_dispatcher_c,
    rewrite_c_source_for_multicall,
    sanitize_applet_id,
    stage_multicall_applet,
)


def test_sanitize_discover_and_rewrite_edge_cases(tmp_path: Path) -> None:
    """Verify identifier sanitization, comment/literal stripping, and member exclusion.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    assert sanitize_applet_id("ssh-copy-id") == "ssh_copy_id"
    assert sanitize_applet_id("9base") == "app_9base"
    with pytest.raises(FreeBsdPortError) as exc_id:
        sanitize_applet_id("---")
    assert exc_id.value.code is ErrorCode.CODEGEN_FAILURE

    # Non-existent file in discover_external_symbols is safely skipped
    missing_c = tmp_path / "missing.c"
    multiline_c = tmp_path / "multiline.c"
    multiline_c.write_text(
        LF.join(
            [
                "/* block comment",
                "   spanning lines */",
                "// line comment",
                "#include <stdio.h>",
                "static int hidden_fn(void) {",
                "    return 0;",
                "}",
                "int",
                "shared_helper(const char *msg) {",
                f'    const char *lit = "shared_helper {BS}"quoted{BS}"";',
                "    char ch = 'x';",
                "    (void)lit; (void)ch;",
                "    return msg != NULL;",
                "}",
                "unsigned long custom_counter = 5;",
                "int main(void) {",
                '    return shared_helper("ok");',
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    unclosed_c1 = tmp_path / "unclosed1.c"
    unclosed_c1.write_text("int fbsd_skip_me(void) { return 0; } /* unclosed", encoding="utf-8")
    unclosed_c2 = tmp_path / "unclosed2.c"
    unclosed_c2.write_text(
        f'int fbsd_skip_var = 0;{LF}const char *u = "unclosed',
        encoding="utf-8",
    )
    syms = discover_external_symbols([missing_c, multiline_c, unclosed_c1, unclosed_c2])
    assert "shared_helper" in syms
    assert "custom_counter" in syms
    assert "hidden_fn" not in syms

    # Test unclosed comment / unclosed string / member access (.usage, ->usage) / trailing #include
    tricky_c = LF.join(
        [
            '#include "myhdr.h"',
            "struct cfg { int usage; };",
            "int use_cfg(struct cfg *p) {",
            "    struct cfg local;",
            "    local.usage = 1;",
            "    return p->usage + vflag;",
            "}",
            "#include <stdlib.h>",
            "// trailing comment without newline",
        ]
    )
    rewritten = rewrite_c_source_for_multicall(
        tricky_c, "demo", ["usage", "vflag"], rewrite_main=False
    )
    assert "local.usage = 1;" in rewritten
    assert "p->usage + fbsd_demo_vflag;" in rewritten
    assert '#include "myhdr.h"' in rewritten

    unclosed_comment = "int vflag = 1; /* unclosed"
    assert "fbsd_demo_vflag" in rewrite_c_source_for_multicall(unclosed_comment, "demo", ["vflag"])
    unclosed_str = 'int vflag = 1; const char *s = "unclosed'
    assert "fbsd_demo_vflag" in rewrite_c_source_for_multicall(unclosed_str, "demo", ["vflag"])


def test_multicall_compile_two_colliding_multifile_applets(tmp_path: Path) -> None:
    """Compile two multi-file applets with colliding globals/functions into one binary.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    alpha_dir = tmp_path / "src_alpha"
    beta_dir = tmp_path / "src_beta"
    alpha_dir.mkdir()
    beta_dir.mkdir()

    # Both alpha and beta define non-static `int vflag`, `void usage(void)`, `int compute(int)`!
    for idx_val, d_path, mult in ((1, alpha_dir, 10), (2, beta_dir, 100)):
        (d_path / "common.h").write_text(
            LF.join(
                [
                    "#ifndef COMMON_H_",
                    "#define COMMON_H_",
                    "extern int vflag;",
                    "void usage(void);",
                    "int compute(int x);",
                    "#endif",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (d_path / "helper.c").write_text(
            LF.join(
                [
                    "#include <stdio.h>",
                    '#include "common.h"',
                    f"int vflag = {idx_val};",
                    "void usage(void) {",
                    f'    printf("usage-{idx_val}{BS}n");',
                    "}",
                    "int compute(int x) {",
                    f"    return x * {mult} + vflag;",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        main_sig = "int main(void) {" if idx_val == 1 else "int main(int argc, char *argv[]) {"
        main_body = (
            [
                "#include <stdio.h>",
                '#include "common.h"',
                main_sig,
                f'    printf("%d{BS}n", compute(3));',
                "    return 0;",
                "}",
                "",
            ]
            if idx_val == 1
            else [
                "#include <stdio.h>",
                "#include <unistd.h>",
                '#include "common.h"',
                main_sig,
                "    int ch;",
                '    while ((ch = getopt(argc, argv, "v")) != -1) {',
                "        if (ch == 'v') vflag = 9;",
                "    }",
                f'    printf("%d:%s{BS}n", compute(3), argv[optind] ? argv[optind] : "none");',
                "    return 0;",
                "}",
                "",
            ]
        )
        (d_path / "main.c").write_text(LF.join(main_body), encoding="utf-8")

    applets_out = tmp_path / "applets"
    hdr_a, staged_a = stage_multicall_applet(
        "alpha",
        [alpha_dir / "helper.c", alpha_dir / "main.c"],
        applets_out,
    )
    hdr_b, staged_b = stage_multicall_applet(
        "beta",
        [beta_dir / "helper.c", beta_dir / "main.c"],
        applets_out,
    )
    assert hdr_a.is_file() and hdr_b.is_file()

    disp_c = tmp_path / "freebsd_multicall_main.c"
    disp_c.write_text(
        generate_multicall_dispatcher_c(
            ["alpha", "beta"],
            alias_links={"beta_alias": "beta", "alpha": "alpha"},
            total_entries=280,
        ),
        encoding="utf-8",
    )

    cc_bin = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    assert cc_bin is not None
    multicall_bin = tmp_path / "freebsd-usr-bin"
    comp = subprocess.run(
        [
            cc_bin,
            "-Wall",
            "-Wextra",
            "-Werror",
            *[str(p) for p in (*staged_a, *staged_b, disp_c)],
            "-o",
            str(multicall_bin),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert comp.returncode == 0, f"Multicall compile failed: {comp.stderr}"

    res_a = subprocess.run(
        [str(multicall_bin), "alpha"], capture_output=True, text=True, check=False
    )
    assert res_a.returncode == 0 and res_a.stdout.strip() == "31"

    res_b = subprocess.run(
        [str(multicall_bin), "beta_alias", "-v", "arg1"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_b.returncode == 0 and res_b.stdout.strip() == "309:arg1"

    res_ver = subprocess.run(
        [str(multicall_bin), "--version"], capture_output=True, text=True, check=False
    )
    assert res_ver.returncode == 0 and "280 entries" in res_ver.stdout

    res_list = subprocess.run(
        [str(multicall_bin), "--list"], capture_output=True, text=True, check=False
    )
    assert "beta_alias" in res_list.stdout

    # Invoking via symlink named "alpha.exe" tests argv[0] basename + .exe stripping!
    exe_link = tmp_path / "alpha.exe"
    exe_link.symlink_to(multicall_bin)
    res_link = subprocess.run([str(exe_link)], capture_output=True, text=True, check=False)
    assert res_link.returncode == 0 and res_link.stdout.strip() == "31"
