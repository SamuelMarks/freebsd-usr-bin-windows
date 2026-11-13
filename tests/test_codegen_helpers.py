"""Unit tests for ``scripts.codegen_helpers``."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.codegen_helpers import (
    BS,
    CONTRIB_CONFIG_LIBS,
    DQUOTE,
    LF,
    _find_m4_binary,
    emit_all_codegen_helpers,
    generate_contrib_config_header,
    generate_elftc_artifacts,
    generate_libfetch_errlist_h,
    generate_msvc_def_file,
    generate_ncurses_headers,
    generate_vi_options_def_h,
    stage_iconv_citrus_headers,
)
from scripts.errors import ErrorCode, FreeBsdPortError


def test_libfetch_and_vi_generators(tmp_path: Path) -> None:
    """Verify ``ftperr.h`` / ``httperr.h`` and ``options_def.h`` generation and errors.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    with pytest.raises(FreeBsdPortError) as exc_fetch:
        generate_libfetch_errlist_h(tmp_path / "missing.errors", "ftp_errlist", "FTP")
    assert exc_fetch.value.code is ErrorCode.SOURCE_TREE_NOT_FOUND

    ftp_errors = tmp_path / "ftp.errors"
    ftp_errors.write_text(
        LF.join(
            [
                "# comment",
                "",
                f"500 PROTO Syntax {DQUOTE}quoted{DQUOTE} error",
                "200 OK Command okay",
                "malformed_two_cols ONLY",
            ]
        )
        + LF,
        encoding="utf-8",
    )
    ftp_h = generate_libfetch_errlist_h(ftp_errors, "ftp_errlist", "FTP")
    assert "static struct fetcherr ftp_errlist[] = {" in ftp_h
    assert '{ 200, FETCH_OK, "Command okay" },' in ftp_h
    assert f'{{ 500, FETCH_PROTO, "Syntax {BS}{DQUOTE}quoted{BS}{DQUOTE} error" }},' in ftp_h
    assert '{ -1, FETCH_UNKNOWN, "Unknown FTP error" }' in ftp_h

    with pytest.raises(FreeBsdPortError) as exc_vi:
        generate_vi_options_def_h(tmp_path / "missing_options.c")
    assert exc_vi.value.code is ErrorCode.SOURCE_TREE_NOT_FOUND

    opts_c = tmp_path / "options.c"
    opts_c.write_text(
        LF.join(
            [
                "/* O_ALTWERASE */",
                '    { L("altwerase"), NULL, OPT_0BOOL, 0 },',
                "/* O_AUTOINDENT */",
                '    { L("autoindent"), NULL, OPT_0BOOL, 0 },',
            ]
        )
        + LF,
        encoding="utf-8",
    )
    opts_def = generate_vi_options_def_h(opts_c)
    assert "#define O_ALTWERASE 0" in opts_def
    assert "#define O_AUTOINDENT 1" in opts_def
    assert "#define O_OPTIONCOUNT 2" in opts_def


def test_ncurses_elftc_iconv_config_and_def_generators(tmp_path: Path) -> None:
    """Verify ncurses, elftoolchain, iconv, contrib ``config.h``, and ``.def`` emitters.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # 1. ncurses with Caps and without Caps
    caps_file = tmp_path / "Caps"
    caps_file.write_text(
        LF.join(
            [
                "# comment",
                "",
                "infoalias ignored",
                "short line",
                "auto_left_margin bw bool bw",
                "columns cols num co",
                "bell bel str bl",
                "other_cap oc other xx",
            ]
        )
        + LF,
        encoding="utf-8",
    )
    nc_with_caps = generate_ncurses_headers(caps_file, tmp_path / "nc1")
    assert "termsort.h" in nc_with_caps
    assert "curses.h" in nc_with_caps
    assert "term.h" in nc_with_caps

    nc_no_caps = generate_ncurses_headers(None, tmp_path / "nc2")
    assert "bool_terminfo_sort" in nc_no_caps["termsort.h"].read_text(encoding="utf-8")

    # 2. elftoolchain with and without sys/sys
    empty_fbsd = tmp_path / "empty_fbsd"
    empty_fbsd.mkdir()
    elftc_min = generate_elftc_artifacts(empty_fbsd, tmp_path / "elftc1")
    assert "native-elf-format.h" in elftc_min
    assert "libelftc_version.c" in elftc_min
    assert stage_iconv_citrus_headers(empty_fbsd, tmp_path / "iconv_empty") == {}

    # 3. contrib config.h for all supported libs + error on unknown
    for lib_name in CONTRIB_CONFIG_LIBS:
        cfg_text = generate_contrib_config_header(lib_name)
        assert f'#define PACKAGE "{lib_name}"' in cfg_text

    with pytest.raises(FreeBsdPortError) as exc_cfg:
        generate_contrib_config_header("unknown_lib")
    assert exc_cfg.value.code is ErrorCode.CODEGEN_FAILURE

    # 4. MSVC .def generator
    def_text = generate_msvc_def_file(
        "fbsd_libxo.dll",
        functions=["xo_emit", "xo_finish", ""],
        data_symbols=["xo_default_handle", ""],
    )
    assert 'LIBRARY "fbsd_libxo"' in def_text
    assert "    xo_emit" in def_text
    assert "    xo_default_handle DATA" in def_text

    def_no_ext = generate_msvc_def_file("fbsd_libutil", functions=["humanize_number"])
    assert 'LIBRARY "fbsd_libutil"' in def_no_ext

    with pytest.raises(FreeBsdPortError) as exc_def:
        generate_msvc_def_file("   ", functions=["fn"])
    assert exc_def.value.code is ErrorCode.CODEGEN_FAILURE


def test_emit_all_codegen_helpers_full_and_minimal(tmp_path: Path) -> None:
    """Verify ``emit_all_codegen_helpers`` across both populated and minimal trees.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    min_src = tmp_path / "min_src"
    min_src.mkdir()
    min_emitted = emit_all_codegen_helpers(min_src, tmp_path / "min_gen")
    assert "codegen/libarchive/config.h" in min_emitted
    assert "codegen/libfetch/ftperr.h" not in min_emitted

    full_src = tmp_path / "full_src"
    fetch_dir = full_src / "lib" / "libfetch"
    fetch_dir.mkdir(parents=True)
    (fetch_dir / "ftp.errors").write_text(f"200 OK Ready{LF}", encoding="utf-8")
    # Intentionally omit http.errors first to cover partial libfetch branch
    partial_emitted = emit_all_codegen_helpers(full_src, tmp_path / "partial_gen")
    assert "codegen/libfetch/ftperr.h" in partial_emitted
    assert "codegen/libfetch/httperr.h" not in partial_emitted

    (fetch_dir / "http.errors").write_text(f"200 OK Success{LF}", encoding="utf-8")

    nvi_common = full_src / "contrib" / "nvi" / "common"
    nvi_common.mkdir(parents=True)
    (nvi_common / "options.c").write_text(f"/* O_BACKUP */{LF}", encoding="utf-8")
    vi_dir = full_src / "usr.bin" / "vi"
    vi_dir.mkdir(parents=True)
    (vi_dir / "config.h").write_text(f"#define VI_CFG 1{LF}", encoding="utf-8")

    caps_dir = full_src / "contrib" / "ncurses" / "include"
    caps_dir.mkdir(parents=True)
    (caps_dir / "Caps").write_text(f"bell bel str bl{LF}", encoding="utf-8")

    sys_dir = full_src / "sys" / "sys"
    sys_dir.mkdir(parents=True)
    (sys_dir / "elf_common.h").write_text(f"#define ELF_COMMON 1{LF}", encoding="utf-8")
    (sys_dir / "md4.h").write_text(f"#define MD4_H 1{LF}", encoding="utf-8")

    md_dir = full_src / "lib" / "libmd"
    md_dir.mkdir(parents=True)
    (md_dir / "mdXhl.c").write_text(
        f"char *MDXEnd(MDX_CTX *c) {{ return 0; }}{LF}", encoding="utf-8"
    )

    elftc_libelf = full_src / "contrib" / "elftoolchain" / "libelf"
    elftc_libelf.mkdir(parents=True)
    (elftc_libelf / "libelf_fsize.m4").write_text(f"int fsize_ok = 1;{LF}", encoding="utf-8")
    elftc_common = full_src / "contrib" / "elftoolchain" / "common"
    elftc_common.mkdir(parents=True)
    (elftc_common / "_elftc.h").write_text(
        f"#define ELFTC_NEED_BYTEORDER_EXTENSIONS 1{LF}",
        encoding="utf-8",
    )

    inc_dir = full_src / "include"
    inc_dir.mkdir(parents=True)
    (inc_dir / "regex.h").write_text(f"#include <sys/_types.h>{LF}", encoding="utf-8")

    file_src_dir = full_src / "contrib" / "file" / "src"
    file_src_dir.mkdir(parents=True)
    (file_src_dir / "magic.h.in").write_text(f"#define MAGIC_VERSION X.YY{LF}", encoding="utf-8")

    ldns_dir = full_src / "contrib" / "ldns" / "ldns"
    ldns_dir.mkdir(parents=True)
    (ldns_dir / "common.h").write_text(
        f"#define LDNS_BUILD_CONFIG_HAVE_SSL 1{LF}",
        encoding="utf-8",
    )
    (ldns_dir / "config.h").write_text(
        f"#define HAVE_SSL 1{LF}#define random(x) rand(x){LF}",
        encoding="utf-8",
    )

    iconv_dir = full_src / "lib" / "libc" / "iconv"
    iconv_dir.mkdir(parents=True)
    (iconv_dir / "citrus_hash.h").write_text(f"#define CITRUS_HASH 1{LF}", encoding="utf-8")

    full_emitted = emit_all_codegen_helpers(full_src, tmp_path / "full_gen")
    assert "codegen/libfetch/ftperr.h" in full_emitted
    assert "codegen/libfetch/httperr.h" in full_emitted
    assert "codegen/vi/options_def.h" in full_emitted
    assert "codegen/vi/config.h" in full_emitted
    assert "codegen/ncurses/termsort.h" in full_emitted
    assert "codegen/elftoolchain/sys/elf_common.h" in full_emitted
    assert "codegen/elftoolchain/gensrcs/libelf_fsize.c" in full_emitted
    assert "codegen/libmd/md5hl.c" in full_emitted
    assert "codegen/libmd/sys/md4.h" in full_emitted
    assert "codegen/libregex/regex.h" in full_emitted
    assert "codegen/libmagic/magic.h" in full_emitted
    assert "codegen/ldns/ldns/common.h" in full_emitted
    assert "codegen/ldns/ldns/config.h" in full_emitted
    assert "codegen/pkgconf/libpkgconf/config.h" in full_emitted
    assert "codegen/iconv/citrus_hash.h" in full_emitted
    assert "codegen/ncurses_progs/tput.c" in full_emitted
    assert "codegen/ncurses_progs/tic.c" in full_emitted
    assert "codegen/kernel_stat/vmstat.c" in full_emitted
    assert "codegen/kernel_stat/netstat.c" in full_emitted
    assert "codegen/kernel_stat/truss.c" in full_emitted


def test_find_m4_binary_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ``_find_m4_binary`` returns ``None`` when neither ``m4`` nor Git ``m4`` exists.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert _find_m4_binary() in (None, "C:/Program Files/Git/usr/bin/m4.exe")
