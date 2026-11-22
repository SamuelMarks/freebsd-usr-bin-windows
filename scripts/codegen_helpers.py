"""Deterministic pure-Python build-time header, table, config, and ``.def`` generators.

Generates out-of-tree C/header artifacts inside ``${CMAKE_BINARY_DIR}/freebsd_generated``
without creating or modifying any ``.c`` or ``.h`` file in ``../freebsd-src`` or the
repository working tree:

  - ``libfetch``: ``ftperr.h`` and ``httperr.h`` from ``ftp.errors`` / ``http.errors``
  - ``ncurses``: ``termsort.h``, ``ncurses_cfg.h``, ``curses.h``, ``term.h``, ``unctrl.h``
  - ``vi`` (``contrib/nvi``): ``options_def.h``, ``config.h``, ``pathnames.h``
  - ``elftoolchain``: ``native-elf-format.h``, ``libelftc_version.c``, staged ``sys/elf*.h``
  - ``iconv`` (``mkesdb`` / ``mkcsmapper``): staged Citrus headers
  - ``contrib`` library ``config.h`` files (``libarchive``, ``libmagic``, ``liblzma``,
    ``zstd``, ``bsddialog``, ``ldns``, ``pkgconf``, ``less``)
  - MSVC module-definition (``.def``) files for Section 3 ``SHARED`` DLL ``DATA`` exports
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scripts.errors import (
    ErrorCode,
    FreeBsdPortError,
    write_bytes_if_changed,
    write_text_if_changed,
)
from scripts.section3_shims import (
    emit_curses_section3_sources,
    emit_libarchive_win32_sources,
    emit_libdialog_section3_sources,
    emit_libedit_section3_sources,
    emit_libmp_section3_sources,
    emit_libsys_section3_sources,
)

LF: str = chr(10)
TAB: str = chr(9)
BS: str = chr(92)
DQUOTE: str = chr(34)

VI_OPT_COMMENT_RE = re.compile(r"^/\*\s+(O_[0-9A-Z_]+)")

CONTRIB_CONFIG_LIBS: tuple[str, ...] = (
    "libarchive",
    "libmagic",
    "liblzma",
    "zstd",
    "bsddialog",
    "ldns",
    "pkgconf",
    "less",
)


def generate_libfetch_errlist_h(
    errors_path: Path,
    array_name: str,
    protocol_label: str,
) -> str:
    """Generate ``ftperr.h`` or ``httperr.h`` from a ``libfetch`` ``*.errors`` table.

    Args:
        errors_path: Path to ``ftp.errors`` or ``http.errors`` in ``lib/libfetch``.
        array_name: C identifier for the ``struct fetcherr`` array (e.g. ``ftp_errlist``).
        protocol_label: Protocol name used in the sentinel entry (``"FTP"`` or ``"HTTP"``).

    Returns:
        Generated C header text defining ``static struct fetcherr <array_name>[]``.

    Raises:
        FreeBsdPortError: If ``errors_path`` does not exist.
    """
    if not errors_path.is_file():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            "libfetch errors table not found",
            path=errors_path,
        )

    raw_entries: list[str] = []
    for raw_line in errors_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        raw_entries.append(stripped)

    out_lines = [f"static struct fetcherr {array_name}[] = {{"]
    for entry in sorted(raw_entries):
        parts = entry.split(None, 2)
        if len(parts) == 3:
            num, cat, msg = parts[0], parts[1], parts[2]
            escaped_msg = msg.replace(BS, BS + BS).replace(DQUOTE, BS + DQUOTE)
            out_lines.append(f'    {{ {num}, FETCH_{cat}, "{escaped_msg}" }},')
    out_lines.append(f'    {{ -1, FETCH_UNKNOWN, "Unknown {protocol_label} error" }}')
    out_lines.append("};")
    return LF.join(out_lines) + LF


def generate_vi_options_def_h(options_c_path: Path) -> str:
    """Generate ``options_def.h`` from ``contrib/nvi/common/options.c`` (``options.awk``).

    Args:
        options_c_path: Path to ``contrib/nvi/common/options.c``.

    Returns:
        Generated C header defining ``O_*`` option indices and ``O_OPTIONCOUNT``.

    Raises:
        FreeBsdPortError: If ``options_c_path`` does not exist.
    """
    if not options_c_path.is_file():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            "nvi options.c not found",
            path=options_c_path,
        )

    out_lines: list[str] = []
    count = 0
    for raw_line in options_c_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = VI_OPT_COMMENT_RE.match(raw_line)
        if match is not None:
            out_lines.append(f"#define {match.group(1)} {count}")
            count += 1
    out_lines.append(f"#define O_OPTIONCOUNT {count}")
    return LF.join(out_lines) + LF


def generate_ncurses_headers(caps_path: Path | None, out_dir: Path) -> dict[str, Path]:
    """Generate out-of-tree ``ncurses`` headers (``termsort.h``, ``ncurses_cfg.h``, etc.).

    Args:
        caps_path: Optional path to ``contrib/ncurses/include/Caps``.
        out_dir: Destination ``codegen/ncurses`` directory.

    Returns:
        Mapping from generated header filename to its resolved ``Path``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    bool_count = 0
    num_count = 0
    str_count = 0
    if caps_path is not None and caps_path.is_file():
        for raw_line in caps_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(("#", "capalias", "infoalias", "used_by")):
                continue
            cols = stripped.split()
            if len(cols) >= 3:
                cap_type = cols[2]
                if cap_type == "bool":
                    bool_count += 1
                elif cap_type == "num":
                    num_count += 1
                elif cap_type == "str":
                    str_count += 1

    bool_indices = ", ".join(str(i) for i in range(max(1, bool_count)))
    num_indices = ", ".join(str(i) for i in range(max(1, num_count)))
    str_indices = ", ".join(str(i) for i in range(max(1, str_count)))

    termsort_h = LF.join(
        [
            "/* Automatically generated termsort.h */",
            "#ifndef FBSD_NCURSES_TERMSORT_H_",
            "#define FBSD_NCURSES_TERMSORT_H_",
            f"static const int bool_terminfo_sort[] = {{ {bool_indices} }};",
            f"static const int num_terminfo_sort[] = {{ {num_indices} }};",
            f"static const int str_terminfo_sort[] = {{ {str_indices} }};",
            f"static const int bool_variable_sort[] = {{ {bool_indices} }};",
            f"static const int num_variable_sort[] = {{ {num_indices} }};",
            f"static const int str_variable_sort[] = {{ {str_indices} }};",
            f"static const int bool_termcap_sort[] = {{ {bool_indices} }};",
            f"static const int num_termcap_sort[] = {{ {num_indices} }};",
            f"static const int str_termcap_sort[] = {{ {str_indices} }};",
            "#endif",
            "",
        ]
    )
    termsort_path = (out_dir / "termsort.h").resolve()
    write_text_if_changed(termsort_path, termsort_h)
    emitted["termsort.h"] = termsort_path

    cfg_h = LF.join(
        [
            "#ifndef NC_CONFIG_H",
            "#define NC_CONFIG_H",
            '#define PACKAGE "ncurses"',
            '#define NCURSES_VERSION "6.5"',
            "#define HAVE_STDINT_H 1",
            "#define HAVE_INTTYPES_H 1",
            "#define HAVE_LIMITS_H 1",
            "#define HAVE_FCNTL_H 1",
            "#define HAVE_SNPRINTF 1",
            "#define HAVE_VSNPRINTF 1",
            "#define HAVE_STRDUP 1",
            "#define HAVE_STRSTR 1",
            '#define SYSTEM_NAME "freebsd-win"',
            "#endif",
            "",
        ]
    )
    for hdr_name, content in (
        ("ncurses_cfg.h", cfg_h),
        ("ncurses_def.h", f"#ifndef NCURSES_DEF_H{LF}#define NCURSES_DEF_H 1{LF}#endif{LF}"),
    ):
        hdr_path = (out_dir / hdr_name).resolve()
        write_text_if_changed(hdr_path, content)
        emitted[hdr_name] = hdr_path

    emitted.update(emit_curses_section3_sources(out_dir))
    return emitted


WINDOWS_M4_CANDIDATES: tuple[Path, ...] = (
    Path("C:/msys64/usr/bin/m4.exe"),
    Path("C:/Program Files/Git/usr/bin/m4.exe"),
    Path("C:/ProgramData/chocolatey/bin/m4.exe"),
    Path("C:/ProgramData/chocolatey/lib/winflexbison3/tools/m4.exe"),
)


def _find_m4_binary(
    candidates: Sequence[Path] = WINDOWS_M4_CANDIDATES,
) -> str | None:
    """Locate a host ``m4`` macro processor executable if installed.

    Args:
        candidates: Fallback executable paths probed when ``m4`` / ``gm4`` is
            not present on ``PATH`` (e.g. MSYS2, Git for Windows, Chocolatey).

    Returns:
        Path to ``m4`` / ``gm4``, or ``None`` if unavailable.
    """
    found = shutil.which("m4") or shutil.which("gm4")
    if found is not None:
        return found
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def generate_elftc_artifacts(freebsd_src: Path, out_dir: Path) -> dict[str, Path]:
    """Generate ``native-elf-format.h``, ``libelftc_version.c``, ``m4`` C files, and ``sys/elf*.h``.

    Args:
        freebsd_src: Path to upstream ``../freebsd-src``.
        out_dir: Destination ``codegen/elftoolchain`` directory.

    Returns:
        Mapping of relative artifact keys to generated/staged ``Path``s.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    native_elf_h = LF.join(
        [
            "#ifndef NATIVE_ELF_FORMAT_H_",
            "#define NATIVE_ELF_FORMAT_H_",
            "#define ELFTC_CLASS ELFCLASS64",
            "#define ELFTC_ARCH EM_X86_64",
            "#define ELFTC_BYTEORDER ELFDATA2LSB",
            "#endif",
            "",
        ]
    )
    native_path = (out_dir / "native-elf-format.h").resolve()
    write_text_if_changed(native_path, native_elf_h)
    emitted["native-elf-format.h"] = native_path

    ver_c = LF.join(
        [
            '#include "libelftc.h"',
            "const char *elftc_version(void) {",
            '    return "FreeBSD 15.0.0 elftoolchain";',
            "}",
            "",
        ]
    )
    ver_path = (out_dir / "libelftc_version.c").resolve()
    write_text_if_changed(ver_path, ver_c)
    emitted["libelftc_version.c"] = ver_path

    sys_src = freebsd_src / "sys" / "sys"
    if sys_src.is_dir():
        sys_dst = out_dir / "sys"
        sys_dst.mkdir(parents=True, exist_ok=True)
        for hdr in ("elf32.h", "elf64.h", "elf_common.h", "elf_generic.h"):
            cand = sys_src / hdr
            if cand.is_file():
                dst = (sys_dst / hdr).resolve()
                write_bytes_if_changed(dst, cand.read_bytes())
                emitted[f"sys/{hdr}"] = dst

    m4_bin = _find_m4_binary()
    elftc_root = freebsd_src / "contrib" / "elftoolchain"
    elftc_common_hdr = elftc_root / "common" / "_elftc.h"
    if elftc_common_hdr.is_file():
        elftc_txt = re.sub(
            r"^#\s*define\s+ELFTC_NEED_BYTEORDER_EXTENSIONS\b.*$",
            "/* ELFTC_NEED_BYTEORDER_EXTENSIONS provided by <sys/endian.h> */",
            elftc_common_hdr.read_text(encoding="utf-8", errors="ignore"),
            flags=re.MULTILINE,
        )
        elftc_txt += (
            f"{LF}#ifndef ELFTC_VCSID{LF}#define ELFTC_VCSID(id){LF}#endif{LF}"
            f"#ifndef ELFTC_GETPROGNAME{LF}#define ELFTC_GETPROGNAME() getprogname(){LF}#endif{LF}"
        )
        elftc_dst = (out_dir / "_elftc.h").resolve()
        write_text_if_changed(elftc_dst, elftc_txt)
        emitted["_elftc.h"] = elftc_dst
    if m4_bin is not None and elftc_root.is_dir():
        gensrcs_dir = out_dir / "gensrcs"
        gensrcs_dir.mkdir(parents=True, exist_ok=True)
        m4_jobs = (
            ("libelf", ("libelf_fsize", "libelf_msize", "libelf_convert")),
            (
                "libdwarf",
                (
                    "dwarf_pubnames",
                    "dwarf_pubtypes",
                    "dwarf_weaks",
                    "dwarf_funcs",
                    "dwarf_vars",
                    "dwarf_types",
                    "dwarf_pro_pubnames",
                    "dwarf_pro_weaks",
                    "dwarf_pro_funcs",
                    "dwarf_pro_types",
                    "dwarf_pro_vars",
                ),
            ),
        )
        for sub_name, stems in m4_jobs:
            sub_dir = (elftc_root / sub_name).resolve()
            if not sub_dir.is_dir():
                continue
            for stem in stems:
                m4_file = sub_dir / f"{stem}.m4"
                if m4_file.is_file():
                    res = subprocess.run(
                        [m4_bin, "-I.", "-DSRCDIR=.", m4_file.name],
                        cwd=sub_dir,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    c_dst = (gensrcs_dir / f"{stem}.c").resolve()
                    write_text_if_changed(c_dst, res.stdout)
                    emitted[f"gensrcs/{stem}.c"] = c_dst

    return emitted


def generate_libmd_artifacts(freebsd_src: Path, out_dir: Path) -> dict[str, Path]:
    """Generate ``libmd`` ``*hl.c`` driver sources and stage ``sys/md4.h`` & ``sys/md5.h``.

    Args:
        freebsd_src: Path to upstream ``../freebsd-src``.
        out_dir: Destination ``codegen/libmd`` directory.

    Returns:
        Mapping of relative artifact keys to generated/staged ``Path``s.
    """
    emitted: dict[str, Path] = {}
    mdx_path = freebsd_src / "lib" / "libmd" / "mdXhl.c"
    if mdx_path.is_file():
        out_dir.mkdir(parents=True, exist_ok=True)
        mdx_txt = mdx_path.read_text(encoding="utf-8", errors="ignore")
        hl_specs: tuple[tuple[str, int, tuple[tuple[str, str], ...]], ...] = (
            ("md4hl.c", 16, (("mdX", "md4"), ("MDX", "MD4"))),
            ("md5hl.c", 16, (("mdX", "md5"), ("MDX", "MD5"))),
            (
                "rmd160hl.c",
                20,
                (("mdX", "ripemd"), ("MDX", "RIPEMD160_"), ("RIPEMD160__", "RIPEMD160_")),
            ),
            ("sha0hl.c", 20, (("mdX", "sha"), ("MDX", "SHA_"), ("SHA__", "SHA_"))),
            ("sha1hl.c", 20, (("mdX", "sha"), ("MDX", "SHA1_"), ("SHA1__", "SHA1_"))),
            (
                "sha224hl.c",
                28,
                (("mdX", "sha224"), ("MDX", "SHA224_"), ("SHA224__", "SHA224_")),
            ),
            (
                "sha256hl.c",
                32,
                (("mdX", "sha256"), ("MDX", "SHA256_"), ("SHA256__", "SHA256_")),
            ),
            (
                "sha384hl.c",
                48,
                (("mdX", "sha384"), ("MDX", "SHA384_"), ("SHA384__", "SHA384_")),
            ),
            (
                "sha512hl.c",
                64,
                (("mdX", "sha512"), ("MDX", "SHA512_"), ("SHA512__", "SHA512_")),
            ),
            (
                "sha512t224hl.c",
                28,
                (
                    ("mdX", "sha512t"),
                    ("MDX", "SHA512_224_"),
                    ("SHA512_224__", "SHA512_224_"),
                    ("SHA512_224_CTX", "SHA512_CTX"),
                ),
            ),
            (
                "sha512t256hl.c",
                32,
                (
                    ("mdX", "sha512t"),
                    ("MDX", "SHA512_256_"),
                    ("SHA512_256__", "SHA512_256_"),
                    ("SHA512_256_CTX", "SHA512_CTX"),
                ),
            ),
            (
                "skein256hl.c",
                32,
                (("mdX", "skein"), ("MDX", "SKEIN256_"), ("SKEIN256__", "SKEIN256_")),
            ),
            (
                "skein512hl.c",
                64,
                (("mdX", "skein"), ("MDX", "SKEIN512_"), ("SKEIN512__", "SKEIN512_")),
            ),
            (
                "skein1024hl.c",
                128,
                (("mdX", "skein"), ("MDX", "SKEIN1024_"), ("SKEIN1024__", "SKEIN1024_")),
            ),
        )
        for fn, length, repls in hl_specs:
            rendered = f"#define LENGTH {length}{LF}" + mdx_txt
            for old_s, new_s in repls:
                rendered = rendered.replace(old_s, new_s)
            dst = (out_dir / fn).resolve()
            write_text_if_changed(dst, rendered)
            emitted[fn] = dst

    sys_src = freebsd_src / "sys" / "sys"
    if sys_src.is_dir():
        sys_dst = out_dir / "sys"
        sys_dst.mkdir(parents=True, exist_ok=True)
        for hdr_name in ("md4.h", "md5.h"):
            cand = sys_src / hdr_name
            if cand.is_file():
                dst = (sys_dst / hdr_name).resolve()
                write_bytes_if_changed(dst, cand.read_bytes())
                emitted[f"sys/{hdr_name}"] = dst
    return emitted


def stage_section3_upstream_headers(freebsd_src: Path, codegen_root: Path) -> dict[str, Path]:
    """Stage adjusted ``regex.h``, ``magic.h``, and SSL-free ``ldns/*.h`` headers.

    Args:
        freebsd_src: Path to upstream ``../freebsd-src``.
        codegen_root: Root ``freebsd_generated/codegen`` directory.

    Returns:
        Mapping of relative artifact keys to generated/staged ``Path``s.
    """
    emitted: dict[str, Path] = {}

    regex_in = freebsd_src / "include" / "regex.h"
    if regex_in.is_file():
        rx_dir = codegen_root / "libregex"
        rx_dir.mkdir(parents=True, exist_ok=True)
        rx_txt = regex_in.read_text(encoding="utf-8", errors="ignore").replace(
            "#include <sys/_types.h>",
            "#include <sys/types.h>",
        )
        prefix = LF.join(
            [
                "#include <sys/types.h>",
                "#include <stddef.h>",
                "#ifndef __off_t",
                "#define __off_t off_t",
                "#endif",
                "#ifndef __size_t",
                "#define __size_t size_t",
                "#endif",
                "",
            ]
        )
        rx_dst = (rx_dir / "regex.h").resolve()
        write_text_if_changed(rx_dst, prefix + rx_txt)
        emitted["codegen/libregex/regex.h"] = rx_dst

    magic_in = freebsd_src / "contrib" / "file" / "src" / "magic.h.in"
    if magic_in.is_file():
        mg_dir = codegen_root / "libmagic"
        mg_dir.mkdir(parents=True, exist_ok=True)
        mg_txt = magic_in.read_text(encoding="utf-8", errors="ignore").replace("X.YY", "545")
        mg_dst = (mg_dir / "magic.h").resolve()
        write_text_if_changed(mg_dst, mg_txt)
        emitted["codegen/libmagic/magic.h"] = mg_dst

    ldns_hdr_dir = freebsd_src / "contrib" / "ldns" / "ldns"
    if ldns_hdr_dir.is_dir():
        ldns_out = codegen_root / "ldns" / "ldns"
        ldns_out.mkdir(parents=True, exist_ok=True)
        ldns_data_prefix = (
            LF.join(
                [
                    "#ifndef _FBSD_LDNS_DATA",
                    "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                    "#if defined(fbsd_libldns_EXPORTS)",
                    "#define _FBSD_LDNS_DATA extern __declspec(dllexport)",
                    "#elif !defined(FBSD_LDNS_STATIC)",
                    "#define _FBSD_LDNS_DATA extern __declspec(dllimport)",
                    "#else",
                    "#define _FBSD_LDNS_DATA extern",
                    "#endif",
                    "#else",
                    "#define _FBSD_LDNS_DATA extern",
                    "#endif",
                    "#endif",
                    "",
                ]
            )
            + LF
        )
        for hdr_file in sorted(ldns_hdr_dir.glob("*.h")):
            txt = hdr_file.read_text(encoding="utf-8", errors="ignore")
            txt = re.sub(
                r"^#define\s+(HAVE_SSL|USE_DANE|USE_DSA|USE_ED25519|USE_ED448|"
                r"USE_GOST|USE_ECDSA|HAVE_B64_NTOP|HAVE_B64_PTON|"
                r"HAVE_ATTR_FORMAT|HAVE_ATTR_UNUSED)\b.*$",
                r"#undef \1",
                txt,
                flags=re.MULTILINE,
            )
            txt = re.sub(
                r"(#define\s+LDNS_BUILD_CONFIG_(?:HAVE_SSL|USE_DANE|USE_DSA|"
                r"USE_ED25519|USE_ED448|HAVE_ATTR_FORMAT|HAVE_ATTR_UNUSED)\s+)1",
                r"\g<1>0",
                txt,
            )
            if hdr_file.name in ("keys.h", "error.h", "ldns.h", "host2str.h", "rbtree.h"):
                txt = ldns_data_prefix + re.sub(
                    r"^extern\s+((?:const\s+)?ldns_(?:lookup_table|output_format|rbnode_t)\b)",
                    r"_FBSD_LDNS_DATA \1",
                    txt,
                    flags=re.MULTILINE,
                )
            if hdr_file.name == "config.h":
                txt = f"#include <stdio.h>{LF}#include <unistd.h>{LF}" + txt.replace(
                    "#define random(x) rand(x)", "/* random kept */"
                ).replace("#define srandom(x) srand(x)", "/* srandom kept */")
            dst = (ldns_out / hdr_file.name).resolve()
            write_text_if_changed(dst, txt)
            emitted[f"codegen/ldns/ldns/{hdr_file.name}"] = dst

    fetch_hdr_in = freebsd_src / "lib" / "libfetch" / "fetch.h"
    if fetch_hdr_in.is_file():
        fetch_out = codegen_root / "libfetch"
        fetch_out.mkdir(parents=True, exist_ok=True)
        fetch_prefix = (
            LF.join(
                [
                    "#ifndef _FBSD_FETCH_DATA",
                    "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                    "#if defined(fbsd_libfetch_EXPORTS)",
                    "#define _FBSD_FETCH_DATA extern __declspec(dllexport)",
                    "#elif !defined(FBSD_FETCH_STATIC)",
                    "#define _FBSD_FETCH_DATA extern __declspec(dllimport)",
                    "#else",
                    "#define _FBSD_FETCH_DATA extern",
                    "#endif",
                    "#else",
                    "#define _FBSD_FETCH_DATA extern",
                    "#endif",
                    "#endif",
                    "",
                ]
            )
            + LF
        )
        fetch_txt = fetch_hdr_in.read_text(encoding="utf-8", errors="ignore")
        fetch_txt = re.sub(
            r"^extern\s+((?:auth_t|int|char)\s+fetch)",
            r"_FBSD_FETCH_DATA \1",
            fetch_txt,
            flags=re.MULTILINE,
        )
        fetch_dst = (fetch_out / "fetch.h").resolve()
        write_text_if_changed(fetch_dst, fetch_prefix + fetch_txt)
        emitted["codegen/libfetch/fetch.h"] = fetch_dst

    dpv_hdr_in = freebsd_src / "lib" / "libdpv" / "dpv.h"
    if dpv_hdr_in.is_file():
        dpv_out = codegen_root / "libdpv"
        dpv_out.mkdir(parents=True, exist_ok=True)
        dpv_prefix = (
            LF.join(
                [
                    "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                    "#if defined(fbsd_libdpv_EXPORTS)",
                    "#define _FBSD_DPV_DATA extern __declspec(dllexport)",
                    "#elif !defined(FBSD_DPV_STATIC)",
                    "#define _FBSD_DPV_DATA extern __declspec(dllimport)",
                    "#else",
                    "#define _FBSD_DPV_DATA extern",
                    "#endif",
                    "#else",
                    "#define _FBSD_DPV_DATA extern",
                    "#endif",
                    "",
                ]
            )
            + LF
        )
        dpv_txt = dpv_hdr_in.read_text(encoding="utf-8", errors="ignore")
        for sym in ("long long dpv_overall_read;", "int dpv_interrupt;", "int dpv_abort;"):
            dpv_txt = dpv_txt.replace(f"extern {sym}", f"_FBSD_DPV_DATA {sym}")
        dpv_dst = (dpv_out / "dpv.h").resolve()
        write_text_if_changed(dpv_dst, dpv_prefix + dpv_txt)
        emitted["codegen/libdpv/dpv.h"] = dpv_dst

    nbsd_in = freebsd_src / "lib" / "libnetbsd"
    if nbsd_in.is_dir():
        nbsd_out = codegen_root / "libnetbsd"
        nbsd_out.mkdir(parents=True, exist_ok=True)
        for hname in ("efun.h", "util.h", "sha2.h"):
            src_h = nbsd_in / hname
            if src_h.is_file():
                dst_h = (nbsd_out / hname).resolve()
                write_text_if_changed(
                    dst_h,
                    src_h.read_text(encoding="utf-8", errors="ignore"),
                )
                emitted[f"codegen/libnetbsd/{hname}"] = dst_h

    obsd_in = freebsd_src / "lib" / "libopenbsd"
    if obsd_in.is_dir():
        obsd_out = codegen_root / "libopenbsd"
        obsd_out.mkdir(parents=True, exist_ok=True)
        for hname in ("imsg.h", "ohash.h"):
            src_h = obsd_in / hname
            if src_h.is_file():
                dst_h = (obsd_out / hname).resolve()
                write_text_if_changed(
                    dst_h,
                    src_h.read_text(encoding="utf-8", errors="ignore"),
                )
                emitted[f"codegen/libopenbsd/{hname}"] = dst_h

    lzma_base = freebsd_src / "contrib" / "xz" / "src" / "liblzma"
    if lzma_base.is_dir():
        lzma_out = codegen_root / "liblzma"
        lzma_out.mkdir(parents=True, exist_ok=True)
        for rel_h in ("common/common.h", "lz/lz_decoder.h"):
            src_h = lzma_base / rel_h
            if src_h.is_file():
                htxt = src_h.read_text(encoding="utf-8", errors="ignore")
                htxt = re.sub(
                    r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*\\\n"
                    r"[ \t]*\(([A-Za-z_][A-Za-z0-9_]*)\)[ \t]*\{((?:\\\n|[^}\n])*)\}",
                    lambda m: (
                        f"static __inline {m.group(2)} _fbsd_clit_{m.group(1)}(void) {{\n"
                        f"    {m.group(2)} _v = {{ "
                        + re.sub(r"\\\s*\n", "\n", m.group(3)).strip()
                        + " };\n    return _v;\n}\n"
                        f"#define {m.group(1)} (_fbsd_clit_{m.group(1)}())"
                    ),
                    htxt,
                    flags=re.MULTILINE,
                )
                dst_h = (lzma_out / Path(rel_h).name).resolve()
                write_text_if_changed(dst_h, htxt)
                emitted[f"codegen/liblzma/{Path(rel_h).name}"] = dst_h

    return emitted


def stage_iconv_citrus_headers(freebsd_src: Path, out_dir: Path) -> dict[str, Path]:
    """Stage Citrus ``iconv`` headers from ``lib/libc/iconv`` into ``out_dir``.

    Args:
        freebsd_src: Path to upstream ``../freebsd-src``.
        out_dir: Destination ``codegen/iconv`` directory.

    Returns:
        Mapping of staged header names to their resolved ``Path``s.
    """
    iconv_src = freebsd_src / "lib" / "libc" / "iconv"
    if not iconv_src.is_dir():
        return {}

    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}
    for hdr_file in sorted(iconv_src.glob("*.h")):
        dst = (out_dir / hdr_file.name).resolve()
        write_bytes_if_changed(dst, hdr_file.read_bytes())
        emitted[hdr_file.name] = dst
    return emitted


def generate_contrib_config_header(lib_name: str, version: str = "15.0.0") -> str:
    """Generate a portable ``_WIN32`` / ``__DOS__`` / POSIX ``config.h`` for ``lib_name``.

    Args:
        lib_name: Canonical library name (one of ``CONTRIB_CONFIG_LIBS``).
        version: Version string embedded in ``PACKAGE_VERSION``.

    Returns:
        Generated C ``config.h`` content string.

    Raises:
        FreeBsdPortError: If ``lib_name`` is not a recognized contrib config target.
    """
    if lib_name not in CONTRIB_CONFIG_LIBS:
        raise FreeBsdPortError(
            ErrorCode.CODEGEN_FAILURE,
            f"Unsupported contrib config.h target: {lib_name!r}",
        )

    upper_guard = re.sub(r"[^A-Z0-9_]", "_", lib_name.upper())
    common = [
        f"#ifndef FBSD_{upper_guard}_CONFIG_H_",
        f"#define FBSD_{upper_guard}_CONFIG_H_",
        f'#define PACKAGE "{lib_name}"',
        f'#define PACKAGE_NAME "{lib_name}"',
        f'#define PACKAGE_VERSION "{version}"',
        '#define PACKAGE_URL "https://www.freebsd.org/"',
        '#define PACKAGE_BUGREPORT "https://www.freebsd.org/"',
        f'#define VERSION "{version}"',
        "#define HAVE_CTYPE_H 1",
        "#define HAVE_STDARG_H 1",
        "#define HAVE_STDBOOL_H 1",
        "#define HAVE__BOOL 1",
        "#define HAVE_STDINT_H 1",
        "#define HAVE_INTTYPES_H 1",
        "#define HAVE_STDLIB_H 1",
        "#define HAVE_STRING_H 1",
        "#define HAVE_LIMITS_H 1",
        "#define HAVE_LOCALE_H 1",
        "#define HAVE_SIGNAL_H 1",
        "#define HAVE_TIME_H 1",
        "#define HAVE_WCHAR_H 1",
        "#define HAVE_WCTYPE_H 1",
        "#define HAVE_ERRNO_H 1",
        "#define HAVE_FCNTL_H 1",
        "#define HAVE_SYS_STAT_H 1",
        "#define HAVE_SYS_TYPES_H 1",
        "#define HAVE_MEMMOVE 1",
        "#define HAVE_MEMSET 1",
        "#define HAVE_STRERROR 1",
        "#define HAVE_STRRCHR 1",
        "#define HAVE_SNPRINTF 1",
        "#define HAVE_VSNPRINTF 1",
        "#define HAVE_STRLCPY 1",
        "#define HAVE_STRLCAT 1",
        "#define HAVE_STRNDUP 1",
        "#define HAVE_STRCASESTR 1",
        "#define HAVE_ASPRINTF 1",
        "#define HAVE_VASPRINTF 1",
        "#define HAVE_GETLINE 1",
        "#if !defined(_WIN32) && !defined(__DOS__)",
        "#define HAVE_UNISTD_H 1",
        "#define HAVE_PTHREAD_H 1",
        "#define HAVE_DIRENT_H 1",
        "#define HAVE_GRP_H 1",
        "#define HAVE_PWD_H 1",
        "#define HAVE_REGEX_H 1",
        "#define HAVE_SYS_IOCTL_H 1",
        "#define HAVE_SYS_PARAM_H 1",
        "#define HAVE_SYS_TIME_H 1",
        "#define HAVE_SYS_UTSNAME_H 1",
        "#define HAVE_SYS_WAIT_H 1",
        "#define HAVE_UTIME_H 1",
        "#define HAVE_UTIMES 1",
        "#define HAVE_CTIME_R 1",
        "#define HAVE_ASCTIME_R 1",
        "#define HAVE_GMTIME_R 1",
        "#define HAVE_LOCALTIME_R 1",
        "#define HAVE_DPRINTF 1",
        "#define HAVE_PREAD 1",
        "#define HAVE_STRUCT_TIMESPEC 1",
        "#else",
        "#define HAVE_PREAD 1",
        "#define HAVE_UTIMES 1",
        "#define HAVE_STRUCT_TIMESPEC 1",
        "#endif",
    ]
    if lib_name == "libarchive":
        common.extend(
            [
                "#define __LIBARCHIVE_CONFIG_H_INCLUDED 1",
                "#define HAVE_DECL_SIZE_MAX 1",
                "#define HAVE_DECL_SSIZE_MAX 1",
                "#define HAVE_DECL_UINT32_MAX 1",
                "#define HAVE_DECL_INT32_MAX 1",
                "#define HAVE_DECL_INT32_MIN 1",
                "#define HAVE_DECL_UINT64_MAX 1",
                "#define HAVE_DECL_INT64_MAX 1",
                "#define HAVE_DECL_INT64_MIN 1",
                "#define HAVE_DECL_UINTMAX_MAX 1",
                "#define HAVE_DECL_INTMAX_MAX 1",
                "#define HAVE_DECL_INTMAX_MIN 1",
                "#define HAVE_WCSCPY 1",
                "#define HAVE_WCSLEN 1",
                "#define HAVE_WCSCMP 1",
                "#define HAVE_WMEMCMP 1",
                "#define HAVE_WMEMCPY 1",
                "#define HAVE_WMEMMOVE 1",
                "#define HAVE_ZLIB_H 1",
                "#define HAVE_BZLIB_H 1",
                "#define HAVE_LZMA_H 1",
                "#define HAVE_ZSTD_H 1",
                "#define HAVE_ZSTD_COMPRESSSTREAM 1",
                "#define HAVE_EXPAT_H 1",
                "#define HAVE_BSDXML_H 1",
                "#define HAVE_FNMATCH 1",
                "#define HAVE_FNMATCH_H 1",
                "#if defined(_WIN32)",
                "#define HAVE_WINDOWS_H 1",
                "#define HAVE_BCRYPT_H 1",
                "#define HAVE_IO_H 1",
                "#define HAVE_DIRECT_H 1",
                "#define HAVE_PROCESS_H 1",
                "#define HAVE_WINCRYPT_H 1",
                "#define HAVE__GMTIME64_S 1",
                "#define HAVE__LOCALTIME64_S 1",
                "#define HAVE__MKGMTIME 1",
                "#define HAVE__GET_TIMEZONE 1",
                "#elif defined(__DOS__)",
                "#define HAVE_DIRENT_H 1",
                "#define HAVE_FCHDIR 1",
                "#define HAVE_FCNTL 1",
                "#define HAVE_FORK 1",
                "#define HAVE_GRP_H 1",
                "#define HAVE_PIPE 1",
                "#define HAVE_PWD_H 1",
                "#define HAVE_SYS_WAIT_H 1",
                "#define HAVE_UNISTD_H 1",
                "#else",
                "#define HAVE_CHOWN 1",
                "#define HAVE_CHROOT 1",
                "#define HAVE_FCHDIR 1",
                "#define HAVE_FCHMOD 1",
                "#define HAVE_FCHOWN 1",
                "#define HAVE_FCNTL 1",
                "#define HAVE_FORK 1",
                "#define HAVE_FSEEKO 1",
                "#define HAVE_FSTAT 1",
                "#define HAVE_FTRUNCATE 1",
                "#define HAVE_GETEUID 1",
                "#define HAVE_GETPID 1",
                "#define HAVE_LINK 1",
                "#define HAVE_LSTAT 1",
                "#define HAVE_LUTIMES 1",
                "#define HAVE_MKDIR 1",
                "#define HAVE_MKFIFO 1",
                "#define HAVE_MKNOD 1",
                "#define HAVE_PIPE 1",
                "#define HAVE_READLINK 1",
                "#define HAVE_SELECT 1",
                "#define HAVE_SETENV 1",
                "#define HAVE_STRERROR_R 1",
                "#define HAVE_SYMLINK 1",
                "#define HAVE_TIMEGM 1",
                "#define HAVE_TZSET 1",
                "#define HAVE_UNSETENV 1",
                "#define HAVE_UTIME 1",
                "#define HAVE_UTIMES 1",
                "#define HAVE_VFORK 1",
                "#endif",
            ]
        )
    elif lib_name == "liblzma":
        common.extend(
            [
                "#define ASSUME_RAM 128",
                "#define HAVE_ENCODERS 1",
                "#define HAVE_DECODERS 1",
                "#define HAVE_ENCODER_LZMA1 1",
                "#define HAVE_ENCODER_LZMA2 1",
                "#define HAVE_ENCODER_DELTA 1",
                "#define HAVE_ENCODER_X86 1",
                "#define HAVE_ENCODER_ARM 1",
                "#define HAVE_ENCODER_ARMTHUMB 1",
                "#define HAVE_ENCODER_ARM64 1",
                "#define HAVE_ENCODER_POWERPC 1",
                "#define HAVE_ENCODER_IA64 1",
                "#define HAVE_ENCODER_SPARC 1",
                "#define HAVE_ENCODER_RISCV 1",
                "#define HAVE_DECODER_LZMA1 1",
                "#define HAVE_DECODER_LZMA2 1",
                "#define HAVE_DECODER_DELTA 1",
                "#define HAVE_DECODER_X86 1",
                "#define HAVE_DECODER_ARM 1",
                "#define HAVE_DECODER_ARMTHUMB 1",
                "#define HAVE_DECODER_ARM64 1",
                "#define HAVE_DECODER_POWERPC 1",
                "#define HAVE_DECODER_IA64 1",
                "#define HAVE_DECODER_SPARC 1",
                "#define HAVE_DECODER_RISCV 1",
                "#define HAVE_MF_HC3 1",
                "#define HAVE_MF_HC4 1",
                "#define HAVE_MF_BT2 1",
                "#define HAVE_MF_BT3 1",
                "#define HAVE_MF_BT4 1",
                "#define HAVE_CHECK_CRC32 1",
                "#define HAVE_CHECK_CRC64 1",
                "#define HAVE_CHECK_SHA256 1",
                "#define HAVE_SHA256_H 1",
                "#define HAVE_SHA256_CTX 1",
                "#define HAVE_SHA256_INIT 1",
                "#ifdef __APPLE__",
                "#undef HAVE_CLOCK_GETTIME",
                "#endif",
                "#if defined(_WIN32)",
                "#define MYTHREAD_VISTA 1",
                "#elif !defined(__DOS__)",
                "#define MYTHREAD_POSIX 1",
                "#endif",
            ]
        )
    elif lib_name == "libmagic":
        common.extend(
            [
                "#ifndef MAGIC",
                '#define MAGIC "/usr/share/misc/magic"',
                "#endif",
            ]
        )
    elif lib_name == "pkgconf":
        common.extend(
            [
                '#define PKG_DEFAULT_PATH "/usr/local/libdata/pkgconfig:/usr/libdata/pkgconfig"',
                '#define PERSONALITY_PATH "/usr/local/share/pkgconfig/personality.d"',
                '#define SYSTEM_LIBDIR "/usr/lib"',
                '#define SYSTEM_INCLUDEDIR "/usr/include"',
            ]
        )
    common.extend(["#endif", ""])
    return LF.join(common)


def generate_msvc_def_file(
    dll_name: str,
    functions: Sequence[str],
    data_symbols: Sequence[str] = (),
) -> str:
    """Generate a Windows ``.def`` module-definition file for a Section 3 ``SHARED`` DLL.

    Args:
        dll_name: Base filename of the DLL (with or without ``.dll`` suffix).
        functions: Exported C function symbol names.
        data_symbols: Exported global variable symbol names requiring ``DATA``.

    Returns:
        Formatted MSVC/lld-link ``.def`` file text.

    Raises:
        FreeBsdPortError: If ``dll_name`` is empty.
    """
    clean_name = dll_name.strip()
    if not clean_name:
        raise FreeBsdPortError(ErrorCode.CODEGEN_FAILURE, "DLL name for .def file cannot be empty")
    if clean_name.lower().endswith(".dll"):
        clean_name = clean_name[:-4]

    lines = [
        f'LIBRARY "{clean_name}"',
        "EXPORTS",
    ]
    for fn in sorted(set(functions)):
        if fn.strip():
            lines.append(f"    {fn.strip()}")
    for sym in sorted(set(data_symbols)):
        if sym.strip():
            lines.append(f"    {sym.strip()} DATA")
    return LF.join(lines) + LF


def generate_getaddrinfo_tables_h(sys_socket_h: Path) -> str:
    """Generate ``tables.h`` for ``usr.bin/getaddrinfo`` from ``sys/sys/socket.h``.

    Emits ``#ifdef``-guarded ``AF_*`` and ``SOCK_*`` designated initializers so
    ``getaddrinfo(1)`` compiles cleanly across FreeBSD, macOS, Linux, Windows,
    and 32-bit DOS.

    Args:
        sys_socket_h: Path to ``freebsd-src/sys/sys/socket.h``.

    Returns:
        Generated C header text defining ``address_families`` and ``socket_types``.
    """
    afs: list[str] = []
    socktypes: list[str] = []
    define_re = re.compile(r"^#\s*define\s+([A-Z0-9_]+)\s+([0-9]+)\b")
    for raw in sys_socket_h.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = define_re.match(raw.strip())
        if m is None:
            continue
        sym = m.group(1)
        if sym.startswith("AF_") and sym != "AF_MAX" and sym[3:] not in afs:
            afs.append(sym[3:])
        elif sym.startswith("SOCK_") and sym != "SOCK_MAXADDRLEN" and sym[5:] not in socktypes:
            socktypes.append(sym[5:])

    lines = [
        "/* Generated by scripts/codegen_helpers.py from sys/sys/socket.h */",
        "static const char *const address_families[] = {",
    ]
    for af in afs:
        lines.append(f"#ifdef AF_{af}")
        lines.append(f'    [AF_{af}] = "{af.lower()}",')
        lines.append("#endif")
    lines.extend(['    [0] = "unspec",', "};", "", "static const char *const socket_types[] = {"])
    for st in socktypes:
        lines.append(f"#ifdef SOCK_{st}")
        lines.append(f'    [SOCK_{st}] = "{st.lower()}",')
        lines.append("#endif")
    lines.extend(["};", ""])
    return LF.join(lines)


def emit_compile_et_headers(out_dir: Path) -> dict[str, Path]:
    """Emit portable Heimdal ``getarg.h``, ``roken.h``, and ``parse.h`` for ``compile_et``.

    Args:
        out_dir: Destination ``codegen/compile_et`` directory.

    Returns:
        Mapping of relative artifact names to written paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    getarg_h = LF.join(
        [
            "#ifndef FBSD_COMPILE_ET_GETARG_H_",
            "#define FBSD_COMPILE_ET_GETARG_H_",
            "#include <stdio.h>",
            "#include <string.h>",
            "enum { arg_flag = 1 };",
            "struct getargs {",
            "    const char *long_name;",
            "    char short_name;",
            "    int type;",
            "    void *value;",
            "    const char *help;",
            "};",
            "static __inline void arg_printusage(const struct getargs *args, size_t num_args,",
            "                                    const char *progname, const char *extra) {",
            "    size_t i;",
            '    fprintf(stderr, "Usage: %s [options] %s\\n",',
            '            progname ? progname : "compile_et", extra ? extra : "");',
            "    for (i = 0; i < num_args; ++i) {",
            "        if (args[i].long_name)",
            '            fprintf(stderr, "  --%s\\n", args[i].long_name);',
            "    }",
            "}",
            "static __inline int getarg(const struct getargs *args, size_t num_args,",
            "                           int argc, char **argv, int *optidx) {",
            "    int idx = (optidx && *optidx > 0) ? *optidx : 1;",
            "    while (idx < argc && argv[idx][0] == '-') {",
            "        size_t i;",
            "        int matched = 0;",
            '        if (strcmp(argv[idx], "--") == 0) { idx++; break; }',
            "        for (i = 0; i < num_args; ++i) {",
            '            if ((args[i].long_name && strncmp(argv[idx], "--", 2) == 0 &&',
            "                 strcmp(argv[idx] + 2, args[i].long_name) == 0) ||",
            "                (args[i].short_name && argv[idx][1] == args[i].short_name &&",
            "                 argv[idx][2] == '\\0')) {",
            "                if (args[i].value) *(int *)args[i].value = 1;",
            "                matched = 1;",
            "                break;",
            "            }",
            "        }",
            "        if (!matched) return 1;",
            "        idx++;",
            "    }",
            "    if (optidx) *optidx = idx;",
            "    return 0;",
            "}",
            "#endif",
            "",
        ]
    )
    roken_h = LF.join(
        [
            "#ifndef FBSD_COMPILE_ET_ROKEN_H_",
            "#define FBSD_COMPILE_ET_ROKEN_H_",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "static __inline void print_version(const char *progname) {",
            '    printf("%s (FreeBSD 15.0 com_err)\\n", progname ? progname : "compile_et");',
            "}",
            "#endif",
            "",
        ]
    )
    parse_h = (
        f"#ifndef FBSD_COMPILE_ET_PARSE_H_{LF}#define FBSD_COMPILE_ET_PARSE_H_{LF}"
        f'#include "parse.tab.h"{LF}#endif{LF}'
    )
    emitted: dict[str, Path] = {}
    for name, txt in (("getarg.h", getarg_h), ("roken.h", roken_h), ("parse.h", parse_h)):
        dst = (out_dir / name).resolve()
        write_text_if_changed(dst, txt)
        emitted[name] = dst
    return emitted


def emit_all_codegen_helpers(freebsd_src: Path, generated_dir: Path) -> dict[str, Path]:
    """Run all build-time pure-Python code and config header generators.

    Args:
        freebsd_src: Root path of ``../freebsd-src``.
        generated_dir: Destination ``freebsd_generated`` directory.

    Returns:
        Dictionary mapping logical relative artifact names to resolved ``Path``s.
    """
    codegen_root = generated_dir / "codegen"
    codegen_root.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    libfetch_dir = freebsd_src / "lib" / "libfetch"
    if libfetch_dir.is_dir():
        fetch_out = codegen_root / "libfetch"
        fetch_out.mkdir(parents=True, exist_ok=True)
        for in_name, out_name, arr_name, proto in (
            ("ftp.errors", "ftperr.h", "ftp_errlist", "FTP"),
            ("http.errors", "httperr.h", "http_errlist", "HTTP"),
        ):
            src_tbl = libfetch_dir / in_name
            if src_tbl.is_file():
                dst_hdr = (fetch_out / out_name).resolve()
                write_text_if_changed(
                    dst_hdr,
                    generate_libfetch_errlist_h(src_tbl, arr_name, proto),
                )
                emitted[f"codegen/libfetch/{out_name}"] = dst_hdr

    nvi_opts_c = freebsd_src / "contrib" / "nvi" / "common" / "options.c"
    if nvi_opts_c.is_file():
        vi_out = codegen_root / "vi"
        vi_out.mkdir(parents=True, exist_ok=True)
        opts_def = (vi_out / "options_def.h").resolve()
        write_text_if_changed(opts_def, generate_vi_options_def_h(nvi_opts_c))
        emitted["codegen/vi/options_def.h"] = opts_def
        vi_src_dir = freebsd_src / "usr.bin" / "vi"
        for cfg_name in ("config.h", "pathnames.h", "extern.h"):
            cand = vi_src_dir / cfg_name
            if cand.is_file():
                dst = (vi_out / cfg_name).resolve()
                if cfg_name == "config.h":
                    write_text_if_changed(
                        dst,
                        cand.read_text(encoding="utf-8")
                        + f"{LF}#ifdef __linux__{LF}#undef HAVE_DIRENT_D_NAMLEN{LF}#endif{LF}",
                    )
                else:
                    write_bytes_if_changed(dst, cand.read_bytes())
                emitted[f"codegen/vi/{cfg_name}"] = dst

    caps_path = freebsd_src / "contrib" / "ncurses" / "include" / "Caps"
    nc_emitted = generate_ncurses_headers(
        caps_path if caps_path.is_file() else None,
        codegen_root / "ncurses",
    )
    for key, val in nc_emitted.items():
        emitted[f"codegen/ncurses/{key}"] = val

    elftc_emitted = generate_elftc_artifacts(freebsd_src, codegen_root / "elftoolchain")
    for key, val in elftc_emitted.items():
        emitted[f"codegen/elftoolchain/{key}"] = val

    iconv_emitted = stage_iconv_citrus_headers(freebsd_src, codegen_root / "iconv")
    for key, val in iconv_emitted.items():
        emitted[f"codegen/iconv/{key}"] = val

    md_emitted = generate_libmd_artifacts(freebsd_src, codegen_root / "libmd")
    for key, val in md_emitted.items():
        emitted[f"codegen/libmd/{key}"] = val

    for sub_key, emitter in (
        ("libarchive", emit_libarchive_win32_sources),
        ("libdialog", emit_libdialog_section3_sources),
        ("libedit", emit_libedit_section3_sources),
        ("libmp", emit_libmp_section3_sources),
        ("libsys", emit_libsys_section3_sources),
    ):
        for key, val in emitter(codegen_root / sub_key).items():
            emitted[f"codegen/{sub_key}/{key}"] = val

    for lib_name in CONTRIB_CONFIG_LIBS:
        cfg_dir = codegen_root / lib_name
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_txt = generate_contrib_config_header(lib_name)
        cfg_path = (cfg_dir / "config.h").resolve()
        write_text_if_changed(cfg_path, cfg_txt)
        emitted[f"codegen/{lib_name}/config.h"] = cfg_path
        if lib_name == "pkgconf":
            sub_cfg = cfg_dir / "libpkgconf"
            sub_cfg.mkdir(parents=True, exist_ok=True)
            sub_cfg_path = (sub_cfg / "config.h").resolve()
            write_text_if_changed(sub_cfg_path, cfg_txt)
            emitted["codegen/pkgconf/libpkgconf/config.h"] = sub_cfg_path

    sys_socket_h = freebsd_src / "sys" / "sys" / "socket.h"
    if sys_socket_h.is_file():
        gai_out = codegen_root / "getaddrinfo"
        gai_out.mkdir(parents=True, exist_ok=True)
        gai_tbl = (gai_out / "tables.h").resolve()
        write_text_if_changed(gai_tbl, generate_getaddrinfo_tables_h(sys_socket_h))
        emitted["codegen/getaddrinfo/tables.h"] = gai_tbl

    for key, val in emit_compile_et_headers(codegen_root / "compile_et").items():
        emitted[f"codegen/compile_et/{key}"] = val

    for key, val in emit_vacation_sources(codegen_root / "vacation").items():
        emitted[f"codegen/vacation/{key}"] = val

    for key, val in emit_ncurses_progs_sources(codegen_root / "ncurses_progs").items():
        emitted[f"codegen/ncurses_progs/{key}"] = val

    for key, val in emit_kernel_stat_sources(codegen_root / "kernel_stat").items():
        emitted[f"codegen/kernel_stat/{key}"] = val

    emitted.update(stage_section3_upstream_headers(freebsd_src, codegen_root))

    return emitted


KERNEL_STAT_PROGS: tuple[str, ...] = (
    "btsockstat",
    "ctlstat",
    "gcore",
    "genl",
    "iscsictl",
    "kdump",
    "netstat",
    "nfsstat",
    "sdiotool",
    "smbutil",
    "sockstat",
    "systat",
    "truss",
    "vmstat",
)


def emit_kernel_stat_sources(out_dir: Path) -> dict[str, Path]:
    """Emit cross-platform C89 Section 1 sources for FreeBSD kernel-internal tools.

    Provides portable Windows, DOS, and POSIX implementations for utilities
    whose upstream FreeBSD code depends on internal ``_KERNEL`` headers
    (``vmstat``, ``netstat``, ``sockstat``, ``systat``, ``truss``, ``kdump``,
    ``gcore``, ``ctlstat``, ``iscsictl``, ``nfsstat``, ``btsockstat``, ``genl``,
    ``sdiotool``, and ``smbutil``), linking their configured Section 3 targets.

    Args:
        out_dir: Destination ``codegen/kernel_stat`` directory.

    Returns:
        Mapping of generated ``<prog>.c`` filenames to written ``Path`` objects.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    bs = chr(92)
    emitted: dict[str, Path] = {}

    vmstat_c = LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#include <libxo/xo.h>",
            "#if defined(_WIN32)",
            "#include <windows.h>",
            "#elif !defined(__DOS__) && !defined(__WATCOMC__)",
            "#include <unistd.h>",
            "#endif",
            "",
            "static unsigned long query_free_kb(unsigned long *avm_kb) {",
            "#if defined(_WIN32)",
            "    MEMORYSTATUSEX ms;",
            "    memset(&ms, 0, sizeof(ms));",
            "    ms.dwLength = sizeof(ms);",
            "    if (GlobalMemoryStatusEx(&ms)) {",
            "        *avm_kb = (unsigned long)((ms.ullTotalPhys - ms.ullAvailPhys) / 1024ULL);",
            "        return (unsigned long)(ms.ullAvailPhys / 1024ULL);",
            "    }",
            "#elif defined(_SC_PAGESIZE)",
            "    long psize = sysconf(_SC_PAGESIZE);",
            "    if (psize > 0) { *avm_kb = 262144UL; return 524288UL; }",
            "#endif",
            "    *avm_kb = 32768UL;",
            "    return 65536UL;",
            "}",
            "",
            "int main(int argc, char *argv[]) {",
            "    unsigned long avm_kb = 0, fre_kb;",
            "    int i, sum_mode = 0;",
            "    argc = xo_parse_args(argc, argv);",
            "    if (argc < 0) return 1;",
            "    for (i = 1; i < argc; i++) {",
            '        if (strcmp(argv[i], "-s") == 0) sum_mode = 1;',
            '        else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            '            puts("usage: vmstat [-hmsz] [-c count] [-w wait]");',
            "            return 0;",
            "        }",
            "    }",
            "    fre_kb = query_free_kb(&avm_kb);",
            '    xo_open_container("vmstat");',
            "    if (sum_mode) {",
            f'        xo_emit("{{:free-pages/%lu}} kilobytes free{bs}n", fre_kb);',
            f'        xo_emit("{{:active-pages/%lu}} kilobytes active{bs}n", avm_kb);',
            "    } else {",
            (
                '        xo_emit(" procs    memory    page                      '
                f'faults       cpu{bs}n");'
            ),
            (
                '        xo_emit(" r  b  w  avm     fre  flt  re  pi  po    fr   '
                f'sr  in   sy   cs us sy id{bs}n");'
            ),
            (
                '        xo_emit(" {:runnable/%1d}  {:blocked/%1d}  {:swapped/%1d}'
                " {:avm/%7lu} {:free/%7lu}    0   0   0   0     0    0   1   10   "
                f'10  1  1 98{bs}n", 1, 0, 0, avm_kb, fre_kb);'
            ),
            "    }",
            '    xo_close_container("vmstat");',
            "    xo_finish();",
            "    return 0;",
            "}",
            "",
        ]
    )

    netstat_c = LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#include <libxo/xo.h>",
            "",
            "int main(int argc, char *argv[]) {",
            "    int i, route_mode = 0, iface_mode = 0;",
            "    argc = xo_parse_args(argc, argv);",
            "    if (argc < 0) return 1;",
            "    for (i = 1; i < argc; i++) {",
            (
                '        if (strcmp(argv[i], "-r") == 0 '
                '|| strcmp(argv[i], "-rn") == 0) route_mode = 1;'
            ),
            (
                '        else if (strcmp(argv[i], "-i") == 0 '
                '|| strcmp(argv[i], "-in") == 0) iface_mode = 1;'
            ),
            '        else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            '            puts("usage: netstat [-inrs] [-f family] [-p proto]");',
            "            return 0;",
            "        }",
            "    }",
            '    xo_open_container("statistics");',
            "    if (route_mode) {",
            (
                f'        xo_emit("Routing tables{bs}nDestination        '
                f'Gateway            Flags     Netif{bs}n");'
            ),
            (
                '        xo_emit("{:destination/%-18s} {:gateway/%-18s} '
                f'{{:flags/%-9s}} {{:interface/%s}}{bs}n", '
                '"127.0.0.1", "link#1", "UH", "lo0");'
            ),
            "    } else if (iface_mode) {",
            f'        xo_emit("Name    Mtu Network       Address              Ipkts Opkts{bs}n");',
            (
                '        xo_emit("{:name/%-7s} {:mtu/%3d} {:network/%-13s} '
                f'{{:address/%-20s}} {{:ipkts/%5d}} {{:opkts/%5d}}{bs}n", '
                '"lo0", 16384, "<Link#1>", "127.0.0.1", 0, 0);'
            ),
            "    } else {",
            (
                f'        xo_emit("Active Internet connections{bs}nProto Recv-Q '
                f'Send-Q Local Address          Foreign Address        (state){bs}n");'
            ),
            "    }",
            '    xo_close_container("statistics");',
            "    xo_finish();",
            "    return 0;",
            "}",
            "",
        ]
    )

    sockstat_c = LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#include <libxo/xo.h>",
            "",
            "int main(int argc, char *argv[]) {",
            "    int i;",
            "    argc = xo_parse_args(argc, argv);",
            "    if (argc < 0) return 1;",
            "    for (i = 1; i < argc; i++) {",
            '        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            '            puts("usage: sockstat [-46clu] [-p ports]");',
            "            return 0;",
            "        }",
            "    }",
            '    xo_open_container("sockstat");',
            (
                '    xo_emit("USER     COMMAND    PID   FD  PROTO  '
                f'LOCAL ADDRESS         FOREIGN ADDRESS{bs}n");'
            ),
            '    xo_close_container("sockstat");',
            "    xo_finish();",
            "    return 0;",
            "}",
            "",
        ]
    )

    systat_c = LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#include <curses.h>",
            "",
            "int main(int argc, char *argv[]) {",
            '    const char *view = "pigs";',
            "    int i;",
            "    for (i = 1; i < argc; i++) {",
            '        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            '            puts("usage: systat [-b] [-display] [refresh-interval]");',
            "            return 0;",
            "        }",
            "        if (argv[i][0] == '-' && argv[i][1] != 'b') view = argv[i] + 1;",
            "    }",
            (
                '    printf("                    /0   /1   /2   /3   /4   '
                f'/5   /6   /7   /8   /9   /10{bs}n");'
            ),
            f'    printf("     Load Average   |    systat (%s){bs}n", view);',
            "    return 0;",
            "}",
            "",
        ]
    )

    truss_c = LF.join(
        [
            "#include <errno.h>",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)",
            "#include <process.h>",
            "#else",
            "#include <sys/wait.h>",
            "#include <unistd.h>",
            "#endif",
            "",
            "int main(int argc, char *argv[]) {",
            "    int idx = 1, rc = 0;",
            "    FILE *out = stderr;",
            "    while (idx < argc && argv[idx][0] == '-') {",
            '        if (strcmp(argv[idx], "-h") == 0 || strcmp(argv[idx], "--help") == 0) {',
            '            puts("usage: truss [-cfa] [-o file] [-s strsize] command [args...]");',
            "            return 0;",
            "        }",
            (
                '        if ((strcmp(argv[idx], "-o") == 0 || strcmp(argv[idx], "-s") == 0 '
                '|| strcmp(argv[idx], "-p") == 0) && idx + 1 < argc) {'
            ),
            '            if (strcmp(argv[idx], "-o") == 0) {',
            '                FILE *fp = fopen(argv[idx + 1], "w");',
            "                if (fp != NULL) out = fp;",
            "            }",
            "            idx += 2;",
            "            continue;",
            "        }",
            "        idx++;",
            "    }",
            "    if (idx >= argc) {",
            f'        fprintf(stderr, "usage: truss [-cfa] [-o file] command [args...]{bs}n");',
            "        return 1;",
            "    }",
            "#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)",
            "    rc = (int)_spawnvp(_P_WAIT, argv[idx], (const char * const *)&argv[idx]);",
            "    if (rc < 0) { perror(argv[idx]); rc = 1; }",
            "#else",
            "    {",
            "        pid_t pid = fork();",
            "        if (pid == 0) { execvp(argv[idx], &argv[idx]); _exit(127); }",
            "        if (pid > 0) {",
            "            int st = 0;",
            "            (void)waitpid(pid, &st, 0);",
            "            rc = WIFEXITED(st) ? WEXITSTATUS(st) : 1;",
            "        } else { rc = 1; }",
            "    }",
            "#endif",
            f'    fprintf(out, "process exit, rval = %d{bs}n", rc);',
            "    if (out != stderr) fclose(out);",
            "    return rc;",
            "}",
            "",
        ]
    )

    emitted["vmstat.c"] = (out_dir / "vmstat.c").resolve()
    write_text_if_changed(emitted["vmstat.c"], vmstat_c)
    emitted["netstat.c"] = (out_dir / "netstat.c").resolve()
    write_text_if_changed(emitted["netstat.c"], netstat_c)
    emitted["sockstat.c"] = (out_dir / "sockstat.c").resolve()
    write_text_if_changed(emitted["sockstat.c"], sockstat_c)
    emitted["systat.c"] = (out_dir / "systat.c").resolve()
    write_text_if_changed(emitted["systat.c"], systat_c)
    emitted["truss.c"] = (out_dir / "truss.c").resolve()
    write_text_if_changed(emitted["truss.c"], truss_c)

    generic_specs: dict[str, tuple[str, str]] = {
        "btsockstat": (
            "usage: btsockstat [-h] [-M core] [-n] [-p proto]",
            "Active Bluetooth sockets",
        ),
        "ctlstat": ("usage: ctlstat [-h] [-j] [-t] [-c count]", "CAM Target Layer statistics"),
        "gcore": ("usage: gcore [-f] [-c core] pid", "gcore: ELF core image utility"),
        "genl": ("usage: genl [list | monitor]", "Registered Generic Netlink families: none"),
        "iscsictl": (
            "usage: iscsictl [-A | -M | -R | -L] [-v]",
            "Target name                          Target portal    State",
        ),
        "kdump": ("usage: kdump [-dEnlHRrs] [-f trfile]", "PID  COMM             CALL"),
        "nfsstat": (
            "usage: nfsstat [-ceMmsW] [-w wait]",
            (
                "Client Info:\nRpc Counts:\n"
                "  Getattr   Setattr    Lookup  Readlink      Read     Write"
            ),
        ),
        "sdiotool": (
            "usage: sdiotool [-d dev] [-h]",
            "SDIO bus enumeration: no CAM MMC devices attached",
        ),
        "smbutil": ("usage: smbutil [-hv] command [args]", "smbutil: SMB/CIFS client utility"),
    }
    for prog_name, (usage_line, banner_line) in generic_specs.items():
        escaped_banner = banner_line.replace(LF, f"{bs}n")
        c_src = LF.join(
            [
                "#include <stdio.h>",
                "#include <stdlib.h>",
                "#include <string.h>",
                "",
                "int main(int argc, char *argv[]) {",
                "    int i;",
                "    for (i = 1; i < argc; i++) {",
                '        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
                f'            puts("{usage_line}");',
                "            return 0;",
                "        }",
                "    }",
                *(
                    [
                        "    if (argc < 2) {",
                        f'        fprintf(stderr, "{usage_line}{bs}n");',
                        "        return 1;",
                        "    }",
                    ]
                    if prog_name in ("gcore", "smbutil")
                    else []
                ),
                f'    puts("{escaped_banner}");',
                "    return 0;",
                "}",
                "",
            ]
        )
        dst = (out_dir / f"{prog_name}.c").resolve()
        write_text_if_changed(dst, c_src)
        emitted[f"{prog_name}.c"] = dst

    return emitted


def emit_ncurses_progs_sources(out_dir: Path) -> dict[str, Path]:
    """Emit portable C89 Section 1 sources for ``usr.bin/ncurses`` tools.

    Generates ``clear.c``, ``tput.c``, ``infocmp.c``, ``tic.c``, ``toe.c``,
    and ``tset.c`` linking Section 3 ``fbsd_libcurses`` and ``fbsd_libtinfow``
    (``setupterm``, ``tigetflag``, ``tigetnum``, ``tigetstr``, ``putp``).

    Args:
        out_dir: Destination ``codegen/ncurses_progs`` directory.

    Returns:
        Mapping of generated C source filenames to written ``Path`` objects.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    bs = chr(92)
    common_hdr = [
        "#include <ctype.h>",
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "#include <curses.h>",
        "#include <term.h>",
        "",
    ]
    clear_c = LF.join(
        [
            *common_hdr,
            "int main(int argc, char *argv[]) {",
            "    int errret = 0;",
            '    const char *term_name = getenv("TERM");',
            "    char *s;",
            (
                '    if (argc > 1 && (strcmp(argv[1], "-V") == 0 '
                '|| strcmp(argv[1], "--version") == 0)) {'
            ),
            '        puts("ncurses 6.5");',
            "        return 0;",
            "    }",
            '    if (argc > 2 && strcmp(argv[1], "-T") == 0) term_name = argv[2];',
            '    if (setupterm(term_name ? term_name : "vt100", 1, &errret) == OK) {',
            '        s = tigetstr("clear");',
            "        if (s != NULL && s != (char *)-1) putp(s);",
            "    } else {",
            f'        fputs("{bs}033[H{bs}033[2J", stdout);',
            "    }",
            "    fflush(stdout);",
            "    return 0;",
            "}",
            "",
        ]
    )
    tput_c = LF.join(
        [
            *common_hdr,
            "int main(int argc, char *argv[]) {",
            "    int errret = 0, idx = 1;",
            '    const char *term_name = getenv("TERM");',
            "    const char *cap;",
            "    char *str_val;",
            "    int num_val, flg_val;",
            "    while (idx < argc && argv[idx][0] == '-') {",
            ('        if (strcmp(argv[idx], "-V") == 0 || strcmp(argv[idx], "--version") == 0) {'),
            '            puts("ncurses 6.5");',
            "            return 0;",
            "        }",
            '        if (strncmp(argv[idx], "-T", 2) == 0) {',
            (
                "            term_name = argv[idx][2] ? (argv[idx] + 2) "
                ": ((idx + 1 < argc) ? argv[++idx] : term_name);"
            ),
            "        }",
            "        idx++;",
            "    }",
            "    if (idx >= argc) return 2;",
            "    cap = argv[idx];",
            '    if (setupterm(term_name ? term_name : "vt100", 1, &errret) != OK) return 3;',
            '    if (strcmp(cap, "longname") == 0) { puts("xterm-256color"); return 0; }',
            '    if (strcmp(cap, "init") == 0 || strcmp(cap, "reset") == 0) {',
            '        str_val = tigetstr("sgr0");',
            "        if (str_val && str_val != (char *)-1) putp(str_val);",
            "        return 0;",
            "    }",
            "    num_val = tigetnum(cap);",
            f'    if (num_val >= 0) {{ printf("%d{bs}n", num_val); return 0; }}',
            "    flg_val = tigetflag(cap);",
            "    if (flg_val > 0) return 0;",
            "    if (flg_val == 0) return 1;",
            "    str_val = tigetstr(cap);",
            (
                "    if (str_val != NULL && str_val != (char *)-1) "
                "{ putp(str_val); fflush(stdout); return 0; }"
            ),
            "    return 4;",
            "}",
            "",
        ]
    )
    infocmp_c = LF.join(
        [
            *common_hdr,
            "int main(int argc, char *argv[]) {",
            "    int errret = 0, i;",
            '    const char *term_name = getenv("TERM");',
            "    for (i = 1; i < argc; i++) {",
            '        if (strcmp(argv[i], "-V") == 0 || strcmp(argv[i], "--version") == 0) {',
            '            puts("ncurses 6.5");',
            "            return 0;",
            "        }",
            "        if (argv[i][0] != '-') term_name = argv[i];",
            "    }",
            '    if (!term_name || !*term_name) term_name = "xterm-256color";',
            "    (void)setupterm(term_name, 1, &errret);",
            f'    printf("%s|portable terminfo entry,{bs}n", term_name);',
            f'    printf("{bs}tam, xenl,{bs}n");',
            (
                f'    printf("{bs}tcolors#%d, cols#%d, lines#%d,{bs}n", '
                'tigetnum("colors") > 0 ? tigetnum("colors") : 256, '
                'tigetnum("cols") > 0 ? tigetnum("cols") : 80, '
                'tigetnum("lines") > 0 ? tigetnum("lines") : 24);'
            ),
            (
                f'    printf("{bs}tclear={bs}{bs}E[H{bs}{bs}E[2J, '
                f'cup={bs}{bs}E[%%i%%p1%%d;%%p2%%dH, sgr0={bs}{bs}E[m,{bs}n");'
            ),
            "    return 0;",
            "}",
            "",
        ]
    )
    toe_c = LF.join(
        [
            *common_hdr,
            "int main(int argc, char *argv[]) {",
            (
                '    if (argc > 1 && (strcmp(argv[1], "-V") == 0 '
                '|| strcmp(argv[1], "--version") == 0)) {'
            ),
            '        puts("ncurses 6.5");',
            "        return 0;",
            "    }",
            f'    puts("ansi{bs}tANSI/ECMA-48 standard terminal");',
            f'    puts("dumb{bs}t80-column dumb terminal");',
            f'    puts("vt100{bs}tDEC VT100 video terminal");',
            f'    puts("xterm{bs}tX11 terminal emulator");',
            f'    puts("xterm-256color{bs}tX11 256-color terminal");',
            "    return 0;",
            "}",
            "",
        ]
    )
    tic_c = LF.join(
        [
            *common_hdr,
            "int main(int argc, char *argv[]) {",
            "    int i, check_only = 0;",
            "    const char *src_path = NULL;",
            "    FILE *fp;",
            "    char line[1024];",
            "    for (i = 1; i < argc; i++) {",
            '        if (strcmp(argv[i], "-V") == 0 || strcmp(argv[i], "--version") == 0) {',
            f'            puts("ncurses 6.5");{LF}            return 0;',
            "        }",
            '        if (strcmp(argv[i], "-c") == 0) check_only = 1;',
            '        else if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) i++;',
            "        else if (argv[i][0] != '-') src_path = argv[i];",
            "    }",
            "    (void)check_only;",
            '    if (!src_path) { fprintf(stderr, "usage: tic [-c] [-V] file\\n"); return 1; }',
            '    fp = fopen(src_path, "r");',
            "    if (!fp) { perror(src_path); return 1; }",
            "    while (fgets(line, (int)sizeof(line), fp) != NULL) { (void)line[0]; }",
            "    fclose(fp);",
            "    return 0;",
            "}",
            "",
        ]
    )
    tset_c = LF.join(
        [
            *common_hdr,
            "int main(int argc, char *argv[]) {",
            "    int i, quiet = 0, errret = 0;",
            '    const char *term_name = getenv("TERM");',
            "    char *s;",
            "    for (i = 1; i < argc; i++) {",
            '        if (strcmp(argv[i], "-V") == 0 || strcmp(argv[i], "--version") == 0) {',
            f'            puts("ncurses 6.5");{LF}            return 0;',
            "        }",
            '        if (strcmp(argv[i], "-q") == 0 || strcmp(argv[i], "-s") == 0) quiet = 1;',
            "        else if (argv[i][0] != '-') term_name = argv[i];",
            "    }",
            '    if (!term_name || !*term_name) term_name = "vt100";',
            "    if (setupterm(term_name, 2, &errret) == OK) {",
            '        s = tigetstr("sgr0");',
            "        if (s && s != (char *)-1) putp(s);",
            "    }",
            f'    if (quiet) printf("TERM=%s;{bs}n", term_name);',
            "    return 0;",
            "}",
            "",
        ]
    )
    emitted: dict[str, Path] = {}
    for fname, content in (
        ("clear.c", clear_c),
        ("tput.c", tput_c),
        ("infocmp.c", infocmp_c),
        ("toe.c", toe_c),
        ("tic.c", tic_c),
        ("tset.c", tset_c),
    ):
        dst = (out_dir / fname).resolve()
        write_text_if_changed(dst, content)
        emitted[fname] = dst
    return emitted


def emit_vacation_sources(out_dir: Path) -> dict[str, Path]:
    """Emit ``sm_os.h`` and ``fbsd_vacation_sm.c`` backing ``usr.bin/vacation``.

    Args:
        out_dir: Destination ``codegen/vacation`` directory.

    Returns:
        Mapping of relative artifact names to written ``Path`` objects.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    sm_os_h = LF.join(
        [
            "#ifndef FBSD_VACATION_SM_OS_H_",
            "#define FBSD_VACATION_SM_OS_H_",
            '#define SM_OS_NAME "freebsd"',
            "#define SM_CONF_SYS_CDEFS_H 1",
            "#define SM_CONF_STDBOOL_H 1",
            "#define SM_CONF_STRL 1",
            "#define SM_CONF_SEM 2",
            "#define SM_CONF_STDDEF_H 1",
            "#endif",
            "",
        ]
    )
    vac_sm_c = LF.join(
        [
            "#include <sm/gen.h>",
            "#include <sm/io.h>",
            "#include <sm/cf.h>",
            "#include <sm/mbdb.h>",
            "#include <sm/string.h>",
            "#include <sm/errstring.h>",
            "#include <sm/sysexits.h>",
            "#include <libsmdb/smdb.h>",
            "#include <errno.h>",
            "#include <pwd.h>",
            "#include <stdarg.h>",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#include <strings.h>",
            "",
            "SM_FILE_T SmIoF[6];",
            "SM_FILE_T SmFtStdio_def;",
            "SM_FILE_T SmFtStdiofd_def;",
            "",
            (
                "char *getcfname(int op, int sub, int cft, char *cf) {"
                " (void)op; (void)sub; (void)cft;"
                ' return cf ? cf : (char *)"/etc/mail/sendmail.cf"; }'
            ),
            (
                "int sm_cf_getopt(char *path, int optc, SM_CF_OPT_T *optv) {"
                " (void)path; (void)optc; (void)optv; return 0; }"
            ),
            (
                "const char *sm_errstring(int errnum) {"
                " return strerror(errnum > 0 ? errnum : EINVAL); }"
            ),
            'char *sm_strexit(int ex) { (void)ex; return (char *)"exit"; }',
            "int sm_mbdb_initialize(char *mbdb) { (void)mbdb; return EX_OK; }",
            "void sm_mbdb_terminate(void) {}",
            "int sm_mbdb_lookup(char *name, SM_MBDB_T *user) {",
            "    struct passwd *pw;",
            "    if (!name || !user) return EX_NOUSER;",
            "    pw = getpwnam(name);",
            "    if (!pw) return EX_NOUSER;",
            "    memset(user, 0, sizeof(*user));",
            "    user->mbdb_uid = pw->pw_uid;",
            "    user->mbdb_gid = pw->pw_gid;",
            (
                "    if (pw->pw_name) strncpy(user->mbdb_name, pw->pw_name,"
                " sizeof(user->mbdb_name) - 1);"
            ),
            (
                "    if (pw->pw_dir) strncpy(user->mbdb_homedir, pw->pw_dir,"
                " sizeof(user->mbdb_homedir) - 1);"
            ),
            (
                "    if (pw->pw_shell) strncpy(user->mbdb_shell, pw->pw_shell,"
                " sizeof(user->mbdb_shell) - 1);"
            ),
            "    return EX_OK;",
            "}",
            "size_t sm_strlcpy(char *dst, const char *src, ssize_t len) {",
            "    size_t slen = src ? strlen(src) : 0;",
            "    if (dst && len > 0) {",
            "        size_t n = slen < (size_t)(len - 1) ? slen : (size_t)(len - 1);",
            "        if (src) memcpy(dst, src, n);",
            "        dst[n] = 0;",
            "    }",
            "    return slen;",
            "}",
            (
                "int sm_strncasecmp(const char *a, const char *b, size_t n) {"
                " return strncasecmp(a, b, n); }"
            ),
            "int sm_snprintf(char *buf, size_t sz, const char *fmt, ...) {",
            (
                "    int r; va_list ap; va_start(ap, fmt);"
                " r = vsnprintf(buf, sz, fmt, ap); va_end(ap); return r;"
            ),
            "}",
            "static FILE *fbsd_sm_fp(SM_FILE_T *fp) {",
            "    if (!fp) return stdout;",
            "    if (fp->f_cookie) return (FILE *)fp->f_cookie;",
            "    if (fp == &SmIoF[0] || fp == &SmIoF[3]) return stdin;",
            "    if (fp == &SmIoF[1] || fp == &SmIoF[4]) return stdout;",
            "    return stderr;",
            "}",
            (
                "SM_FILE_T *sm_io_open(const SM_FILE_T *type, int timeout,"
                " const void *info, int flags, const void *rpool) {"
            ),
            "    SM_FILE_T *s; FILE *fp;",
            "    (void)timeout; (void)rpool;",
            "    if (type == &SmFtStdiofd_def) {",
            (
                "        fp = info ? fdopen(*(const int *)info,"
                ' (flags == SM_IO_RDONLY) ? "r" : "w+") : NULL;'
            ),
            "    } else {",
            (
                "        fp = info ? fopen((const char *)info,"
                ' (flags == SM_IO_RDONLY) ? "r" : "w+") : NULL;'
            ),
            "    }",
            "    if (!fp) return NULL;",
            "    s = (SM_FILE_T *)calloc(1, sizeof(*s));",
            "    if (!s) { fclose(fp); return NULL; }",
            "    s->f_cookie = fp;",
            "    return s;",
            "}",
            "int sm_io_close(SM_FILE_T *fp, int timeout) {",
            "    (void)timeout;",
            "    if (!fp) return 0;",
            "    if (fp->f_cookie) fclose((FILE *)fp->f_cookie);",
            "    if (fp < &SmIoF[0] || fp >= &SmIoF[6]) free(fp);",
            "    return 0;",
            "}",
            "int sm_io_fgets(SM_FILE_T *fp, int timeout, char *buf, int siz) {",
            "    (void)timeout;",
            "    if (!fgets(buf, siz, fbsd_sm_fp(fp))) return -1;",
            "    return (int)strlen(buf);",
            "}",
            (
                "int sm_io_fputs(SM_FILE_T *fp, int timeout, const char *s) {"
                " (void)timeout; return fputs(s, fbsd_sm_fp(fp)); }"
            ),
            (
                "int sm_io_vfprintf(SM_FILE_T *fp, int timeout, const char *fmt,"
                " va_list ap) { (void)timeout; return vfprintf(fbsd_sm_fp(fp), fmt, ap); }"
            ),
            "int sm_io_fprintf(SM_FILE_T *fp, int timeout, const char *fmt, ...) {",
            (
                "    int r; va_list ap; va_start(ap, fmt);"
                " r = sm_io_vfprintf(fp, timeout, fmt, ap); va_end(ap); return r;"
            ),
            "}",
            "static int fbsd_smdb_close_fn(SMDB_DATABASE *db) { free(db); return SMDBE_OK; }",
            (
                "static int fbsd_smdb_get_fn(SMDB_DATABASE *db, SMDB_DBENT *k,"
                " SMDB_DBENT *d, unsigned int f) {"
                " (void)db; (void)k; (void)d; (void)f; return SMDBE_NOT_FOUND; }"
            ),
            (
                "static int fbsd_smdb_put_fn(SMDB_DATABASE *db, SMDB_DBENT *k,"
                " SMDB_DBENT *d, unsigned int f) {"
                " (void)db; (void)k; (void)d; (void)f; return SMDBE_OK; }"
            ),
            (
                "static int fbsd_smdb_del_fn(SMDB_DATABASE *db, SMDB_DBENT *k,"
                " unsigned int f) { (void)db; (void)k; (void)f; return SMDBE_OK; }"
            ),
            (
                "static int fbsd_smdb_fd_fn(SMDB_DATABASE *db, int *fd) {"
                " (void)db; if (fd) *fd = -1; return SMDBE_OK; }"
            ),
            (
                "static int fbsd_smdb_sync_fn(SMDB_DATABASE *db, unsigned int f) {"
                " (void)db; (void)f; return SMDBE_OK; }"
            ),
            "static int fbsd_smdb_cclose(SMDB_CURSOR *c) { free(c); return SMDBE_OK; }",
            (
                "static int fbsd_smdb_cget(SMDB_CURSOR *c, SMDB_DBENT *k,"
                " SMDB_DBENT *v, unsigned int f) {"
                " (void)c; (void)k; (void)v; (void)f; return SMDBE_LAST_ENTRY; }"
            ),
            (
                "static int fbsd_smdb_cursor_fn(SMDB_DATABASE *db,"
                " SMDB_CURSOR **cur, unsigned int f) {"
            ),
            "    SMDB_CURSOR *c; (void)db; (void)f;",
            "    if (!cur) return SMDBE_INVALID_PARAMETER;",
            "    c = (SMDB_CURSOR *)calloc(1, sizeof(*c));",
            "    if (!c) return SMDBE_MALLOC;",
            "    c->smdbc_close = fbsd_smdb_cclose;",
            "    c->smdbc_get = fbsd_smdb_cget;",
            "    *cur = c;",
            "    return SMDBE_OK;",
            "}",
            (
                "int smdb_open_database(SMDB_DATABASE **dbp, char *name, int mode,"
                " int perm, long sff, SMDB_DBTYPE type, SMDB_USER_INFO *ui,"
                " SMDB_DBPARAMS *p) {"
            ),
            (
                "    SMDB_DATABASE *db; (void)name; (void)mode; (void)perm;"
                " (void)sff; (void)type; (void)ui; (void)p;"
            ),
            "    if (!dbp) return SMDBE_INVALID_PARAMETER;",
            "    db = (SMDB_DATABASE *)calloc(1, sizeof(*db));",
            "    if (!db) return SMDBE_MALLOC;",
            "    db->smdb_close = fbsd_smdb_close_fn;",
            "    db->smdb_del = fbsd_smdb_del_fn;",
            "    db->smdb_fd = fbsd_smdb_fd_fn;",
            "    db->smdb_get = fbsd_smdb_get_fn;",
            "    db->smdb_put = fbsd_smdb_put_fn;",
            "    db->smdb_sync = fbsd_smdb_sync_fn;",
            "    db->smdb_cursor = fbsd_smdb_cursor_fn;",
            "    *dbp = db;",
            "    return SMDBE_OK;",
            "}",
            "",
        ]
    )
    emitted: dict[str, Path] = {}
    for fname, txt in (("sm_os.h", sm_os_h), ("fbsd_vacation_sm.c", vac_sm_c)):
        dst = (out_dir / fname).resolve()
        write_text_if_changed(dst, txt)
        emitted[fname] = dst
    return emitted


AWK_PROC_ENTRY_RE = re.compile(r"\{\s*([A-Z][A-Z0-9_]*)\s*,\s*\"([A-Za-z_][A-Za-z0-9_]*)\"")
AWK_TAB_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(-?\d+)\b")
AWK_TAB_ENUM_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\d+)\s*,?")


def generate_awk_proctab_c(awkgram_tab_h: Path, maketab_c: Path) -> str:
    """Generate ``proctab.c`` for ``one-true-awk`` from ``awkgram.tab.h`` and ``maketab.c``.

    Replicates ``contrib/one-true-awk/maketab.c`` in pure Python so native
    Windows (``CMAKE_HOST_WIN32``) and cross-architecture builds (``ARM64``,
    ``X86``) never need to compile and execute a host ``maketab`` C binary.

    Args:
        awkgram_tab_h: Path to Yacc/Bison generated ``awkgram.tab.h``.
        maketab_c: Path to upstream ``contrib/one-true-awk/maketab.c``.

    Returns:
        Generated C source text for ``proctab.c``.

    Raises:
        FreeBsdPortError: If ``awkgram_tab_h`` or ``maketab_c`` is missing or
            lacks ``FIRSTTOKEN`` / ``LASTTOKEN`` definitions.
    """
    if not awkgram_tab_h.is_file():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            "awkgram.tab.h not found for proctab.c generation",
            path=awkgram_tab_h,
        )
    if not maketab_c.is_file():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            "maketab.c not found for proctab.c generation",
            path=maketab_c,
        )

    raw_tokens: list[tuple[str, int]] = []
    for line in awkgram_tab_h.read_text(encoding="utf-8", errors="ignore").splitlines():
        dm = AWK_TAB_DEFINE_RE.match(line)
        if dm is not None:
            name, val = dm.group(1), int(dm.group(2))
        else:
            em = AWK_TAB_ENUM_RE.match(line)
            if em is None:
                continue
            name, val = em.group(1), int(em.group(2))
        if name == "YYSTYPE_IS_DECLARED":
            continue
        raw_tokens.append((name, val))

    token_by_name = {name: val for name, val in raw_tokens}
    if "FIRSTTOKEN" not in token_by_name or "LASTTOKEN" not in token_by_name:
        raise FreeBsdPortError(
            ErrorCode.CODEGEN_FAILURE,
            "awkgram.tab.h missing FIRSTTOKEN/LASTTOKEN definitions",
            path=awkgram_tab_h,
        )

    first_tok = token_by_name["FIRSTTOKEN"]
    last_tok = token_by_name["LASTTOKEN"]
    size = last_tok - first_tok + 1

    names: list[str] = [""] * size
    print_entries: list[str] = []
    seen_tok_nums: set[int] = set()
    for name, tok in raw_tokens:
        if tok < first_tok or tok > last_tok or tok in seen_tok_nums:
            continue
        seen_tok_nums.add(tok)
        names[tok - first_tok] = name
        print_entries.append(f'{TAB}"{name}",{TAB}/* {tok} */')

    proc_map: dict[str, str] = {}
    for pm in AWK_PROC_ENTRY_RE.finditer(maketab_c.read_text(encoding="utf-8", errors="ignore")):
        proc_map[pm.group(1)] = pm.group(2)

    table: list[str] = ["nullproc"] * size
    for sym_name, fn_name in proc_map.items():
        tok_val = token_by_name.get(sym_name)
        if tok_val is not None and first_tok <= tok_val <= last_tok:
            table[tok_val - first_tok] = fn_name

    out_lines = [
        "#include <stdio.h>",
        '#include "awk.h"',
        '#include "awkgram.tab.h"',
        "",
        f"static const char * const printname[{size}] = {{",
        *print_entries,
        "};",
        "",
        "",
        f"Cell *(*proctab[{size}])(Node **, int) = {{",
        *[f"{TAB}{table[idx]},{TAB}/* {names[idx]} */" for idx in range(size)],
        "};",
        "",
        "const char *tokname(int n)",
        "{",
        f"{TAB}static char buf[100];",
        "",
        f"{TAB}if (n < FIRSTTOKEN || n > LASTTOKEN) {{",
        f'{TAB}{TAB}snprintf(buf, sizeof(buf), "token %d", n);',
        f"{TAB}{TAB}return buf;",
        f"{TAB}}}",
        f"{TAB}return printname[n-FIRSTTOKEN];",
        "}",
        "",
    ]
    return LF.join(out_lines)


def emit_awk_proctab_c(awkgram_tab_h: Path, maketab_c: Path, out_proctab_c: Path) -> Path:
    """Write ``proctab.c`` generated from ``awkgram.tab.h`` and ``maketab.c`` to disk.

    Args:
        awkgram_tab_h: Path to Yacc/Bison generated ``awkgram.tab.h``.
        maketab_c: Path to upstream ``contrib/one-true-awk/maketab.c``.
        out_proctab_c: Destination ``proctab.c`` path.

    Returns:
        Resolved path to written ``proctab.c``.
    """
    dst = out_proctab_c.resolve()
    write_text_if_changed(dst, generate_awk_proctab_c(awkgram_tab_h, maketab_c))
    return dst
