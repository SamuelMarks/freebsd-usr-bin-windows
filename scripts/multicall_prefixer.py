"""Multi-file C symbol isolation and multicall dispatcher generator.

Transforms single-file and multi-file FreeBSD ``usr.bin`` C utilities so they
can be linked into a single ``freebsd-usr-bin`` multicall executable without
duplicate symbol collisions across translation units:

  - Scans all C sources belonging to a ``BinarySpec`` to discover utility-defined
    external functions and file-scope global variables.
  - Emits ``${FREEBSD_GEN_DIR}/applets/<id>_sym_prefix.h`` documenting the
    remapped symbol table for inspection and standalone tooling.
  - Rewrites ``main(...)`` to ``int fbsd_<id>_main(int argc, char *argv[])`` and
    prefixes utility-internal symbols outside comments, string/char literals,
    preprocessor ``#include`` directives, and ``.`` / ``->`` member accesses.
  - Generates ``src/freebsd_multicall_main.c`` resetting ``optind = 1``,
    ``optreset = 1`` (when available), and ``errno = 0`` prior to dispatch.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts.errors import ErrorCode, FreeBsdPortError, write_text_if_changed

LF: str = chr(10)
TAB: str = chr(9)
BS: str = chr(92)
DQ: str = chr(34)
SQ: str = chr(39)

C_KEYWORDS_AND_STD: frozenset[str] = frozenset(
    {
        "auto",
        "bool",
        "break",
        "case",
        "char",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "errno",
        "extern",
        "false",
        "float",
        "for",
        "goto",
        "if",
        "inline",
        "int",
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "intmax_t",
        "intptr_t",
        "long",
        "main",
        "off_t",
        "optarg",
        "opterr",
        "optind",
        "optopt",
        "optreset",
        "pid_t",
        "ptrdiff_t",
        "register",
        "restrict",
        "return",
        "short",
        "signed",
        "size_t",
        "sizeof",
        "ssize_t",
        "static",
        "stderr",
        "stdin",
        "stdout",
        "struct",
        "switch",
        "time_t",
        "true",
        "typedef",
        "uid_t",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
        "uintmax_t",
        "uintptr_t",
        "union",
        "unsigned",
        "va_list",
        "void",
        "volatile",
        "wchar_t",
        "while",
        "FILE",
        "NULL",
    }
)

COMMON_COLLISION_SYMBOLS: frozenset[str] = frozenset(
    {
        "usage",
        "version",
        "progname",
        "vflag",
        "qflag",
        "fflag",
        "nflag",
        "rflag",
        "sflag",
        "dflag",
        "cflag",
        "iflag",
        "lflag",
        "pflag",
        "tflag",
        "wflag",
        "xflag",
        "debug",
        "verbose",
    }
)

SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_]")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

FUNC_DEF_LINE_RE = re.compile(
    f"^(?:[A-Za-z_][A-Za-z0-9_]*[ {TAB}*]+)+([A-Za-z_][A-Za-z0-9_]*)[ {TAB}]*[(][^;]*[{{][ {TAB}]*$"
)
GLOBAL_DEF_LINE_RE = re.compile(
    f"^(?:(?:unsigned|signed|long|short|const|volatile|struct|enum)[ {TAB}]+)*"
    f"[A-Za-z_][A-Za-z0-9_]*[ {TAB}*]+([A-Za-z_][A-Za-z0-9_]*)"
    f"(?:{BS}[[^]]*{BS}])?[ {TAB}]*(?:=[^;]+)?;$"
)
MAIN_DEF_RE = re.compile(f"(?:int[ {TAB}]+)?main[ {TAB}{LF}]*[(]([^)]*)[)][ {TAB}{LF}]*[{{]")


def sanitize_applet_id(name: str) -> str:
    """Convert an applet binary name into a valid lowercase C identifier stem.

    Args:
        name: Raw applet name (e.g. ``ssh-copy-id`` or ``locate.bigram``).

    Returns:
        Sanitized C identifier stem (e.g. ``ssh_copy_id`` or ``locate_bigram``).

    Raises:
        FreeBsdPortError: If ``name`` produces an empty identifier.
    """
    cleaned = SAFE_ID_RE.sub("_", name.strip().lower()).strip("_")
    if not cleaned:
        raise FreeBsdPortError(
            ErrorCode.CODEGEN_FAILURE,
            f"Applet name cannot be sanitized to a C identifier: {name!r}",
        )
    if cleaned[0].isdigit():
        return f"app_{cleaned}"
    return cleaned


def _strip_comments_keep_lines(source_text: str) -> str:
    """Replace C block and line comments with spaces while preserving newlines.

    Args:
        source_text: Raw C source code.

    Returns:
        Comment-stripped C text with identical line boundaries.
    """
    out: list[str] = []
    idx = 0
    length = len(source_text)
    while idx < length:
        ch = source_text[idx]
        nxt = source_text[idx + 1] if idx + 1 < length else ""
        if ch == "/" and nxt == "*":
            out.append("  ")
            idx += 2
            while idx < length and not (
                source_text[idx] == "*" and idx + 1 < length and source_text[idx + 1] == "/"
            ):
                out.append(LF if source_text[idx] == LF else " ")
                idx += 1
            if idx < length:
                out.append("  ")
                idx += 2
        elif ch == "/" and nxt == "/":
            while idx < length and source_text[idx] != LF:
                out.append(" ")
                idx += 1
        elif ch in (DQ, SQ):
            quote = ch
            out.append(ch)
            idx += 1
            while idx < length and source_text[idx] != quote:
                if source_text[idx] == BS and idx + 1 < length:
                    out.append(source_text[idx : idx + 2])
                    idx += 2
                else:
                    out.append(source_text[idx])
                    idx += 1
            if idx < length:
                out.append(source_text[idx])
                idx += 1
        else:
            out.append(ch)
            idx += 1
    return "".join(out)


def discover_external_symbols(c_sources: Sequence[Path]) -> tuple[str, ...]:
    """Scan C translation units to identify non-static file-scope definitions.

    Args:
        c_sources: Sequence of C source ``Path``s belonging to one utility.

    Returns:
        Sorted tuple of utility-defined external C symbol names.
    """
    discovered: set[str] = set(COMMON_COLLISION_SYMBOLS)
    for src_path in [p for p in c_sources if p.is_file()]:
        stripped_text = _strip_comments_keep_lines(
            src_path.read_text(encoding="utf-8", errors="ignore")
        )
        brace_depth = 0
        pending_sig = ""
        for raw_line in stripped_text.splitlines():
            line = raw_line.strip()
            if brace_depth == 0 and line and not line.startswith("#"):
                combined = f"{pending_sig} {line}".strip() if pending_sig else line
                is_internal_linkage = combined.startswith(("static ", "extern ", "typedef "))
                if not is_internal_linkage:
                    fn_m = FUNC_DEF_LINE_RE.match(combined)
                    if fn_m is not None:
                        cand = fn_m.group(1)
                        if cand not in C_KEYWORDS_AND_STD and not cand.startswith("fbsd_"):
                            discovered.add(cand)
                    gl_m = GLOBAL_DEF_LINE_RE.match(combined)
                    if gl_m is not None:
                        cand = gl_m.group(1)
                        if cand not in C_KEYWORDS_AND_STD and not cand.startswith("fbsd_"):
                            discovered.add(cand)
                if ";" not in combined and "{" not in combined:
                    pending_sig = combined
                else:
                    pending_sig = ""
            else:
                pending_sig = ""

            for ch in raw_line:
                if ch == "{":
                    brace_depth += 1
                elif ch == "}" and brace_depth > 0:
                    brace_depth -= 1

    return tuple(sorted(discovered - C_KEYWORDS_AND_STD))


def emit_symbol_prefix_header(
    applet_id: str,
    symbols: Sequence[str],
    out_dir: Path,
) -> Path:
    """Write ``<applet_id>_sym_prefix.h`` documenting isolated multicall symbols.

    Args:
        applet_id: Sanitized C identifier for the applet.
        symbols: External symbol names isolated for this applet.
        out_dir: Destination ``applets/`` directory.

    Returns:
        Resolved ``Path`` to the generated ``_sym_prefix.h`` file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    guard = f"FBSD_{applet_id.upper()}_SYM_PREFIX_H_"
    lines = [
        f"/* Multicall symbol isolation table for {applet_id} */",
        f"#ifndef {guard}",
        f"#define {guard}",
    ]
    for sym in sorted(set(symbols)):
        lines.append(f"/* {sym} -> fbsd_{applet_id}_{sym} */")
    lines.extend(["#endif", ""])
    hdr_path = (out_dir / f"{applet_id}_sym_prefix.h").resolve()
    write_text_if_changed(hdr_path, LF.join(lines))
    return hdr_path


def _rewrite_identifiers_in_code_segment(
    segment: str,
    applet_id: str,
    sym_set: frozenset[str],
) -> str:
    """Rename ``sym_set`` identifiers in a non-comment, non-literal C code slice.

    Skips ``#include`` directives and struct/union member accesses (``.`` / ``->``).

    Args:
        segment: Raw C code slice containing no comments or string literals.
        applet_id: Sanitized applet identifier prefix.
        sym_set: Set of symbol names to prefix with ``fbsd_<applet_id>_``.

    Returns:
        Rewritten C code slice.
    """
    out: list[str] = []
    last_end = 0
    for match in IDENT_RE.finditer(segment):
        ident = match.group(0)
        start, end = match.span()
        out.append(segment[last_end:start])
        line_start = segment.rfind(LF, 0, start) + 1
        line_end = segment.find(LF, start)
        cur_line = segment[line_start:] if line_end == -1 else segment[line_start:line_end]
        is_inc = cur_line.lstrip().startswith("#") and "include" in cur_line
        prefix_slice = segment[:start].rstrip()
        is_member = prefix_slice.endswith((".", "->"))
        if ident in sym_set and not is_member and not is_inc:
            out.append(f"fbsd_{applet_id}_{ident}")
        else:
            out.append(ident)
        last_end = end
    out.append(segment[last_end:])
    return "".join(out)


def rewrite_c_source_for_multicall(
    source_text: str,
    applet_id: str,
    symbols: Sequence[str],
    *,
    rewrite_main: bool = True,
) -> str:
    """Transform a C source or local header file for collision-free multicall linkage.

    Args:
        source_text: Original C source code text.
        applet_id: Sanitized applet identifier stem.
        symbols: Utility-internal external/static collision symbols to prefix.
        rewrite_main: Whether to rewrite ``main(...)`` to ``fbsd_<applet_id>_main``.

    Returns:
        Transformed C source text safe for linking into ``freebsd-usr-bin``.
    """
    sym_set = frozenset(symbols) - C_KEYWORDS_AND_STD
    idx = 0
    length = len(source_text)
    pieces: list[str] = []

    while idx < length:
        ch = source_text[idx]
        nxt = source_text[idx + 1] if idx + 1 < length else ""
        if ch == "/" and nxt == "*":
            end_c = source_text.find("*/", idx + 2)
            stop = length if end_c == -1 else end_c + 2
            pieces.append(source_text[idx:stop])
            idx = stop
        elif ch == "/" and nxt == "/":
            end_l = source_text.find(LF, idx + 2)
            stop = length if end_l == -1 else end_l
            pieces.append(source_text[idx:stop])
            idx = stop
        elif ch in (DQ, SQ):
            quote = ch
            start_q = idx
            idx += 1
            while idx < length and source_text[idx] != quote:
                idx += 2 if (source_text[idx] == BS and idx + 1 < length) else 1
            if idx < length:
                idx += 1
            pieces.append(source_text[start_q:idx])
        else:
            code_start = idx
            while idx < length:
                c_cur = source_text[idx]
                c_nxt = source_text[idx + 1] if idx + 1 < length else ""
                if (c_cur == "/" and c_nxt in ("*", "/")) or c_cur in (DQ, SQ):
                    break
                idx += 1
            pieces.append(
                _rewrite_identifiers_in_code_segment(
                    source_text[code_start:idx],
                    applet_id,
                    sym_set,
                )
            )

    rewritten = "".join(pieces)
    if rewrite_main:

        def _replace_main(match: re.Match[str]) -> str:
            """Rewrite matched ``main(...)`` signature to ``fbsd_<id>_main``.

            Args:
                match: Regex match object on ``main(...) {``.

            Returns:
                Standardized ``int fbsd_<applet_id>_main(...) {`` header.
            """
            params = match.group(1).strip()
            if not params or params == "void":
                return (
                    f"int fbsd_{applet_id}_main(int fbsd_u_argc, char *fbsd_u_argv[]) "
                    "{ (void)fbsd_u_argc; (void)fbsd_u_argv;"
                )
            return f"int fbsd_{applet_id}_main({params}) {{"

        rewritten = MAIN_DEF_RE.sub(_replace_main, rewritten, count=1)

    return rewritten


def stage_multicall_applet(
    prog: str,
    c_sources: Sequence[Path],
    out_dir: Path,
) -> tuple[Path, tuple[Path, ...]]:
    """Stage all C files (and local headers) of ``prog`` for multicall compilation.

    Args:
        prog: Binary name (e.g. ``sed``, ``printf``).
        c_sources: Sequence of resolved ``.c`` files for ``prog``.
        out_dir: Destination ``applets/`` directory.

    Returns:
        Tuple of ``(sym_prefix_header_path, staged_c_source_paths)``.
    """
    applet_id = sanitize_applet_id(prog)
    applet_dir = (out_dir / applet_id).resolve()
    applet_dir.mkdir(parents=True, exist_ok=True)

    symbols = discover_external_symbols(c_sources)
    hdr_path = emit_symbol_prefix_header(applet_id, symbols, applet_dir)

    seen_dirs: set[Path] = set()
    for c_file in c_sources:
        if c_file.is_file() and c_file.parent.resolve() not in seen_dirs:
            src_parent = c_file.parent.resolve()
            seen_dirs.add(src_parent)
            for local_hdr in sorted(src_parent.glob("*.h")):
                hdr_text = local_hdr.read_text(encoding="utf-8", errors="ignore")
                rewritten_hdr = rewrite_c_source_for_multicall(
                    hdr_text,
                    applet_id,
                    symbols,
                    rewrite_main=False,
                )
                write_text_if_changed((applet_dir / local_hdr.name).resolve(), rewritten_hdr)

    staged_c: list[Path] = []
    for idx, c_file in enumerate(c_sources):
        raw_c = c_file.read_text(encoding="utf-8", errors="ignore")
        rewritten_c = rewrite_c_source_for_multicall(
            raw_c,
            applet_id,
            symbols,
            rewrite_main=True,
        )
        dst_c = (applet_dir / f"{idx:02d}_{c_file.name}").resolve()
        write_text_if_changed(dst_c, rewritten_c)
        staged_c.append(dst_c)

    return hdr_path, tuple(staged_c)


def generate_multicall_dispatcher_c(
    applet_progs: Sequence[str],
    alias_links: Mapping[str, str] | None = None,
    total_entries: int = 280,
) -> str:
    """Generate ``freebsd_multicall_main.c`` with ``optind`` / ``optreset`` / ``errno`` reset.

    Args:
        applet_progs: Sequence of primary applet names linked into the multicall binary.
        alias_links: Optional mapping from alias name (e.g. ``gunzip``) to primary ``prog``.
        total_entries: Total audited ``usr.bin`` entry count reported by ``--version``.

    Returns:
        Complete C89 source text for ``freebsd_multicall_main.c``.
    """
    unique_progs = sorted(dict.fromkeys(applet_progs))
    links_map = dict(alias_links) if alias_links is not None else {}

    lines = [
        "#include <errno.h>",
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
        "#include <unistd.h>",
        "#else",
        "extern int optind;",
        "#endif",
        "#if defined(__FreeBSD__) || defined(__APPLE__)",
        "extern int optreset;",
        "#endif",
        "",
    ]

    for prog in unique_progs:
        aid = sanitize_applet_id(prog)
        lines.append(f"int fbsd_{aid}_main(int argc, char *argv[]);")

    lines.extend(
        [
            "",
            "typedef int (*fbsd_applet_fn)(int, char **);",
            "typedef struct fbsd_applet_entry {",
            "    const char *name;",
            "    fbsd_applet_fn fn;",
            "} fbsd_applet_entry_t;",
            "",
            "static const fbsd_applet_entry_t g_applets[] = {",
        ]
    )
    for prog in unique_progs:
        aid = sanitize_applet_id(prog)
        lines.append(f'    {{ "{prog}", fbsd_{aid}_main }},')
    for alias, target in sorted(links_map.items()):
        if target in unique_progs and alias not in unique_progs:
            aid = sanitize_applet_id(target)
            lines.append(f'    {{ "{alias}", fbsd_{aid}_main }},')
    lines.extend(
        [
            "    { NULL, NULL }",
            "};",
            "",
            "static const char *strip_exe_basename(const char *argv0, char *buf, size_t bsz) {",
            "    const char *slash = strrchr(argv0, '/');",
            f"    const char *bslash = strrchr(argv0, '{BS}{BS}');",
            "    const char *base = argv0;",
            "    size_t len;",
            "    if (slash != NULL && slash + 1 > base) base = slash + 1;",
            "    if (bslash != NULL && bslash + 1 > base) base = bslash + 1;",
            "    len = strlen(base);",
            "    if (len >= bsz) len = bsz - 1;",
            "    memcpy(buf, base, len);",
            f"    buf[len] = '{BS}0';",
            "    if (len > 4 && (",
            '        strcmp(buf + len - 4, ".exe") == 0 || strcmp(buf + len - 4, ".EXE") == 0',
            "    )) {",
            f"        buf[len - 4] = '{BS}0';",
            "    }",
            "    return buf;",
            "}",
            "",
            "static int dispatch_applet(const char *name, int argc, char *argv[]) {",
            "    size_t i;",
            "    for (i = 0; g_applets[i].name != NULL; i++) {",
            "        if (strcmp(g_applets[i].name, name) == 0) {",
            "            errno = 0;",
            "            optind = 1;",
            "#if defined(__FreeBSD__) || defined(__APPLE__)",
            "            optreset = 1;",
            "#endif",
            "            return g_applets[i].fn(argc, argv);",
            "        }",
            "    }",
            "    return -1;",
            "}",
            "",
            "int main(int argc, char *argv[]) {",
            "    char prog_buf[256];",
            (
                "    const char *invoked = (argc > 0 && argv[0] != NULL) "
                '? argv[0] : "freebsd-usr-bin";'
            ),
            "    const char *base = strip_exe_basename(invoked, prog_buf, sizeof(prog_buf));",
            "    int rc;",
            '    if (strcmp(base, "freebsd-usr-bin") != 0 && strcmp(base, "FREEBSD-") != 0) {',
            "        rc = dispatch_applet(base, argc, argv);",
            "        if (rc != -1) return rc;",
            "    }",
            '    if (argc < 2 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {',
            (
                f'        printf("usage: freebsd-usr-bin '
                f'[--list | --version] <applet> [args...]{BS}n");'
            ),
            "        return (argc < 2) ? 1 : 0;",
            "    }",
            '    if (strcmp(argv[1], "--version") == 0) {',
            (f'        printf("freebsd-usr-bin 15.0.0 ({total_entries} entries audited){BS}n");'),
            "        return 0;",
            "    }",
            '    if (strcmp(argv[1], "--list") == 0) {',
            "        size_t i;",
            "        for (i = 0; g_applets[i].name != NULL; i++) {",
            f'            printf("%s{BS}n", g_applets[i].name);',
            "        }",
            "        return 0;",
            "    }",
            "    rc = dispatch_applet(argv[1], argc - 1, argv + 1);",
            "    if (rc == -1) {",
            f'        fprintf(stderr, "freebsd-usr-bin: unknown applet: %s{BS}n", argv[1]);',
            "        return 127;",
            "    }",
            "    return rc;",
            "}",
            "",
        ]
    )
    return LF.join(lines)
