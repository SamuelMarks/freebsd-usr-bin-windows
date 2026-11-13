"""Unit tests for ``scripts.parse_freebsd_usr_bin``."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.parse_freebsd_usr_bin import (
    BS,
    LIBADD_TO_SECTION3_TARGET,
    NL,
    TAB,
    BinarySpec,
    UtilitySpec,
    audit_freebsd_usr_bin,
    audit_freebsd_usr_bin_binaries,
    classify_tier,
    evaluate_makefile_condition,
    expand_makefile_vars,
    generate_bc_strgen_c,
    generate_dispatcher_c,
    generate_fake_gperf_c,
    generate_netstat_nlist,
    locate_default_freebsd_src,
    main,
    map_libadd_to_section3_targets,
    parse_args,
    parse_cflags_tokens,
    parse_makefile_recursive,
    resolve_sources_for_prog,
    stage_build_time_generated_files,
    write_manifest_files,
)


def test_expand_vars_locate_src_and_libadd_mapping(tmp_path: Path) -> None:
    """Verify variable modifiers, ``freebsd-src`` auto-detection, and ``LIBADD`` mapping.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    env = {
        "CURDIR": "/usr/src/usr.bin/bmake",
        "MODE": "DeV",
        "EMPTY_Check": "val",
    }
    assert expand_makefile_vars("${CURDIR:H}", env) == "/usr/src/usr.bin"
    assert expand_makefile_vars("${CURDIR:H:H}", env) == "/usr/src"
    assert expand_makefile_vars("${CURDIR:T}", env) == "bmake"
    assert expand_makefile_vars("${MODE:tl}", env) == "dev"
    assert expand_makefile_vars("${MODE:tu}", env) == "DEV"
    assert expand_makefile_vars("${EMPTY_Check}", env) == "val"
    assert expand_makefile_vars("${MISSING:Ufallback}", env) == "fallback"
    assert expand_makefile_vars("${STILL_MISSING}", env) == "${STILL_MISSING}"

    # Repo root with nested ./freebsd-src vs sibling ../freebsd-src
    ws = tmp_path / "ws"
    repo_dir = ws / "repo"
    repo_dir.mkdir(parents=True)
    assert locate_default_freebsd_src(repo_dir) == ws / "freebsd-src"

    nested = repo_dir / "freebsd-src"
    nested.mkdir()
    assert locate_default_freebsd_src(repo_dir) == nested

    # All 68 LIBADD keys + custom fallback + deduplication + None filtering
    mapped = map_libadd_to_section3_targets(
        [*LIBADD_TO_SECTION3_TARGET.keys(), "archive", "customxyz"]
    )
    assert "fbsd_libarchive" in mapped
    assert "fbsd_libcustomxyz" in mapped
    assert mapped.count("fbsd_libarchive") == 1


def test_evaluate_conditions_and_parse_cflags(tmp_path: Path) -> None:
    """Verify ``evaluate_makefile_condition`` and ``parse_cflags_tokens`` across all branches.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    env = {
        "MK_CASPER": "no",
        "MK_ICONV": "yes",
        "BOOTSTRAPPING": "1",
        "ZERO_VAR": "0",
        "INC_SUB": "include",
    }
    assert evaluate_makefile_condition("ifdef", "BOOTSTRAPPING", env) is True
    assert evaluate_makefile_condition("ifdef", "!BOOTSTRAPPING", env) is False
    assert evaluate_makefile_condition("ifndef", "UNDEF_VAR", env) is True
    assert evaluate_makefile_condition("if", "", env) is True
    assert evaluate_makefile_condition("if", "(defined(BOOTSTRAPPING)) && !defined(NOPE)", env)
    assert evaluate_makefile_condition("if", '${MK_CASPER} != "no" || ${MK_ICONV} == "yes"', env)
    assert evaluate_makefile_condition("if", '${MK_CASPER} != "no"', env) is False
    assert evaluate_makefile_condition("if", '${UNKNOWN_MK_VAR} != "no"', env) is True
    assert evaluate_makefile_condition("if", "!${ZERO_VAR}", env) is True
    assert evaluate_makefile_condition("if", "${BOOTSTRAPPING}", env) is True

    abs_inc = tmp_path / "abs_inc"
    abs_inc.mkdir()
    incs, defs = parse_cflags_tokens(
        f"-O2 -I {abs_inc} -I${{INC_SUB}} -I${{UNDEF}} -I{abs_inc} "
        "-DFOO=1 -DBAR -DFOO=1 -D${UNDEF_DEF}",
        tmp_path,
        env,
    )
    assert str(abs_inc.resolve()) in incs
    assert str((tmp_path / "include").resolve()) in incs
    assert defs == ("FOO=1", "BAR")


def test_parse_makefile_recursive_conditionals_and_operators(tmp_path: Path) -> None:
    """Verify recursive Makefile parsing, ``.if/.elif/.else/.endif``, ``.PATH``, and operators.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    sub_dir = tmp_path / "tool"
    ext_dir = tmp_path / "contrib" / "tool"
    sub_dir.mkdir(parents=True)
    ext_dir.mkdir(parents=True)

    inc_a = sub_dir / "Makefile.inc"
    inc_b = sub_dir / "Makefile.common"
    mk = sub_dir / "Makefile"

    inc_a.write_text(
        NL.join(
            [
                "# Comment line",
                "PROG?= default_prog",
                "CFLAGS= -O2",
                "VERSION!= echo 1.0",
                ".PATH:",
                f".PATH: ${{UNRESOLVED}} ../contrib/tool {ext_dir} {ext_dir}",
            ]
        ),
        encoding="utf-8",
    )
    inc_b.write_text(
        NL.join(
            [
                '.include "Makefile.inc"',
                '.include "nonexistent.mk"',
                "PROG?= ignored_prog",
                "CFLAGS+= -Wall",
                ".unknown_dot_directive",
                '.if ${MK_CASPER} != "no"',
                "CFLAGS+= -DSKIPPED_CASPER",
                ".ifdef NESTED_SKIPPED",
                "CFLAGS+= -DNESTED_SKIPPED",
                ".endif",
                '.elif ${MK_ICONV} == "yes"',
                "CFLAGS+= -DUSE_ICONV",
                ".else",
                "CFLAGS+= -DSKIPPED_ELSE",
                ".endif",
                ".ifdef UNDEF_FEATURE",
                "CFLAGS+= -DSKIP_IFDEF",
                ".else",
                "CFLAGS+= -DTAKEN_ELSE",
                ".endif",
                ".endif",
            ]
        ),
        encoding="utf-8",
    )
    mk.write_text(
        NL.join(
            [
                f'.include "{inc_b}"',
                '.include "Makefile.common"',
                f"SRCS= a.c {BS}",
                "      b.c",
            ]
        ),
        encoding="utf-8",
    )

    env: dict[str, str] = {"PROG": "", "MK_CASPER": "no", "MK_ICONV": "yes"}
    search_paths: list[Path] = [sub_dir.resolve()]
    parse_makefile_recursive(sub_dir / "missing.mk", sub_dir, env, search_paths)

    parse_makefile_recursive(mk, sub_dir, env, search_paths)
    visited = {mk.resolve()}
    parse_makefile_recursive(mk, sub_dir, env, search_paths, visited)

    assert env["PROG"] == "default_prog"
    assert "-DUSE_ICONV" in env["CFLAGS"]
    assert "-DTAKEN_ELSE" in env["CFLAGS"]
    assert "-DSKIPPED_CASPER" not in env["CFLAGS"]
    assert "-DSKIPPED_ELSE" not in env["CFLAGS"]
    assert "VERSION" not in env
    assert env["SRCS"].split() == ["a.c", "b.c"]
    assert ext_dir.resolve() in search_paths


def test_code_generators_gperf_nlist_bc_dispatcher(tmp_path: Path) -> None:
    """Verify ``generate_fake_gperf_c``, ``generate_netstat_nlist``, ``generate_bc_strgen_c``.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    gperf1 = tmp_path / "with_struct.gperf"
    gperf1.write_text(
        NL.join(
            [
                "%{",
                "#include <unistd.h>",
                "%}",
                "struct custom_map { const char *name; int key; int valid; };",
                "%%",
                "ARG_MAX, _SC_ARG_MAX",
                "ignored_single_token",
                "%%",
                "/* trailing code */",
            ]
        ),
        encoding="utf-8",
    )
    out1 = generate_fake_gperf_c(gperf1)
    assert "static const struct custom_map wordlist[] = {" in out1
    assert '{ "ARG_MAX", _SC_ARG_MAX, 1 },' in out1
    assert "/* trailing code */" in out1

    gperf2 = tmp_path / "no_struct.gperf"
    gperf2.write_text(
        NL.join(
            [
                "unmatched header line",
                "%%",
                "PATH, _CS_PATH",
                "%%",
            ]
        ),
        encoding="utf-8",
    )
    out2 = generate_fake_gperf_c(gperf2)
    assert "static const struct map {" in out2
    assert '{ "PATH", _CS_PATH, 1 },' in out2

    gperf3 = tmp_path / "bare_struct.gperf"
    gperf3.write_text(f"struct{NL}%%{NL}%%{NL}", encoding="utf-8")
    out3 = generate_fake_gperf_c(gperf3)
    assert "static const struct map wordlist[] = {" in out3

    nlist_file = tmp_path / "nlist_symbols"
    nlist_file.write_text(
        NL.join(
            [
                "# comment",
                "",
                "only_one_token",
                "all _ripcbinfo",
                "inet _tcbinfo",
            ]
        ),
        encoding="utf-8",
    )
    nl_c, nl_h = generate_netstat_nlist(nlist_file)
    assert '{ .n_name = "_ripcbinfo" },' in nl_c
    assert f"#define{TAB}N__TCBINFO{TAB}1" in nl_h

    bc_in = tmp_path / "lib.bc"
    bc_in.write_text(
        NL.join(
            [
                "# SPDX-License-Identifier: BSD-2-Clause",
                "",
                f"{TAB}scale = 20",
                f'print "ok{BS}n"',
            ]
        ),
        encoding="utf-8",
    )
    bc_c = generate_bc_strgen_c(
        bc_in,
        "bc_lib",
        label="bc_lib_name",
        define="BC_ENABLED",
        remove_tabs=True,
    )
    assert "#if BC_ENABLED" in bc_c
    assert 'const char *bc_lib_name = "lib.bc";' in bc_c
    assert f'"scale = 20{BS}n"' in bc_c

    bc_empty = tmp_path / "empty.txt"
    bc_empty.write_text("single_line_no_blank", encoding="utf-8")
    bc_empty_c = generate_bc_strgen_c(bc_empty, "bc_empty", remove_tabs=False)
    assert f'"single_line_no_blank{BS}n"' in bc_empty_c

    bc_truly_empty = tmp_path / "truly_empty.txt"
    bc_truly_empty.write_text(NL, encoding="utf-8")
    bc_truly_empty_c = generate_bc_strgen_c(bc_truly_empty, "bc_none")
    assert '""' in bc_truly_empty_c

    disp_known = generate_dispatcher_c("pagesize")
    assert "sysconf" in disp_known
    disp_custom = generate_dispatcher_c("custom_synthetic_applet")
    assert 'const char *prog = "custom_synthetic_applet";' in disp_custom


def test_classify_tier_and_resolve_sources(tmp_path: Path) -> None:
    """Verify ``classify_tier`` and ``resolve_sources_for_prog`` across all branches.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    srctop = tmp_path / "freebsd-src"
    contrib = srctop / "contrib" / "foo"
    usr_bin_tool = srctop / "usr.bin" / "tool"
    gen_sub = tmp_path / "gen" / "tool"
    contrib.mkdir(parents=True)
    usr_bin_tool.mkdir(parents=True)
    gen_sub.mkdir(parents=True)

    assert classify_tier("command", False, (), [usr_bin_tool], srctop) == 6
    assert classify_tier("foo", True, (), [contrib], srctop) == 4
    assert classify_tier("top", True, ("kvm",), [usr_bin_tool], srctop) == 5
    assert classify_tier("ncal", True, ("tinfow",), [usr_bin_tool], srctop) == 3
    assert classify_tier("du", True, ("util",), [usr_bin_tool], srctop) == 2
    assert classify_tier("banner", True, (), [usr_bin_tool], srctop) == 1

    (gen_sub / "gen_only.c").write_text("int g;", encoding="utf-8")
    orig_direct = usr_bin_tool / "direct.c"
    orig_direct.write_text("int d;", encoding="utf-8")
    staged_direct = tmp_path / "staged" / "direct.c"
    staged_direct.parent.mkdir(parents=True)
    staged_direct.write_text("int d_patched;", encoding="utf-8")
    (usr_bin_tool / "gram.y").write_text("%%", encoding="utf-8")
    (usr_bin_tool / "scan.l").write_text("%%", encoding="utf-8")
    (usr_bin_tool / "cxx_src.cc").write_text("int c;", encoding="utf-8")

    resolved = resolve_sources_for_prog(
        ["${IGNORED}", "header.h", "gen_only.c", "direct.c", "gram.c", "scan.c", "missing.c"],
        [usr_bin_tool],
        gen_sub,
        is_cxx=False,
        staged_map={orig_direct.resolve(): staged_direct.resolve()},
    )
    assert len(resolved) == 4
    assert str(staged_direct.resolve()) in resolved

    resolved_cxx = resolve_sources_for_prog(
        ["cxx_src.c"],
        [usr_bin_tool],
        None,
        is_cxx=True,
    )
    assert len(resolved_cxx) == 1


def test_stage_and_audit_synthetic_and_real_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify ``audit_freebsd_usr_bin_binaries`` across synthetic, patched, and real trees.

    Args:
        tmp_path: Pytest temporary directory fixture.
        capsys: Pytest stdout/stderr capture fixture.
    """
    empty_src = tmp_path / "nonexistent_src"
    assert main(["--freebsd-src", str(empty_src), "--output-dir", str(tmp_path / "out")]) == 1
    assert "Error:" in capsys.readouterr().err

    synth_src = tmp_path / "synth_freebsd"
    synth_usr_bin = synth_src / "usr.bin"
    synth_usr_bin.mkdir(parents=True)
    (synth_usr_bin / "Makefile").write_text(f"SUBDIR= dc bmake command{NL}", encoding="utf-8")

    # Directory without Makefile (custom_nomk) + known script dir without Makefile (dc)
    (synth_usr_bin / "dc").mkdir()
    (synth_usr_bin / "custom_nomk").mkdir()

    # Directory with Makefile that defines no PROG and is not in SCRIPT_AND_SPECIAL_DIRS
    empty_mk_dir = synth_usr_bin / "empty_mk_dir"
    empty_mk_dir.mkdir()
    (empty_mk_dir / "Makefile").write_text(f"FILES= sample.dat{NL}", encoding="utf-8")

    # Dedicated alpha directory coming before multiprog to test deduplication False branch
    alpha_ded = synth_usr_bin / "alpha"
    alpha_ded.mkdir()
    (alpha_ded / "Makefile").write_text(f"PROG= alpha{NL}SRCS= alpha_ded.c{NL}", encoding="utf-8")
    (alpha_ded / "alpha_ded.c").write_text(f"int main(void) {{ return 0; }}{NL}", encoding="utf-8")

    # Multi-PROGS + PROGS_CXX directory
    multi_dir = synth_usr_bin / "multiprog"
    multi_dir.mkdir()
    (multi_dir / "Makefile").write_text(
        NL.join(
            [
                "PROGS= alpha gamma",
                "PROGS_CXX= beta_cxx",
                "SRCS.gamma= alpha.c gen_hdr.h gram.y scan.l",
                "CFLAGS.gamma= -I. -DALPHA_MODE=1",
                "LIBADD.gamma= xo",
                "LINKS.gamma= /usr/bin/gamma /usr/bin/gamma_alias "
                "/usr/bin/gamma /usr/bin/gamma_alias /usr/bin/gamma /usr/bin/gamma "
                "/usr/bin/other /usr/bin/skip_me",
                "LINKS+= ${UNEXP} /usr/bin/skip_unexp",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (multi_dir / "alpha.c").write_text(f"int main(void) {{ return 0; }}{NL}", encoding="utf-8")
    (multi_dir / "gram.y").write_text(f"%%{NL}", encoding="utf-8")
    (multi_dir / "scan.l").write_text(f"%%{NL}", encoding="utf-8")
    (multi_dir / "beta_cxx.cc").write_text(f"int main() {{ return 0; }}{NL}", encoding="utf-8")

    # Container directory (bsdiff) with two children sharing common.c, bz2, and a link
    bsdiff_cont = synth_usr_bin / "bsdiff"
    (bsdiff_cont / "bsdiff").mkdir(parents=True)
    (bsdiff_cont / "bspatch").mkdir(parents=True)
    (bsdiff_cont / "notes").mkdir()
    (bsdiff_cont / "Makefile.inc").write_text(f"CFLAGS+= -DBSDIFF_COMMON{NL}", encoding="utf-8")
    (bsdiff_cont / "common.c").write_text(
        f"int common_fn(void) {{ return 0; }}{NL}", encoding="utf-8"
    )
    (bsdiff_cont / "bsdiff" / "Makefile").write_text(
        f".PATH: ..{NL}PROG= bsdiff{NL}SRCS= bsdiff.c common.c{NL}"
        f"LIBADD= bz2{NL}LINKS= /usr/bin/bsdiff /usr/bin/shared_lnk{NL}",
        encoding="utf-8",
    )
    (bsdiff_cont / "bsdiff" / "bsdiff.c").write_text(
        f"int main(void) {{ return 0; }}{NL}",
        encoding="utf-8",
    )
    (bsdiff_cont / "bspatch" / "Makefile").write_text(
        f".PATH: ..{NL}PROG= bspatch{NL}SRCS= bspatch.c common.c{NL}"
        f"LIBADD= bz2{NL}LINKS= /usr/bin/bspatch /usr/bin/shared_lnk{NL}",
        encoding="utf-8",
    )
    (bsdiff_cont / "bspatch" / "bspatch.c").write_text(
        f"int main(void) {{ return 0; }}{NL}",
        encoding="utf-8",
    )

    # Empty container directory (tip) with no sub-Makefiles to cover empty container branch
    (synth_usr_bin / "tip").mkdir()

    bmake_dir = synth_usr_bin / "bmake"
    bmake_dir.mkdir()
    (bmake_dir / "Makefile.inc").write_text(f"WARNS?= 3{NL}", encoding="utf-8")
    (bmake_dir / "Makefile").write_text(
        f"PROG= ${{.CURDIR:T}}{NL}SRCS= main.c{NL}LINKS= /usr/bin/bmake /usr/bin/make{NL}",
        encoding="utf-8",
    )
    (bmake_dir / "main.c").write_text(f"int main(void) {{ return 0; }}{NL}", encoding="utf-8")

    # Declarative patch applied to bmake/main.c
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    (patches_dir / "bmake.patch").write_text(
        NL.join(
            [
                "--- a/usr.bin/bmake/main.c",
                "+++ b/usr.bin/bmake/main.c",
                "@@ -1 +1 @@",
                "-int main(void) { return 0; }",
                "+int main(void) { return 0; /* patched */ }",
            ]
        )
        + NL,
        encoding="utf-8",
    )

    cmd_dir = synth_usr_bin / "command"
    cmd_dir.mkdir()
    (cmd_dir / "Makefile").write_text(f"SCRIPTS= command.sh{NL}", encoding="utf-8")

    bc_gen = synth_src / "contrib" / "bc" / "gen"
    bc_gen.mkdir(parents=True)
    (bc_gen / "lib.bc").write_text(f"{NL}scale=20{NL}", encoding="utf-8")
    lex_dir = synth_usr_bin / "lex"
    lex_dir.mkdir()
    (lex_dir / "Makefile").write_text(f"PROG= lex{NL}SRCS= main.c{NL}", encoding="utf-8")
    (lex_dir / "initparse.c").write_text(f"int p;{NL}", encoding="utf-8")

    ftp_dir = synth_usr_bin / "ftp"
    ftp_dir.mkdir()
    (ftp_dir / "Makefile").write_text(f"PROG= ftp{NL}SRCS= main.c{NL}", encoding="utf-8")
    (ftp_dir / "main.c").write_text(f"int main(void) {{ return 0; }}{NL}", encoding="utf-8")
    (ftp_dir / "tnftp_config.h").write_text(
        f"#define HAVE_STRUCT_SOCKADDR_IN_SIN_LEN 1{NL}", encoding="utf-8"
    )

    for special_name, prog_val in (
        ("mt", "mt"),
        ("vacation", "vacation"),
        ("ncurses", "tput"),
        ("vmstat", "vmstat"),
        ("localedef", "localedef"),
        ("grep", "grep"),
    ):
        sp_dir = synth_usr_bin / special_name
        sp_dir.mkdir()
        (sp_dir / "Makefile").write_text(
            f"PROG= {prog_val}{NL}SRCS= main.c{NL}",
            encoding="utf-8",
        )
        (sp_dir / "main.c").write_text(f"int main(void) {{ return 0; }}{NL}", encoding="utf-8")

    ofed_dir = synth_usr_bin / "ofed"
    ofed_dir.mkdir()
    (ofed_dir / "Makefile").write_text(f"PROG= ofed{NL}SRCS= main.c{NL}", encoding="utf-8")
    (ofed_dir / "main.c").write_text(f"int main(void) {{ return 0; }}{NL}", encoding="utf-8")

    synth_out = tmp_path / "synth_out"
    # Direct _parse_single_makefile_dir call before codegen exercises missing-file branches
    from scripts.parse_freebsd_usr_bin import _parse_single_makefile_dir

    for pre_sub in ("mt", "vacation", "ncurses", "vmstat", "localedef", "grep"):
        _parse_single_makefile_dir(
            (synth_usr_bin / pre_sub).resolve(),
            pre_sub,
            synth_src,
            tmp_path / "empty_cg",
        )

    top_mks, synth_specs, synth_bins = audit_freebsd_usr_bin_binaries(
        synth_src,
        synth_out,
        patches_dir=patches_dir,
        heavy_subtrees=frozenset({"ofed"}),
    )
    # Second invocation onto same synth_out hits pre-existing fallback dispatcher branch
    audit_freebsd_usr_bin_binaries(synth_src, synth_out)
    assert top_mks == ["Makefile"]
    assert len(synth_specs) == 18
    gamma_bin = next(b for b in synth_bins if b.prog == "gamma")
    assert gamma_bin.yacc_sources
    assert gamma_bin.lex_sources
    assert gamma_bin.generated_headers == ("gen_hdr.h",)
    assert gamma_bin.section3_targets == ("fbsd_libxo",)
    assert gamma_bin.links == ("gamma_alias",)

    _, compat_specs = audit_freebsd_usr_bin(synth_src, tmp_path / "compat_out")
    assert len(compat_specs) == 18

    json_p, cmake_p = write_manifest_files(top_mks, synth_specs, synth_out, binaries=synth_bins)
    assert json_p.is_file()
    assert cmake_p.is_file()

    real_freebsd_src = locate_default_freebsd_src()
    real_out = tmp_path / "real_out"
    rc = main(["--freebsd-src", str(real_freebsd_src), "--output-dir", str(real_out)])
    assert rc == 0

    manifest_data = json.loads(
        (real_out / "freebsd_usr_bin_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_data["total_entries"] == 280
    assert len(manifest_data["top_makefiles"]) == 6
    assert manifest_data["utility_count"] == 274
    assert manifest_data["binary_count"] >= 285

    for util in manifest_data["utilities"]:
        assert len(util["sources"]) >= 1, f"No sources resolved for {util['name']}"

    parsed = parse_args(
        [
            "--freebsd-src",
            str(synth_src),
            "--output-dir",
            str(synth_out),
            "--build-clang",
            "--build-ofed",
            "--build-kyua",
        ]
    )
    assert parsed.freebsd_src == synth_src
    assert parsed.build_clang and parsed.build_ofed and parsed.build_kyua
    old_argv = sys.argv
    sys.argv = [
        "parse_freebsd_usr_bin.py",
        "--freebsd-src",
        str(empty_src),
        "--output-dir",
        str(synth_out),
    ]
    try:
        script_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "parse_freebsd_usr_bin.py"
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(script_path), run_name="__main__")
        assert exc_info.value.code == 1
    finally:
        sys.argv = old_argv
    capsys.readouterr()

    spec = UtilitySpec(
        name="true",
        prog="true",
        tier=1,
        is_cxx=False,
        sources=("true.c",),
        include_dirs=(".",),
        libs=(),
        links=(),
        scripts=(),
    )
    bspec = BinarySpec(
        prog="true",
        subdir="true",
        tier=1,
        is_cxx=False,
        sources=("true.c",),
        yacc_sources=(),
        lex_sources=(),
        generated_headers=(),
        include_dirs=(".",),
        compile_defs=(),
        raw_libs=(),
        section3_targets=(),
        links=(),
        scripts=(),
    )
    assert spec.prog == bspec.prog
    assert stage_build_time_generated_files(empty_src, tmp_path / "empty_gen")
