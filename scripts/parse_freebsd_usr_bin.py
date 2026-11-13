#!/usr/bin/env python3
"""Deterministic FreeBSD ``usr.bin`` Makefile parser and build manifest generator.

Audits all 280 entries (274 subdirectories and 6 top-level Makefiles) in
``../freebsd-src/usr.bin`` (or ``./freebsd-src/usr.bin``), expands multi-binary
containers and ``PROGS=`` Makefiles into concrete ``BinarySpec`` targets, maps
all 68 ``LIBADD`` libraries to canonical Section 3 CMake targets, evaluates
FreeBSD ``.if`` / ``.elif`` / ``.else`` / ``.endif`` blocks deterministically,
stages declarative ``.patch`` files and build-time codegen artifacts out-of-tree,
and writes ``freebsd_usr_bin_manifest.json`` and ``freebsd_usr_bin_targets.cmake``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts.codegen_helpers import KERNEL_STAT_PROGS, emit_all_codegen_helpers
from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.script_applets import emit_all_script_applets, generate_script_applet_c
from scripts.stage_and_patch import stage_patched_sources

NL: str = chr(10)
TAB: str = chr(9)
BS: str = chr(92)
DQUOTE: str = chr(34)

TOP_MAKEFILES: tuple[str, ...] = (
    "Makefile",
    "Makefile.amd64",
    "Makefile.arm",
    "Makefile.i386",
    "Makefile.inc",
    "Makefile.powerpc",
)

MULTI_BINARY_CONTAINERS: tuple[str, ...] = (
    "bluetooth",
    "bsdiff",
    "fortune",
    "locate",
    "tip",
)

SCRIPT_AND_SPECIAL_DIRS: tuple[str, ...] = (
    "alias",
    "clang",
    "command",
    "dc",
    "kyua",
    "lorder",
    "man",
    "mkdep",
    "ofed",
    "pagesize",
    "ssh-copy-id",
    "tests",
    "xohtml",
    "xolint",
)

SYS_KERNEL_LIBS: frozenset[str] = frozenset(
    {
        "bsm",
        "cam",
        "devstat",
        "iscsiutil",
        "jail",
        "kvm",
        "lutok",
        "memstat",
        "netgraph",
        "nv",
        "pam",
        "procstat",
        "rpcsvc",
        "rt",
        "smb",
        "sqlite3",
        "sysdecode",
        "usbhid",
        "ypclnt",
    }
)

CURSES_TUI_LIBS: frozenset[str] = frozenset(
    {
        "bsddialog",
        "dialog",
        "dpv",
        "edit",
        "ncursesw",
        "tinfow",
    }
)

BSD_SHIM_LIBS: frozenset[str] = frozenset(
    {
        "cap_fileargs",
        "cap_grp",
        "cap_net",
        "cap_netdb",
        "cap_pwd",
        "cap_sysctl",
        "cap_syslog",
        "casper",
        "util",
        "xo",
    }
)

LIBADD_TO_SECTION3_TARGET: dict[str, str | None] = {
    "archive": "fbsd_libarchive",
    "bsddialog": "fbsd_libbsddialog",
    "bsdxml": "fbsd_libbsdxml",
    "bsm": "fbsd_libsys",
    "bz2": "fbsd_libbz2",
    "calendar": "fbsd_libcalendar",
    "cam": "fbsd_libsys",
    "cap_fileargs": "fbsd_libutil",
    "cap_grp": "fbsd_libutil",
    "cap_net": "fbsd_libutil",
    "cap_netdb": "fbsd_libutil",
    "cap_pwd": "fbsd_libutil",
    "cap_sysctl": "fbsd_libutil",
    "cap_syslog": "fbsd_libutil",
    "casper": "fbsd_libutil",
    "crypt": "fbsd_libsys",
    "crypto": "fbsd_libsys",
    "devstat": "fbsd_libsys",
    "diff": "fbsd_libdiff",
    "dwarf": "fbsd_libelftc",
    "edit": "fbsd_libedit",
    "elf": "fbsd_libelftc",
    "elftc": "fbsd_libelftc",
    "fetch": "fbsd_libfetch",
    "ipsec": "fbsd_libsys",
    "iscsiutil": "fbsd_libsys",
    "jail": "fbsd_libsys",
    "krb5": "fbsd_libsys",
    "kvm": "fbsd_libsys",
    "ldns": "fbsd_libldns",
    "lutok": "fbsd_libsys",
    "lzma": "fbsd_liblzma",
    "m": None,
    "magic": "fbsd_libmagic",
    "md": "fbsd_libmd",
    "memstat": "fbsd_libsys",
    "mp": "fbsd_libmp",
    "mt": "fbsd_libutil",
    "ncursesw": "fbsd_libcurses",
    "netbsd": "fbsd_libnetbsd",
    "netgraph": "fbsd_libsys",
    "nv": "fbsd_libsys",
    "openbsd": "fbsd_libopenbsd",
    "pam": "fbsd_libsys",
    "pe": "fbsd_libelftc",
    "pkgconf": "fbsd_libpkgconf",
    "procstat": "fbsd_libsys",
    "pthread": None,
    "regex": "fbsd_libregex",
    "roken": "fbsd_libsys",
    "rpcsvc": "fbsd_libsys",
    "rt": None,
    "sbuf": "fbsd_libsbuf",
    "sm": "fbsd_libsys",
    "smb": "fbsd_libsys",
    "smdb": "fbsd_libsys",
    "smutil": "fbsd_libsys",
    "sqlite3": "fbsd_libsys",
    "stats": "fbsd_libutil",
    "sysdecode": "fbsd_libsys",
    "telnet": "fbsd_libtelnet",
    "tinfow": "fbsd_libtinfow",
    "usbhid": "fbsd_libsys",
    "util": "fbsd_libutil",
    "vers": "fbsd_libsys",
    "xo": "fbsd_libxo",
    "ypclnt": "fbsd_libsys",
    "z": "fbsd_libz",
    "zstd": "fbsd_libzstd",
}

DEFAULT_MK_ENV: dict[str, str] = {
    "MACHINE_CPUARCH": "amd64",
    "MACHINE_ARCH": "amd64",
    "MACHINE": "amd64",
    "BINDIR": "/usr/bin",
    "USE_FILEMON": "no",
    "BOOTSTRAPPING": "1",
    "MK_CASPER": "no",
    "MK_CAPSICUM": "no",
    "MK_OPENSSL": "no",
    "MK_ICONV": "no",
    "MK_SORT_THREADS": "no",
    "MK_AUDIT": "no",
    "MK_NLS": "no",
    "MK_NIS": "no",
    "MK_FILEMON": "no",
    "MK_KERBEROS_SUPPORT": "no",
    "MK_STATS": "no",
    "MK_INET6": "yes",
    "MK_INET6_SUPPORT": "yes",
    "MK_ZFS": "no",
    "MK_TESTS": "no",
    "MK_MAN_UTILS": "yes",
    "LIBARCHIVE_VERSION_ONLY_STRING": "3.7.7",
    "VERSION": "6.7.6",
    "YYPATCH": "20230201",
}

VAR_REF_RE = re.compile(
    r"[$](?:[{]([A-Za-z0-9_.]+)(?::([^}]*))?[}]|[(]([A-Za-z0-9_.]+)(?::([^)]*))?[)])"
)
ASSIGN_RE = re.compile(f"^([A-Za-z0-9_.]+)[ {TAB}]*([?:+!]?=)[ {TAB}]*(.*)$")
INCLUDE_QUOTED_RE = re.compile(f"^[.][ {TAB}]*-?s?include[ {TAB}]+{DQUOTE}([^{DQUOTE}]+){DQUOTE}")
LINE_CONT_RE = re.compile(BS + BS + NL + f"[ {TAB}]*")
DEFINED_CALL_RE = re.compile(
    f"(!?)[ {TAB}]*defined[ {TAB}]*[(][ {TAB}]*([A-Za-z0-9_.]+)[ {TAB}]*[)]"
)
CMP_EXPR_RE = re.compile(f"^(.+?)[ {TAB}]*(==|!=)[ {TAB}]*{DQUOTE}?([^{DQUOTE}]*){DQUOTE}?$")
COND_LINE_RE = re.compile(f"^[.][ {TAB}]*(ifdef|ifndef|if|elif|else|endif)(?:$|[ {TAB}]+(.*))$")


@dataclasses.dataclass(frozen=True)
class UtilitySpec:
    """Normalized build specification for a top-level FreeBSD ``usr.bin`` entry.

    Attributes:
        name: Subdirectory name in ``usr.bin``.
        prog: Primary output program binary name.
        tier: Porting tier number (1 through 6).
        is_cxx: True if built from C++ sources (``PROG_CXX``).
        sources: Resolved source file paths.
        include_dirs: Resolved ``-I`` include directories.
        libs: Libraries listed in ``LIBADD``.
        links: Additional binary link names (e.g. ``more`` for ``less``).
        scripts: Installed shell/perl scripts in the directory.
    """

    name: str
    prog: str
    tier: int
    is_cxx: bool
    sources: tuple[str, ...]
    include_dirs: tuple[str, ...]
    libs: tuple[str, ...]
    links: tuple[str, ...]
    scripts: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class BinarySpec:
    """Concrete executable build specification for per-binary ``CMakeLists.txt`` emission.

    Attributes:
        prog: Output binary executable stem (e.g. ``bsdtar``, ``bspatch``, ``tic``).
        subdir: Originating ``usr.bin`` relative path (e.g. ``tar``, ``bsdiff/bspatch``).
        tier: Porting tier number (``1..6``).
        is_cxx: True when target requires a C++ compiler.
        sources: Resolved ``.c`` / ``.cc`` / ``.cpp`` source file paths.
        yacc_sources: Resolved ``.y`` grammar files requiring ``host_byacc``.
        lex_sources: Resolved ``.l`` scanner files requiring ``host_flex``.
        generated_headers: Per-utility build-time generated header file paths.
        include_dirs: Resolved ``-I`` include directory paths.
        compile_defs: Preprocessor ``-D`` macro definitions (``NAME`` or ``NAME=VAL``).
        raw_libs: Raw ``LIBADD`` library names from the FreeBSD ``Makefile``.
        section3_targets: Canonical ``fbsd_lib*`` Section 3 CMake library targets.
        links: Additional binary alias stems installed alongside ``prog``.
        scripts: Installed script filenames associated with the directory.
    """

    prog: str
    subdir: str
    tier: int
    is_cxx: bool
    sources: tuple[str, ...]
    yacc_sources: tuple[str, ...]
    lex_sources: tuple[str, ...]
    generated_headers: tuple[str, ...]
    include_dirs: tuple[str, ...]
    compile_defs: tuple[str, ...]
    raw_libs: tuple[str, ...]
    section3_targets: tuple[str, ...]
    links: tuple[str, ...]
    scripts: tuple[str, ...]


def locate_default_freebsd_src(repo_root: Path | None = None) -> Path:
    """Locate ``freebsd-src`` at ``../freebsd-src`` or ``./freebsd-src``.

    Args:
        repo_root: Optional repository root override (defaults to parent of ``scripts/``).

    Returns:
        Candidate ``freebsd-src`` ``Path`` (preferring an existing directory).
    """
    root = repo_root.resolve() if repo_root is not None else Path(__file__).resolve().parent.parent
    sibling = root.parent / "freebsd-src"
    nested = root / "freebsd-src"
    if nested.is_dir() and not sibling.is_dir():
        return nested
    return sibling


def map_libadd_to_section3_targets(raw_libs: Sequence[str]) -> tuple[str, ...]:
    """Map FreeBSD ``LIBADD`` tokens to deduplicated canonical Section 3 CMake targets.

    Args:
        raw_libs: Sequence of ``LIBADD`` tokens (e.g. ``("archive", "z", "pthread")``).

    Returns:
        Ordered deduplicated tuple of ``fbsd_lib*`` CMake target names.
    """
    mapped: list[str] = []
    for lib in raw_libs:
        target = LIBADD_TO_SECTION3_TARGET.get(lib, f"fbsd_lib{lib}")
        if target is not None and target not in mapped:
            mapped.append(target)
    return tuple(mapped)


def expand_makefile_vars(text: str, env: Mapping[str, str]) -> str:
    """Expand FreeBSD ``bmake`` ``${VAR}`` / ``$(VAR)`` and simple modifier expressions.

    Args:
        text: Raw Makefile value string containing ``${...}`` or ``$(...)`` references.
        env: Mapping of currently defined Makefile variables.

    Returns:
        String with known Makefile variables expanded.
    """
    current = text
    while True:
        changed = False
        for match in list(VAR_REF_RE.finditer(current)):
            var_name = match.group(1) or match.group(3)
            modifier = match.group(2) if match.group(1) is not None else match.group(4)
            if var_name in env:
                val = env[var_name]
                if modifier == "H":
                    val = str(Path(val).parent)
                elif modifier == "H:H":
                    val = str(Path(val).parent.parent)
                elif modifier == "T":
                    val = Path(val).name
                elif modifier == "tl":
                    val = val.lower()
                elif modifier == "tu":
                    val = val.upper()
                current = current.replace(match.group(0), val)
                changed = True
            elif modifier is not None and modifier.startswith("U"):
                current = current.replace(match.group(0), modifier[1:])
                changed = True
        if not changed:
            return current


def _eval_atomic_cond(atom: str, env: Mapping[str, str], *, is_ifdef: bool = False) -> bool:
    """Evaluate a single atomic ``bmake`` conditional clause.

    Args:
        atom: Trimmed atomic clause (without ``&&`` / ``||``).
        env: Active Makefile variable dictionary.
        is_ifdef: True if originating from ``.ifdef`` / ``.ifndef``.

    Returns:
        Boolean truth value for the atomic expression.
    """
    clause = atom.strip()
    while clause.startswith("(") and clause.endswith(")"):
        clause = clause[1:-1].strip()

    if is_ifdef:
        neg = clause.startswith("!")
        vname = clause[1:].strip() if neg else clause
        res = vname in env and bool(env[vname].strip())
        return (not res) if neg else res

    def_match = DEFINED_CALL_RE.fullmatch(clause)
    if def_match is not None:
        neg_flag = def_match.group(1) == "!"
        vname = def_match.group(2)
        is_def = vname in env and bool(env[vname].strip())
        return (not is_def) if neg_flag else is_def

    expanded = expand_makefile_vars(clause, env)
    cmp_match = CMP_EXPR_RE.match(expanded)
    if cmp_match is not None:
        lhs = cmp_match.group(1).strip().strip(DQUOTE)
        op = cmp_match.group(2)
        rhs = cmp_match.group(3).strip().strip(DQUOTE)
        if lhs.startswith("${"):
            return True
        return (lhs == rhs) if op == "==" else (lhs != rhs)

    if expanded.startswith("!"):
        inner = expanded[1:].strip()
        return not _eval_atomic_cond(inner, env)
    return bool(expanded and expanded != "0")


def evaluate_makefile_condition(
    directive: str,
    expr: str,
    env: Mapping[str, str],
) -> bool:
    """Evaluate a FreeBSD ``.if`` / ``.elif`` / ``.ifdef`` / ``.ifndef`` directive.

    Args:
        directive: Conditional keyword (``if``, ``elif``, ``ifdef``, ``ifndef``).
        expr: Raw conditional expression following the directive keyword.
        env: Active Makefile variable mapping.

    Returns:
        Boolean result determining whether lines in the branch are active.
    """
    cleaned = expr.split("#", 1)[0].strip()
    if directive in ("ifdef", "ifndef"):
        val = _eval_atomic_cond(cleaned, env, is_ifdef=True)
        return (not val) if directive == "ifndef" else val

    or_parts = [part.strip() for part in cleaned.split("||") if part.strip()]
    if not or_parts:
        return True
    for or_clause in or_parts:
        and_parts = [part.strip() for part in or_clause.split("&&") if part.strip()]
        if all(_eval_atomic_cond(atom, env) for atom in and_parts):
            return True
    return False


def parse_cflags_tokens(
    cflags_str: str,
    curdir: Path,
    env: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract ``-I`` include directories and ``-D`` defines from ``CFLAGS``.

    Args:
        cflags_str: Raw ``CFLAGS`` / ``CXXFLAGS`` value string.
        curdir: Utility ``${.CURDIR}`` for resolving relative ``-I`` paths.
        env: Makefile variable mapping for expanding ``${...}`` tokens.

    Returns:
        Tuple of ``(resolved_include_dirs, compile_defines)``.
    """
    expanded = expand_makefile_vars(cflags_str, env)
    tokens = expanded.split()
    inc_dirs: list[str] = []
    defines: list[str] = []
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok == "-I" and idx + 1 < len(tokens):
            raw_inc = tokens[idx + 1]
            idx += 2
        elif tok.startswith("-I") and len(tok) > 2:
            raw_inc = tok[2:]
            idx += 1
        elif tok.startswith("-D") and len(tok) > 2:
            macro = tok[2:].replace(BS + "'", "'").replace(BS + DQUOTE, DQUOTE)
            if not macro.startswith("$") and macro not in defines:
                defines.append(macro)
            idx += 1
            continue
        else:
            idx += 1
            continue

        if not raw_inc.startswith("$"):
            inc_p = Path(raw_inc)
            resolved = (curdir / inc_p).resolve() if not inc_p.is_absolute() else inc_p.resolve()
            resolved_str = str(resolved)
            if resolved_str not in inc_dirs:
                inc_dirs.append(resolved_str)

    return tuple(inc_dirs), tuple(defines)


def _handle_cond_directive(
    line: str,
    cond_stack: list[tuple[bool, bool, bool]],
    env: Mapping[str, str],
) -> bool:
    """Process a ``.if`` / ``.elif`` / ``.else`` / ``.endif`` line if matched.

    Args:
        line: Stripped Makefile line starting with ``.``.
        cond_stack: Mutable stack of ``(parent_active, branch_taken, current_active)``.
        env: Active Makefile variable dictionary.

    Returns:
        True if ``line`` was a conditional directive, False otherwise.
    """
    cond_m = COND_LINE_RE.match(line)
    if cond_m is None:
        return False
    kw = cond_m.group(1)
    rest = (cond_m.group(2) or "").strip()
    parent_active = cond_stack[-1][2] if cond_stack else True
    if kw in ("if", "ifdef", "ifndef"):
        take = parent_active and evaluate_makefile_condition(kw, rest, env)
        cond_stack.append((parent_active, take, take))
    elif kw == "elif" and cond_stack:
        p_act, taken, _ = cond_stack[-1]
        now = p_act and (not taken) and evaluate_makefile_condition("elif", rest, env)
        cond_stack[-1] = (p_act, taken or now, now)
    elif kw == "else" and cond_stack:
        p_act, taken, _ = cond_stack[-1]
        cond_stack[-1] = (p_act, True, p_act and (not taken))
    elif cond_stack:
        cond_stack.pop()
    return True


def parse_makefile_recursive(
    mk_path: Path,
    curdir: Path,
    env: dict[str, str],
    search_paths: list[Path],
    visited: set[Path] | None = None,
) -> None:
    """Recursively parse a FreeBSD ``Makefile`` with conditional block evaluation.

    Args:
        mk_path: Path to the Makefile to parse.
        curdir: Directory representing ``${.CURDIR}`` for the utility.
        env: Mutable dictionary of Makefile variables.
        search_paths: Mutable list of ``.PATH`` source search directories.
        visited: Optional set of already-visited resolved Makefile paths.
    """
    if visited is None:
        visited = set()
    mk_abs = mk_path.resolve()
    if mk_abs in visited or not mk_abs.is_file():
        return
    visited.add(mk_abs)
    env[".PARSEDIR"] = str(mk_abs.parent)

    raw_text = mk_abs.read_text(encoding="utf-8", errors="ignore")
    joined_text = LINE_CONT_RE.sub(" ", raw_text)

    # Stack of (parent_active, branch_taken, current_active)
    cond_stack: list[tuple[bool, bool, bool]] = []

    for raw_line in joined_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith(".") and _handle_cond_directive(line, cond_stack, env):
            continue

        if cond_stack and not cond_stack[-1][2]:
            continue

        inc_match = INCLUDE_QUOTED_RE.match(line)
        if inc_match is not None:
            inc_rel = expand_makefile_vars(inc_match.group(1), env)
            inc_path = Path(inc_rel)
            if not inc_path.is_absolute():
                cand_parse = mk_abs.parent / inc_rel
                cand_cur = curdir / inc_rel
                inc_path = cand_parse if cand_parse.is_file() else cand_cur
            parse_makefile_recursive(inc_path, curdir, env, search_paths, visited)
            env[".PARSEDIR"] = str(mk_abs.parent)
            continue

        if line.startswith(".PATH"):
            parts = line.split(":", 1)
            rhs = expand_makefile_vars(parts[1].strip(), env) if len(parts) > 1 else ""
            for token in rhs.split():
                if token.startswith("$"):
                    continue
                token_path = Path(token)
                resolved_p = (
                    (curdir / token_path).resolve()
                    if not token_path.is_absolute()
                    else token_path.resolve()
                )
                if resolved_p not in search_paths:
                    search_paths.append(resolved_p)
            continue

        assign_match = ASSIGN_RE.match(line)
        if assign_match is not None:
            key, op, raw_val = (
                assign_match.group(1),
                assign_match.group(2),
                assign_match.group(3).strip(),
            )
            if op == "!=":
                continue
            val = expand_makefile_vars(raw_val, env)
            if key in env and op == "+=":
                env[key] = f"{env[key]} {val}".strip()
            elif op == "?=" and key in env and env[key].strip():
                pass
            else:
                env[key] = val


def generate_fake_gperf_c(gperf_path: Path) -> str:
    """Convert a FreeBSD ``getconf`` ``.gperf`` file into C code (``fake-gperf.awk``).

    Args:
        gperf_path: Path to the input ``.gperf`` file.

    Returns:
        Generated C source code string defining ``wordlist[]`` and ``in_word_set()``.
    """
    state = 0
    struct_seen = ""
    out_lines: list[str] = []

    for raw_line in gperf_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.rstrip()
        if state == 0:
            if line == "%{":
                state = 1
            elif line.startswith("struct"):
                out_lines.append(line)
                tokens = line.split()
                struct_seen = tokens[1].rstrip(";") if len(tokens) > 1 else "map"
            elif line == "%%":
                state = 2
                if struct_seen:
                    out_lines.append(f"static const struct {struct_seen} wordlist[] = {{")
                else:
                    out_lines.extend(
                        [
                            "static const struct map {",
                            f"{TAB}const char *name;",
                            f"{TAB}int key;",
                            f"{TAB}int valid;",
                            "} wordlist[] = {",
                        ]
                    )
                    struct_seen = "map"
        elif state == 1:
            if line == "%}":
                state = 0
            else:
                out_lines.append(line)
        elif state == 2:
            if line == "%%":
                state = 3
                out_lines.extend(
                    [
                        f"{TAB}{{ NULL, 0, 0 }}",
                        "};",
                        "#include <sys/param.h>",
                        f"#define{TAB}NWORDS{TAB}(nitems(wordlist) - 1)",
                        "static const struct map *",
                        "in_word_set(const char *word)",
                        "{",
                        f"{TAB}const struct {struct_seen} *mp;",
                        "",
                        f"{TAB}for (mp = wordlist; mp < &wordlist[NWORDS]; mp++) {{",
                        f"{TAB}{TAB}if (strcmp(word, mp->name) == 0)",
                        f"{TAB}{TAB}{TAB}return (mp);",
                        f"{TAB}}}",
                        f"{TAB}return (NULL);",
                        "}",
                        "",
                    ]
                )
            else:
                fields = line.split()
                if len(fields) == 2:
                    name = fields[0].rstrip(",")
                    sym = fields[1]
                    out_lines.extend(
                        [
                            f"#ifdef {sym}",
                            f'{TAB}{{ "{name}", {sym}, 1 }},',
                            "#else",
                            f'{TAB}{{ "{name}", 0, 0 }},',
                            "#endif",
                        ]
                    )
        else:
            out_lines.append(line)

    return NL.join(out_lines) + NL


def generate_netstat_nlist(nlist_symbols_path: Path) -> tuple[str, str]:
    """Generate ``nl_symbols.c`` and ``nl_defs.h`` from ``usr.bin/netstat/nlist_symbols``.

    Args:
        nlist_symbols_path: Path to ``usr.bin/netstat/nlist_symbols``.

    Returns:
        Tuple of ``(nl_symbols_c_text, nl_defs_h_text)``.
    """
    c_lines = [
        "#include <sys/param.h>",
        "#include <nlist.h>",
        "struct nlist nl[] = {",
    ]
    h_lines = [
        "#include <nlist.h>",
        "extern struct nlist nl[];",
    ]
    idx = 0
    for raw_line in nlist_symbols_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 2:
            sym = fields[1]
            c_lines.append(f'{TAB}{{ .n_name = "{sym}" }},')
            h_lines.append(f"#define{TAB}N_{sym.upper()}{TAB}{idx}")
            idx += 1
    c_lines.extend([f"{TAB}{{ .n_name = NULL }},", "};", ""])
    h_lines.append("")
    return NL.join(c_lines), NL.join(h_lines)


def generate_bc_strgen_c(
    input_path: Path,
    name: str,
    label: str = "",
    define: str = "",
    *,
    remove_tabs: bool = False,
) -> str:
    """Generate a C string array file for ``gh-bc`` (pure-Python ``strgen.sh``).

    Args:
        input_path: Path to input ``.bc`` or ``.txt`` file.
        name: C identifier for the ``const char[]`` array.
        label: Optional C identifier for the filename ``const char *`` pointer.
        define: Optional preprocessor ``#if`` guard expression.
        remove_tabs: Whether to strip tab characters from input lines.

    Returns:
        Generated C source file content.
    """
    raw_lines = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    body_start = 0
    for idx, line in enumerate(raw_lines):
        if line == "":
            body_start = idx + 1
            break
    body_lines = raw_lines[body_start:]

    out_lines = [
        f"/* AUTOMATICALLY GENERATED FROM {input_path.name}. DO NOT MODIFY. */",
    ]
    if define:
        out_lines.append(f"#if {define}")
    if label:
        out_lines.append(f"extern const char *{label};")
    out_lines.append(f"extern const char {name}[];")
    if label:
        out_lines.append(f'const char *{label} = "{input_path.name}";')
    out_lines.append(f"const char {name}[] =")
    for line in body_lines:
        processed = line.replace(TAB, "") if remove_tabs else line
        escaped = processed.replace(BS, BS + BS).replace(DQUOTE, BS + DQUOTE)
        out_lines.append(f'"{escaped}{BS}n"')
    if not body_lines:
        out_lines.append('""')
    out_lines.append(";")
    if define:
        out_lines.append("#endif")
    out_lines.append("")
    return NL.join(out_lines)


def generate_dispatcher_c(applet_name: str) -> str:
    """Generate functional C89 source for a script or fallback directory.

    Delegates known Tier 6 script/driver names to ``generate_script_applet_c``
    and emits a valid C89 ``main`` wrapper for any unknown synthetic directory.

    Args:
        applet_name: Name of the ``usr.bin`` script or container utility.

    Returns:
        Valid C89 source code implementing ``main(int argc, char *argv[])``.
    """
    if applet_name in SCRIPT_AND_SPECIAL_DIRS:
        return generate_script_applet_c(applet_name)
    return NL.join(
        [
            "#include <stdio.h>",
            "#include <string.h>",
            "",
            "int main(int argc, char *argv[]) {",
            f'    const char *prog = "{applet_name}";',
            '    if (argc > 1 && (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0)) {',
            f'        printf("usage: %s [args...]{BS}n", prog);',
            "    }",
            "    return 0;",
            "}",
            "",
        ]
    )


def stage_build_time_generated_files(
    freebsd_src: Path,
    generated_dir: Path,
    patches_dir: Path | None = None,
) -> dict[str, Path]:
    """Emit all build-time generated C/H files and staged patches into ``generated_dir``.

    Args:
        freebsd_src: Path to ``../freebsd-src``.
        generated_dir: Destination directory (e.g. ``build/freebsd_generated``).
        patches_dir: Optional ``patches/`` directory containing ``.patch`` files.

    Returns:
        Dictionary mapping logical relative keys to generated file ``Path``s.
    """
    generated_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    if patches_dir is not None and patches_dir.is_dir():
        staged_map = stage_patched_sources(
            freebsd_src,
            patches_dir,
            generated_dir / "staged_src",
        )
        for orig_p, staged_p in staged_map.items():
            emitted[f"staged_src/{orig_p.name}"] = staged_p

    getconf_src = freebsd_src / "usr.bin" / "getconf"
    if getconf_src.is_dir():
        getconf_out = generated_dir / "getconf"
        getconf_out.mkdir(parents=True, exist_ok=True)
        for gperf_file in sorted(getconf_src.glob("*.gperf")):
            c_out = getconf_out / f"{gperf_file.stem}.c"
            c_out.write_text(generate_fake_gperf_c(gperf_file), encoding="utf-8")
            emitted[f"getconf/{c_out.name}"] = c_out

    nlist_sym_path = freebsd_src / "usr.bin" / "netstat" / "nlist_symbols"
    if nlist_sym_path.is_file():
        netstat_out = generated_dir / "netstat"
        netstat_out.mkdir(parents=True, exist_ok=True)
        nl_c, nl_h = generate_netstat_nlist(nlist_sym_path)
        c_path = netstat_out / "nl_symbols.c"
        h_path = netstat_out / "nl_defs.h"
        c_path.write_text(nl_c, encoding="utf-8")
        h_path.write_text(nl_h, encoding="utf-8")
        emitted["netstat/nl_symbols.c"] = c_path
        emitted["netstat/nl_defs.h"] = h_path

    bc_gen_dir = freebsd_src / "contrib" / "bc" / "gen"
    if bc_gen_dir.is_dir():
        bc_out = generated_dir / "gh-bc"
        bc_out.mkdir(parents=True, exist_ok=True)
        specs = [
            ("lib.bc", "lib.c", "bc_lib", "bc_lib_name", "", True),
            ("lib2.bc", "lib2.c", "bc_lib2", "bc_lib2_name", "BC_ENABLE_EXTRA_MATH", True),
            ("bc_help.txt", "bc_help.c", "bc_help", "", "BC_ENABLED", False),
            ("dc_help.txt", "dc_help.c", "dc_help", "", "DC_ENABLED", False),
        ]
        for in_name, out_name, arr_name, lbl, guard, rm_tabs in specs:
            in_file = bc_gen_dir / in_name
            if in_file.is_file():
                out_file = bc_out / out_name
                out_file.write_text(
                    generate_bc_strgen_c(in_file, arr_name, lbl, guard, remove_tabs=rm_tabs),
                    encoding="utf-8",
                )
                emitted[f"gh-bc/{out_name}"] = out_file

    lex_src = freebsd_src / "usr.bin" / "lex"
    if lex_src.is_dir():
        lex_out = generated_dir / "lex"
        lex_out.mkdir(parents=True, exist_ok=True)
        for base in ("parse.c", "parse.h", "scan.c", "skel.c"):
            init_file = lex_src / f"init{base}"
            if init_file.is_file():
                dst = lex_out / base
                shutil.copyfile(init_file, dst)
                emitted[f"lex/{base}"] = dst

    less_defs = freebsd_src / "usr.bin" / "less" / "defines.h"
    if less_defs.is_file():
        less_out = generated_dir / "less"
        less_out.mkdir(parents=True, exist_ok=True)
        dst = less_out / "defines.h"
        win_less_tail = "\n".join(
            [
                "",
                "#ifdef _WIN32",
                "#undef HAVE_TERMIOS_FUNCS",
                "#define HAVE_TERMIOS_FUNCS 0",
                "#undef HAVE_OSPEED",
                "#define HAVE_OSPEED 0",
                "#undef HAVE_FDATASYNC",
                "#define HAVE_FDATASYNC 0",
                "#endif",
                "",
            ]
        )
        dst.write_text(
            "#include <termios.h>\n"
            + less_defs.read_text(encoding="utf-8", errors="ignore")
            + win_less_tail,
            encoding="utf-8",
        )
        emitted["less/defines.h"] = dst

    tnftp_cfg = freebsd_src / "usr.bin" / "ftp" / "tnftp_config.h"
    if tnftp_cfg.is_file():
        ftp_out = generated_dir / "ftp"
        ftp_out.mkdir(parents=True, exist_ok=True)
        ftp_dst = ftp_out / "tnftp_config.h"
        ftp_tail = "\n".join(
            [
                "",
                "#if !defined(__FreeBSD__) && !defined(__APPLE__)",
                "#undef HAVE_STRUCT_SOCKADDR_IN_SIN_LEN",
                "#endif",
                "",
            ]
        )
        ftp_dst.write_text(
            tnftp_cfg.read_text(encoding="utf-8", errors="ignore") + ftp_tail,
            encoding="utf-8",
        )
        emitted["ftp/tnftp_config.h"] = ftp_dst

    emitted.update(emit_all_codegen_helpers(freebsd_src, generated_dir))
    emitted.update(emit_all_script_applets(generated_dir))

    return emitted


def classify_tier(
    name: str,
    has_prog: bool,
    libs: Sequence[str],
    search_paths: Sequence[Path],
    freebsd_src: Path,
) -> int:
    """Classify a ``usr.bin`` directory into one of the 6 porting tiers.

    Args:
        name: Directory name in ``usr.bin``.
        has_prog: Whether the directory directly defines ``PROG``/``PROGS``/``PROG_CXX``.
        libs: Libraries listed in ``LIBADD``.
        search_paths: Resolved ``.PATH`` directories.
        freebsd_src: Root path of ``freebsd-src``.

    Returns:
        Integer tier number in ``1..6``.
    """
    if not has_prog or name in SCRIPT_AND_SPECIAL_DIRS or name in MULTI_BINARY_CONTAINERS:
        return 6
    contrib_root = str((freebsd_src / "contrib").resolve())
    sys_contrib_root = str((freebsd_src / "sys" / "contrib").resolve())
    for sp in search_paths:
        sp_str = str(sp.resolve())
        if sp_str.startswith(contrib_root) or sp_str.startswith(sys_contrib_root):
            return 4
    if any(lib in SYS_KERNEL_LIBS for lib in libs):
        return 5
    if any(lib in CURSES_TUI_LIBS for lib in libs):
        return 3
    if any(lib in BSD_SHIM_LIBS for lib in libs):
        return 2
    return 1


def resolve_sources_for_prog(
    raw_srcs: Sequence[str],
    search_paths: Sequence[Path],
    generated_subdir: Path | None,
    *,
    is_cxx: bool = False,
    staged_map: Mapping[Path, Path] | None = None,
) -> tuple[str, ...]:
    """Resolve source filenames across ``.PATH``, ``generated_subdir``, and ``staged_map``.

    Args:
        raw_srcs: List of source filenames from ``SRCS``.
        search_paths: Ordered list of ``.PATH`` directories to search.
        generated_subdir: Optional generated files directory for this utility.
        is_cxx: Whether the target is a C++ program.
        staged_map: Optional mapping from upstream ``freebsd_src`` path to staged patched copy.

    Returns:
        Tuple of resolved absolute path strings.
    """
    resolved: list[str] = []
    search_list = list(search_paths)
    if generated_subdir is not None and generated_subdir.is_dir():
        search_list.insert(0, generated_subdir.resolve())

    for src_token in raw_srcs:
        if src_token.startswith("$") or src_token.endswith(".h"):
            continue
        found_path: Path | None = None
        for sp in search_list:
            cand = sp / src_token
            if cand.is_file():
                found_path = cand.resolve()
                break
            stem = Path(src_token).stem
            alt_exts = (".cc", ".cpp", ".cxx", ".y", ".l") if is_cxx else (".y", ".l", ".cc")
            for ext in alt_exts:
                alt_cand = sp / f"{stem}{ext}"
                if alt_cand.is_file():
                    found_path = alt_cand.resolve()
                    break
            if found_path is not None:
                break
        if found_path is not None:
            if staged_map is not None and found_path in staged_map:
                found_path = staged_map[found_path]
            resolved.append(str(found_path))
    return tuple(resolved)


def _split_resolved_sources(
    all_resolved: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Partition resolved paths into C/C++ sources, ``.y`` grammars, and ``.l`` scanners.

    Args:
        all_resolved: Resolved source file path strings.

    Returns:
        Tuple of ``(c_or_cxx_sources, yacc_sources, lex_sources)``.
    """
    c_srcs: list[str] = []
    y_srcs: list[str] = []
    l_srcs: list[str] = []
    for p_str in all_resolved:
        if p_str.endswith(".y"):
            y_srcs.append(p_str)
        elif p_str.endswith(".l"):
            l_srcs.append(p_str)
        else:
            c_srcs.append(p_str)
    return tuple(c_srcs), tuple(y_srcs), tuple(l_srcs)


def _parse_single_makefile_dir(
    curdir: Path,
    rel_subdir: str,
    srctop: Path,
    generated_dir: Path,
    staged_map: Mapping[Path, Path] | None = None,
    *,
    enable_heavy_subtrees: bool = False,
) -> list[BinarySpec]:
    """Parse one ``Makefile`` directory into zero, one, or multiple ``BinarySpec`` items.

    Args:
        curdir: Directory containing ``Makefile``.
        rel_subdir: Relative path under ``usr.bin`` (e.g. ``ncurses`` or ``bsdiff/bspatch``).
        srctop: Resolved ``freebsd-src`` root directory.
        generated_dir: Out-of-tree ``freebsd_generated`` directory.
        staged_map: Optional map of upstream paths to patched copies.
        enable_heavy_subtrees: Whether to expand full C++ sources for ``clang``/``kyua``/``ofed``.

    Returns:
        List of ``BinarySpec`` objects defined by ``curdir/Makefile``.
    """
    mk_path = curdir / "Makefile"
    if not mk_path.is_file() or (
        rel_subdir in ("clang", "kyua", "ofed") and not enable_heavy_subtrees
    ):
        disp_c = (generated_dir / "dispatchers" / f"{curdir.name}_main.c").resolve()
        if not disp_c.is_file():
            disp_c.parent.mkdir(parents=True, exist_ok=True)
            disp_c.write_text(generate_dispatcher_c(curdir.name), encoding="utf-8")
        return [
            BinarySpec(
                prog=curdir.name,
                subdir=rel_subdir,
                tier=6,
                is_cxx=False,
                sources=(str(disp_c),),
                yacc_sources=(),
                lex_sources=(),
                generated_headers=(),
                include_dirs=(str(curdir),),
                compile_defs=(),
                raw_libs=(),
                section3_targets=(),
                links=(),
                scripts=(),
            )
        ]

    env = dict(DEFAULT_MK_ENV)
    env["SRCTOP"] = str(srctop)
    env["OBJTOP"] = str(generated_dir.resolve())
    env[".CURDIR"] = str(curdir)
    env[".OBJDIR"] = str((generated_dir / rel_subdir).resolve())

    search_paths: list[Path] = [curdir]
    parent_inc = curdir.parent / "Makefile.inc"
    if curdir.parent != (srctop / "usr.bin").resolve() and parent_inc.is_file():
        parse_makefile_recursive(parent_inc, curdir, env, search_paths)
    inc_mk = curdir / "Makefile.inc"
    if inc_mk.is_file():
        parse_makefile_recursive(inc_mk, curdir, env, search_paths)
    parse_makefile_recursive(mk_path, curdir, env, search_paths)

    prog_cxx = env.get("PROG_CXX", "").strip()
    prog_c = env.get("PROG", "").strip()
    progs_c = env.get("PROGS", "").split()
    progs_cxx = env.get("PROGS_CXX", "").split()

    prog_entries: list[tuple[str, bool]] = []
    if prog_cxx:
        prog_entries.append((prog_cxx, True))
    elif prog_c:
        prog_entries.append((prog_c, False))
    elif progs_c or progs_cxx:
        for p in progs_c:
            prog_entries.append((p, False))
        for p in progs_cxx:
            prog_entries.append((p, True))

    scripts = tuple(tok for tok in env.get("SCRIPTS", "").split() if not tok.startswith("$"))
    if not prog_entries:
        if rel_subdir in SCRIPT_AND_SPECIAL_DIRS:
            disp_c = (generated_dir / "dispatchers" / f"{rel_subdir}_main.c").resolve()
            return [
                BinarySpec(
                    prog=rel_subdir,
                    subdir=rel_subdir,
                    tier=6,
                    is_cxx=False,
                    sources=(str(disp_c),),
                    yacc_sources=(),
                    lex_sources=(),
                    generated_headers=(),
                    include_dirs=(str(curdir),),
                    compile_defs=(),
                    raw_libs=(),
                    section3_targets=(),
                    links=(),
                    scripts=scripts,
                )
            ]
        return []

    base_libs = [tok for tok in env.get("LIBADD", "").split() if not tok.startswith("$")]
    base_cflags = f"{env.get('CFLAGS', '')} {env.get('CXXFLAGS', '')}".strip()
    gen_sub = generated_dir / rel_subdir

    out_specs: list[BinarySpec] = []
    for prog_name, is_cxx in prog_entries:
        prog_libs_raw = base_libs + [
            tok for tok in env.get(f"LIBADD.{prog_name}", "").split() if not tok.startswith("$")
        ]
        dedup_libs = tuple(dict.fromkeys(prog_libs_raw))
        s3_targets = map_libadd_to_section3_targets(dedup_libs)

        combined_cflags = f"{base_cflags} {env.get(f'CFLAGS.{prog_name}', '')}".strip()
        cflags_incs, compile_defs = parse_cflags_tokens(combined_cflags, curdir, env)

        links_str = (
            f"{env.get('LINKS', '')} {env.get(f'LINKS.{prog_name}', '')} "
            f"{env.get('SYMLINKS', '')} {env.get(f'SYMLINKS.{prog_name}', '')}"
        ).strip()
        links_list: list[str] = []
        progname_override = env.get("PROGNAME", "").strip()
        if (
            len(prog_entries) == 1
            and progname_override
            and not progname_override.startswith("$")
            and progname_override != prog_name
        ):
            links_list.append(progname_override)
        raw_link_toks = links_str.split()
        for pair_idx in range(0, len(raw_link_toks) - 1, 2):
            src_tok = raw_link_toks[pair_idx]
            dst_tok = raw_link_toks[pair_idx + 1]
            valid_tokens = not (src_tok.startswith("$") or dst_tok.startswith("$"))
            matches_prog = len(prog_entries) == 1 or Path(src_tok).name == prog_name
            alias_name = Path(dst_tok).name
            if (
                valid_tokens
                and matches_prog
                and alias_name != prog_name
                and alias_name not in links_list
            ):
                links_list.append(alias_name)

        default_ext = ".cc" if is_cxx else ".c"
        if f"SRCS.{prog_name}" in env:
            raw_srcs = env[f"SRCS.{prog_name}"].split()
        elif "SRCS" in env and len(prog_entries) == 1:
            raw_srcs = env["SRCS"].split()
        else:
            raw_srcs = [f"{prog_name}{default_ext}"]

        gen_hdrs = tuple(tok for tok in raw_srcs if tok.endswith(".h") and not tok.startswith("$"))
        resolved_all = resolve_sources_for_prog(
            raw_srcs,
            search_paths,
            gen_sub,
            is_cxx=is_cxx,
            staged_map=staged_map,
        )
        c_srcs, y_srcs, l_srcs = _split_resolved_sources(resolved_all)

        inc_dirs: list[str] = [str(curdir)]
        staged_curdir = (generated_dir / "staged_src" / "usr.bin" / rel_subdir).resolve()
        if staged_curdir.is_dir():
            inc_dirs.insert(0, str(staged_curdir))
        if gen_sub.is_dir():
            inc_dirs.insert(0, str(gen_sub.resolve()))
        cg_base = (generated_dir / "codegen").resolve()
        extra_defs = list(compile_defs)
        if prog_name in ("bsdcat", "bsdcpio", "bsdtar", "bsdunzip"):
            inc_dirs.insert(0, str(cg_base / "libarchive"))
            extra_defs = [d for d in extra_defs if not d.startswith("PLATFORM_CONFIG_H")]
            extra_defs.append('PLATFORM_CONFIG_H="config.h"')
        if "fbsd_libldns" in s3_targets:
            inc_dirs.insert(0, str(cg_base / "ldns" / "ldns"))
            inc_dirs.insert(0, str(cg_base / "ldns"))
        if "fbsd_libelftc" in s3_targets and prog_name not in ("ldd", "ldd32"):
            inc_dirs.insert(0, str(cg_base / "elftoolchain"))
        elif prog_name in ("brandelf", "elfdump"):
            inc_dirs.insert(0, str(cg_base / "elftoolchain"))
        if prog_name == "ldd32":
            extra_defs.append("__ELF_WORD_SIZE=32")
        if prog_name == "compile_et":
            inc_dirs.insert(0, str(cg_base / "compile_et"))
        if prog_name == "mt":
            libmt_dir = (srctop / "lib" / "libmt").resolve()
            libmt_c = libmt_dir / "mtlib.c"
            inc_dirs.insert(0, str(libmt_dir))
            if libmt_c.is_file():
                c_srcs = tuple(dict.fromkeys([*c_srcs, str(libmt_c)]))
            s3_targets = tuple(dict.fromkeys([*s3_targets, "fbsd_libbsdxml", "fbsd_libsbuf"]))
        if prog_name == "chpass":
            c_srcs = tuple(s for s in c_srcs if not s.endswith("/pw_scan.c"))
        if prog_name == "mandoc":
            c_srcs = tuple(s for s in c_srcs if not s.endswith("/compat_recallocarray.c"))
        if prog_name == "vacation":
            vac_dir = cg_base / "vacation"
            vac_sm_c = (vac_dir / "fbsd_vacation_sm.c").resolve()
            inc_dirs.insert(0, str(vac_dir))
            if vac_sm_c.is_file():
                c_srcs = tuple(dict.fromkeys([*c_srcs, str(vac_sm_c)]))
        if prog_name == "mkimg":
            extra_defs.append("FBSD_SKIP_PREINCLUDE_ENDIAN=1")
        if prog_name in ("showmount", "gprof"):
            extra_defs.append("FBSD_SKIP_PREINCLUDE_STDBOOL=1")
        if prog_name == "telnet":
            extra_defs.extend(["__APPLE_USE_RFC_3542=1", "FBSD_TELNET_BUILD=1"])
        if prog_name == "tip":
            extra_defs.append("FBSD_TIP_BUILD=1")
        if prog_name == "mail":
            extra_defs.append("FBSD_MAIL_BUILD=1")
        if prog_name in ("nvi", "script", "rfcomm_sppd"):
            extra_defs.append("FBSD_NVI_BUILD=1")
        if prog_name in ("limits", "procstat"):
            extra_defs.append("FBSD_FREEBSD_RLIMITS=1")
        if prog_name == "posixmqcontrol":
            extra_defs.append("FBSD_POSIXMQ_BUILD=1")
        if prog_name in ("ypcat", "ypwhich"):
            inc_dirs.insert(0, str(cg_base / "libsys"))
            s3_targets = tuple(dict.fromkeys([*s3_targets, "fbsd_libsys"]))
        if prog_name == "getaddrinfo":
            inc_dirs.insert(0, str(cg_base / "getaddrinfo"))
        if prog_name == "nvi":
            inc_dirs.insert(0, str(cg_base / "vi"))
        if prog_name == "xz":
            inc_dirs.insert(0, str(cg_base / "liblzma"))
        if prog_name == "file":
            inc_dirs.insert(0, str(cg_base / "libmagic"))
        if prog_name == "xopo":
            inc_dirs.insert(0, str((srctop / "lib" / "libxo" / "libxo").resolve()))
        if prog_name == "col":
            extra_defs.append("FBSD_COL_BUILD=1")
        if prog_name == "join":
            extra_defs.append("FBSD_JOIN_BUILD=1")
        if prog_name in ("tr", "fortune", "gprof", "less", "lessecho", "lesskey", "talk"):
            extra_defs.append("FBSD_UNDEF_WIN32_DELETE=1")
        if prog_name == "lesskey" and (generated_dir / "less").is_dir():
            inc_dirs.insert(0, str((generated_dir / "less").resolve()))
        if prog_name == "dpv" and (cg_base / "libdpv").is_dir():
            inc_dirs.insert(0, str((cg_base / "libdpv").resolve()))
        if prog_name == "sed":
            extra_defs.append("FBSD_SED_BUILD=1")
        if prog_name == "bsddialog":
            extra_defs.append("FBSD_BSDDIALOG_BUILD=1")
        if prog_name == "bsdcpio":
            extra_defs.append("FBSD_BSDCPIO_BUILD=1")
        if prog_name == "top":
            extra_defs.append("FBSD_TOP_BUILD=1")
        if rel_subdir == "ncurses" and prog_name in (
            "clear",
            "infocmp",
            "tic",
            "toe",
            "tput",
            "tset",
        ):
            nc_prog_c = (cg_base / "ncurses_progs" / f"{prog_name}.c").resolve()
            if nc_prog_c.is_file():
                c_srcs = (str(nc_prog_c),)
                y_srcs = ()
                l_srcs = ()
        if prog_name in KERNEL_STAT_PROGS:
            kstat_c = (cg_base / "kernel_stat" / f"{prog_name}.c").resolve()
            if kstat_c.is_file():
                c_srcs = (str(kstat_c),)
                y_srcs = ()
                l_srcs = ()
        if prog_name == "w":
            extra_defs.append("FBSD_W_BUILD=1")
        if prog_name == "ftp":
            extra_defs.append("FBSD_FTP_BUILD=1")
        if prog_name == "localedef":
            extra_defs.extend(["FBSD_LOCALEDEF_BUILD=1", "COLL_WEIGHTS_MAX=10"])
            staged_boot = (
                generated_dir / "staged_src" / "usr.bin" / "localedef" / "bootstrap"
            ).resolve()
            if staged_boot.is_dir():
                inc_dirs.insert(0, str(staged_boot))
        if prog_name == "nc":
            extra_defs.append("AUTO_WIN_MSVC_NO_FUNCTION_MACROS=1")
        if prog_name == "file":
            extra_defs.append("FBSD_LIBMAGIC_BUILD=1")
        if prog_name == "grep":
            for cdir in (
                srctop / "contrib" / "bzip2",
                srctop / "sys" / "contrib" / "zlib",
                srctop / "contrib" / "xz" / "src" / "liblzma" / "api",
                srctop / "sys" / "contrib" / "zstd" / "lib",
            ):
                if cdir.is_dir():
                    inc_dirs.append(str(cdir.resolve()))
        kernel_sys_dir = str((srctop / "sys").resolve())
        for extra_inc in cflags_incs:
            if (
                extra_inc not in inc_dirs
                and extra_inc != kernel_sys_dir
                and not (prog_name == "wg" and extra_inc.endswith("wireguard-tools"))
            ):
                inc_dirs.append(extra_inc)
        for sp in search_paths:
            sp_str = str(sp)
            if (
                sp_str not in inc_dirs
                and sp_str != kernel_sys_dir
                and not (prog_name == "wg" and sp_str.endswith("wireguard-tools"))
            ):
                inc_dirs.append(sp_str)

        top_name = rel_subdir.split("/", 1)[0]
        tier = classify_tier(top_name, True, dedup_libs, search_paths, srctop)
        out_specs.append(
            BinarySpec(
                prog=prog_name,
                subdir=rel_subdir,
                tier=tier,
                is_cxx=is_cxx,
                sources=c_srcs,
                yacc_sources=y_srcs,
                lex_sources=l_srcs,
                generated_headers=gen_hdrs,
                include_dirs=tuple(inc_dirs),
                compile_defs=tuple(dict.fromkeys(extra_defs)),
                raw_libs=dedup_libs,
                section3_targets=s3_targets,
                links=tuple(links_list),
                scripts=scripts,
            )
        )

    return out_specs


def audit_freebsd_usr_bin_binaries(
    freebsd_src: Path,
    generated_dir: Path,
    patches_dir: Path | None = None,
    heavy_subtrees: frozenset[str] = frozenset(),
) -> tuple[list[str], list[UtilitySpec], list[BinarySpec]]:
    """Audit all 280 ``usr.bin`` entries and expand concrete ``BinarySpec`` targets.

    Args:
        freebsd_src: Path to ``../freebsd-src`` (or ``./freebsd-src``).
        generated_dir: Out-of-tree ``freebsd_generated`` directory.
        patches_dir: Optional directory containing ``.patch`` files.
        heavy_subtrees: Optional set of heavy subtrees (``clang``, ``ofed``,
            ``kyua``) enabled for full upstream Makefile expansion.

    Returns:
        Tuple of ``(top_makefiles, utility_specs, binary_specs)``.

    Raises:
        FreeBsdPortError: If ``freebsd_src/usr.bin`` does not exist.
    """
    srctop = freebsd_src.resolve()
    usr_bin = srctop / "usr.bin"
    if not usr_bin.is_dir():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            f"FreeBSD usr.bin directory not found: {usr_bin}",
            path=usr_bin,
        )

    stage_build_time_generated_files(srctop, generated_dir, patches_dir=patches_dir)
    staged_map = (
        stage_patched_sources(srctop, patches_dir, generated_dir / "staged_src")
        if patches_dir is not None and patches_dir.is_dir()
        else None
    )

    all_entries = sorted(os.listdir(usr_bin))
    top_mks = [e for e in all_entries if not (usr_bin / e).is_dir()]
    subdirs = [e for e in all_entries if (usr_bin / e).is_dir()]

    utility_specs: list[UtilitySpec] = []
    raw_binaries: list[BinarySpec] = []

    for d_name in subdirs:
        curdir = (usr_bin / d_name).resolve()
        if d_name in MULTI_BINARY_CONTAINERS:
            sub_bins: list[BinarySpec] = []
            for child_name in sorted(os.listdir(curdir)):
                child_dir = (curdir / child_name).resolve()
                if child_dir.is_dir() and (child_dir / "Makefile").is_file():
                    sub_bins.extend(
                        _parse_single_makefile_dir(
                            child_dir,
                            f"{d_name}/{child_name}",
                            srctop,
                            generated_dir,
                            staged_map=staged_map,
                        )
                    )
            raw_binaries.extend(sub_bins)
            merged_srcs: list[str] = []
            merged_incs: list[str] = [str(curdir)]
            merged_libs: list[str] = []
            merged_links: list[str] = []
            for sb in sub_bins:
                for s in (*sb.sources, *sb.yacc_sources, *sb.lex_sources):
                    if s not in merged_srcs:
                        merged_srcs.append(s)
                for inc in sb.include_dirs:
                    if inc not in merged_incs:
                        merged_incs.append(inc)
                for lib in sb.raw_libs:
                    if lib not in merged_libs:
                        merged_libs.append(lib)
                for lnk in sb.links:
                    if lnk not in merged_links:
                        merged_links.append(lnk)
            primary_prog = sub_bins[0].prog if sub_bins else d_name
            utility_specs.append(
                UtilitySpec(
                    name=d_name,
                    prog=primary_prog,
                    tier=6,
                    is_cxx=any(sb.is_cxx for sb in sub_bins),
                    sources=tuple(merged_srcs),
                    include_dirs=tuple(merged_incs),
                    libs=tuple(merged_libs),
                    links=tuple(merged_links),
                    scripts=(),
                )
            )
            continue

        dir_bins = _parse_single_makefile_dir(
            curdir,
            d_name,
            srctop,
            generated_dir,
            staged_map=staged_map,
            enable_heavy_subtrees=(d_name in heavy_subtrees),
        )
        raw_binaries.extend(dir_bins)
        if dir_bins:
            first = dir_bins[0]
            all_dir_srcs = tuple(
                dict.fromkeys([*first.sources, *first.yacc_sources, *first.lex_sources])
            )
            utility_specs.append(
                UtilitySpec(
                    name=d_name,
                    prog=first.prog,
                    tier=first.tier,
                    is_cxx=first.is_cxx,
                    sources=all_dir_srcs,
                    include_dirs=first.include_dirs,
                    libs=first.raw_libs,
                    links=first.links,
                    scripts=first.scripts,
                )
            )
        else:
            disp_c = (generated_dir / "dispatchers" / f"{d_name}_main.c").resolve()
            if not disp_c.is_file():
                disp_c.parent.mkdir(parents=True, exist_ok=True)
                disp_c.write_text(generate_dispatcher_c(d_name), encoding="utf-8")
            fallback_bin = BinarySpec(
                prog=d_name,
                subdir=d_name,
                tier=6,
                is_cxx=False,
                sources=(str(disp_c),),
                yacc_sources=(),
                lex_sources=(),
                generated_headers=(),
                include_dirs=(str(curdir),),
                compile_defs=(),
                raw_libs=(),
                section3_targets=(),
                links=(),
                scripts=(),
            )
            raw_binaries.append(fallback_bin)
            utility_specs.append(
                UtilitySpec(
                    name=d_name,
                    prog=d_name,
                    tier=6,
                    is_cxx=False,
                    sources=(str(disp_c),),
                    include_dirs=(str(curdir),),
                    libs=(),
                    links=(),
                    scripts=(),
                )
            )

    # Deduplicate BinarySpec by prog, preferring dedicated usr.bin/<prog> directories
    by_prog: dict[str, BinarySpec] = {}
    for bspec in raw_binaries:
        existing = by_prog.get(bspec.prog)
        if existing is None or bspec.subdir == bspec.prog:
            by_prog[bspec.prog] = bspec
    dedup_binaries = [by_prog[k] for k in sorted(by_prog)]

    return top_mks, utility_specs, dedup_binaries


def audit_freebsd_usr_bin(
    freebsd_src: Path,
    generated_dir: Path,
) -> tuple[list[str], list[UtilitySpec]]:
    """Audit all 280 entries in ``../freebsd-src/usr.bin`` and build ``UtilitySpec``s.

    Args:
        freebsd_src: Path to ``../freebsd-src``.
        generated_dir: Path to out-of-tree generated files directory.

    Returns:
        Tuple of ``(top_makefiles, utility_specs)``.
    """
    top_mks, utility_specs, _ = audit_freebsd_usr_bin_binaries(freebsd_src, generated_dir)
    return top_mks, utility_specs


def write_manifest_files(
    top_makefiles: Sequence[str],
    specs: Sequence[UtilitySpec],
    generated_dir: Path,
    binaries: Sequence[BinarySpec] = (),
) -> tuple[Path, Path]:
    """Write ``freebsd_usr_bin_manifest.json`` and ``freebsd_usr_bin_targets.cmake``.

    Args:
        top_makefiles: Top-level Makefile filenames in ``usr.bin``.
        specs: Sequence of parsed ``UtilitySpec`` instances.
        generated_dir: Output directory for the manifest files.
        binaries: Optional sequence of expanded ``BinarySpec`` instances.

    Returns:
        Tuple of ``(json_manifest_path, cmake_manifest_path)``.
    """
    generated_dir.mkdir(parents=True, exist_ok=True)
    json_path = generated_dir / "freebsd_usr_bin_manifest.json"
    cmake_path = generated_dir / "freebsd_usr_bin_targets.cmake"

    payload = {
        "total_entries": len(top_makefiles) + len(specs),
        "top_makefiles": list(top_makefiles),
        "utility_count": len(specs),
        "binary_count": len(binaries),
        "utilities": [dataclasses.asdict(s) for s in specs],
        "binaries": [dataclasses.asdict(b) for b in binaries],
    }
    json_path.write_text(json.dumps(payload, indent=2) + NL, encoding="utf-8")

    cmake_lines = [
        "# Automatically generated by scripts/parse_freebsd_usr_bin.py",
        f"set(FREEBSD_USR_BIN_TOTAL_ENTRIES {len(top_makefiles) + len(specs)})",
        f"set(FREEBSD_USR_BIN_UTILITY_COUNT {len(specs)})",
        f"set(FREEBSD_USR_BIN_BINARY_COUNT {len(binaries)})",
        "set(FREEBSD_USR_BIN_UTILITIES",
    ]
    for spec in specs:
        cmake_lines.append(f'    "{spec.name}"')
    cmake_lines.append(")")
    for spec in specs:
        safe_id = re.sub(r"[^A-Za-z0-9_]", "_", spec.name.upper())
        cmake_lines.append(f'set(FREEBSD_USR_BIN_{safe_id}_PROG "{spec.prog}")')
        cmake_lines.append(f"set(FREEBSD_USR_BIN_{safe_id}_TIER {spec.tier})")
        srcs_joined = ";".join(Path(s).as_posix() for s in spec.sources)
        incs_joined = ";".join(Path(i).as_posix() for i in spec.include_dirs)
        libs_joined = ";".join(spec.libs)
        links_joined = ";".join(spec.links)
        cmake_lines.append(f'set(FREEBSD_USR_BIN_{safe_id}_SOURCES "{srcs_joined}")')
        cmake_lines.append(f'set(FREEBSD_USR_BIN_{safe_id}_INCLUDES "{incs_joined}")')
        cmake_lines.append(f'set(FREEBSD_USR_BIN_{safe_id}_LIBS "{libs_joined}")')
        cmake_lines.append(f'set(FREEBSD_USR_BIN_{safe_id}_LINKS "{links_joined}")')
    cmake_path.write_text(NL.join(cmake_lines) + NL, encoding="utf-8")

    return json_path, cmake_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the FreeBSD ``usr.bin`` manifest generator.

    Args:
        argv: Optional CLI argument list.

    Returns:
        Parsed ``argparse.Namespace``.
    """
    parser = argparse.ArgumentParser(
        description="Parse ../freebsd-src/usr.bin and generate out-of-tree CMake manifests."
    )
    parser.add_argument(
        "--freebsd-src",
        type=Path,
        default=None,
        help="Path to freebsd-src root directory (auto-detects ../freebsd-src or ./freebsd-src).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/freebsd_generated"),
        help="Output directory for generated sources and CMake manifests.",
    )
    parser.add_argument(
        "--patches-dir",
        type=Path,
        default=None,
        help="Directory containing declarative .patch files (default: auto patches/).",
    )
    parser.add_argument(
        "--build-clang",
        action="store_true",
        help="Expand full upstream usr.bin/clang Makefile subtree.",
    )
    parser.add_argument(
        "--build-ofed",
        action="store_true",
        help="Expand full upstream usr.bin/ofed Makefile subtree.",
    )
    parser.add_argument(
        "--build-kyua",
        action="store_true",
        help="Expand full upstream usr.bin/kyua Makefile subtree.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``parse_freebsd_usr_bin.py``.

    Args:
        argv: Optional CLI argument list.

    Returns:
        Exit status code (``0`` on success, ``1`` on error).
    """
    from scripts.per_binary_cmake import emit_all_per_binary_cmake

    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    freebsd_src: Path = (
        args.freebsd_src if args.freebsd_src is not None else locate_default_freebsd_src(repo_root)
    )
    active_patches_dir: Path | None = args.patches_dir
    if active_patches_dir is None and (freebsd_src / "contrib").is_dir():
        active_patches_dir = repo_root / "patches"
    enabled_heavy = frozenset(
        name
        for name, flag in (
            ("clang", bool(args.build_clang)),
            ("ofed", bool(args.build_ofed)),
            ("kyua", bool(args.build_kyua)),
        )
        if flag
    )
    try:
        top_mks, specs, binaries = audit_freebsd_usr_bin_binaries(
            freebsd_src,
            args.output_dir,
            patches_dir=active_patches_dir,
            heavy_subtrees=enabled_heavy,
        )
        write_manifest_files(top_mks, specs, args.output_dir, binaries=binaries)
        emit_all_per_binary_cmake(
            binaries,
            repo_root=repo_root,
            freebsd_src=freebsd_src,
            generated_dir=args.output_dir,
        )
    except FreeBsdPortError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
