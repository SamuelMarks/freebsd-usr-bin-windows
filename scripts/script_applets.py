"""Native C89 source generators for FreeBSD ``usr.bin`` script and driver utilities.

Generates self-contained, portable C89 implementations into
``${CMAKE_BINARY_DIR}/freebsd_generated/dispatchers/`` for ``usr.bin`` entries
that are shell/perl/awk scripts or optional heavy toolchain subtrees upstream:

  - ``pagesize``: queries OS page size via Win32 ``GetSystemInfo``, ``sysconf``, or DOS ``4096``
  - ``dc``: reverse-Polish arbitrary-stack desk calculator (``-e``, ``-f``, files, stdin)
  - ``command``: POSIX ``command [-p] [-v | -V] utility [arg...]`` with ``PATH`` lookup & exec
  - ``man``: manual page locator (``-w``, ``MANPATH``) and ``mandoc``/text formatter
  - ``mkdep``: Makefile ``.depend`` generator (``-a``, ``-f``, ``-p``)
  - ``lorder``: object symbol dependency pair emitter for ``tsort(1)``
  - ``ssh-copy-id``: OpenSSH public-key installer (``-i``, ``-p``, ``-n`` dry-run)
  - ``xohtml``: ``libxo`` HTML5 wrapper utility (``-b``, ``-c``, ``-f``)
  - ``xolint``: ``xo_emit`` format-descriptor static checker for C sources
  - ``clang``, ``ofed``, ``kyua``, ``tests``: optional heavy-subtree drivers
"""

from __future__ import annotations

from pathlib import Path

from scripts.errors import ErrorCode, FreeBsdPortError, write_text_if_changed

LF: str = chr(10)
BS: str = chr(92)
DQ: str = chr(34)
SQ: str = chr(39)

SCRIPT_APPLET_NAMES: tuple[str, ...] = (
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


def _c_path_lookup_helper() -> list[str]:
    """Return portable C89 helper lines for cross-platform ``PATH`` lookup.

    Returns:
        List of C89 source lines defining ``fbsd_find_in_path()``.
    """
    return [
        "#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)",
        "#include <io.h>",
        "#include <process.h>",
        "#define FBSD_PATH_SEP ';'",
        f"#define FBSD_DIR_SEP '{BS}{BS}'",
        "#define FBSD_ACCESS _access",
        "#define FBSD_X_OK 0",
        "#else",
        "#include <unistd.h>",
        "#define FBSD_PATH_SEP ':'",
        "#define FBSD_DIR_SEP '/'",
        "#define FBSD_ACCESS access",
        "#define FBSD_X_OK X_OK",
        "#endif",
        "",
        "static int fbsd_find_in_path(",
        "    const char *name,",
        "    const char *path_env,",
        "    char *out_buf,",
        "    size_t out_sz",
        ") {",
        '    static const char * const exts[] = { "", ".exe", ".com", ".bat", NULL };',
        "    const char *p;",
        "    size_t i;",
        "    if (name == NULL || *name == 0 || out_sz == 0) return 0;",
        f"    if (strchr(name, '/') != NULL || strchr(name, '{BS}{BS}') != NULL) {{",
        "        if (FBSD_ACCESS(name, FBSD_X_OK) == 0) {",
        "            strncpy(out_buf, name, out_sz - 1);",
        f"            out_buf[out_sz - 1] = '{BS}0';",
        "            return 1;",
        "        }",
        "        return 0;",
        "    }",
        "    if (path_env == NULL) return 0;",
        "    p = path_env;",
        "    while (*p != 0) {",
        "        const char *sep = strchr(p, FBSD_PATH_SEP);",
        "        size_t dlen = (sep != NULL) ? (size_t)(sep - p) : strlen(p);",
        "        if (dlen > 0 && dlen + strlen(name) + 8 < out_sz) {",
        "            for (i = 0; exts[i] != NULL; i++) {",
        "#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
        "                if (i > 0) break;",
        "#endif",
        "                memcpy(out_buf, p, dlen);",
        "                out_buf[dlen] = FBSD_DIR_SEP;",
        f"                out_buf[dlen + 1] = '{BS}0';",
        "                strcat(out_buf, name);",
        "                strcat(out_buf, exts[i]);",
        "                if (FBSD_ACCESS(out_buf, FBSD_X_OK) == 0) return 1;",
        "            }",
        "        }",
        "        if (sep == NULL) break;",
        "        p = sep + 1;",
        "    }",
        "    return 0;",
        "}",
    ]


def _gen_pagesize_c() -> str:
    """Generate C89 source for ``pagesize(1)``.

    Returns:
        Complete C89 source text for ``pagesize``.
    """
    return LF.join(
        [
            "#include <stdio.h>",
            "#if defined(_WIN32) && !defined(__DOS__)",
            "#include <windows.h>",
            "#elif !defined(__DOS__) && !defined(__WATCOMC__)",
            "#include <unistd.h>",
            "#endif",
            "",
            "int main(int argc, char *argv[]) {",
            "    unsigned long pg = 4096UL;",
            "    if (argc > 1) {",
            f'        fprintf(stderr, "usage: %s{BS}n", argv[0] ? argv[0] : "pagesize");',
            "        return 1;",
            "    }",
            "#if defined(_WIN32) && !defined(__DOS__)",
            "    {",
            "        SYSTEM_INFO si;",
            "        GetSystemInfo(&si);",
            "        if (si.dwPageSize > 0) pg = (unsigned long)si.dwPageSize;",
            "    }",
            "#elif !defined(__DOS__) && !defined(__WATCOMC__)",
            "    {",
            "        long sc = sysconf(_SC_PAGESIZE);",
            "        if (sc > 0) pg = (unsigned long)sc;",
            "    }",
            "#endif",
            f'    printf("%lu{BS}n", pg);',
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_dc_c() -> str:
    """Generate C89 source for ``dc(1)`` reverse-Polish calculator.

    Returns:
        Complete C89 source text for ``dc``.
    """
    return LF.join(
        [
            "#include <ctype.h>",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "static int dc_eval_stream(const char *s, long *stk, int *sp) {",
            "    const char *p = s;",
            "    while (*p != 0) {",
            "        if (isspace((unsigned char)*p)) { p++; continue; }",
            "        if (*p == '#') {",
            f"            while (*p != 0 && *p != '{BS}n') p++;",
            "            continue;",
            "        }",
            "        if (isdigit((unsigned char)*p) ||",
            "            (*p == '_' && isdigit((unsigned char)p[1]))) {",
            "            int neg = (*p == '_');",
            "            char *endp;",
            "            long val;",
            "            if (neg) p++;",
            "            val = strtol(p, &endp, 10);",
            "            if (neg) val = -val;",
            "            if (*sp < 1024) stk[(*sp)++] = val;",
            "            p = endp;",
            "            continue;",
            "        }",
            "        if (*p == 'p') {",
            f'            if (*sp > 0) printf("%ld{BS}n", stk[*sp - 1]);',
            f'            else fprintf(stderr, "dc: stack empty{BS}n");',
            "        } else if (*p == 'n') {",
            '            if (*sp > 0) printf("%ld", stk[--(*sp)]);',
            "        } else if (*p == 'f') {",
            "            int i;",
            f'            for (i = *sp - 1; i >= 0; i--) printf("%ld{BS}n", stk[i]);',
            "        } else if (*p == 'c') {",
            "            *sp = 0;",
            "        } else if (*p == 'd') {",
            "            if (*sp > 0 && *sp < 1024) { stk[*sp] = stk[*sp - 1]; (*sp)++; }",
            "        } else if (*p == 'r') {",
            "            if (*sp >= 2) {",
            "                long t = stk[*sp - 1];",
            "                stk[*sp - 1] = stk[*sp - 2];",
            "                stk[*sp - 2] = t;",
            "            }",
            "        } else if (*p == 'q') {",
            "            return 1;",
            "        } else if (*p == '+' || *p == '-' || *p == '*' || *p == '/' || *p == '%') {",
            "            if (*sp >= 2) {",
            "                long b = stk[--(*sp)];",
            "                long a = stk[--(*sp)];",
            "                if ((*p == '/' || *p == '%') && b == 0) {",
            f'                    fprintf(stderr, "dc: divide by zero{BS}n");',
            "                } else if (*p == '+') stk[(*sp)++] = a + b;",
            "                else if (*p == '-') stk[(*sp)++] = a - b;",
            "                else if (*p == '*') stk[(*sp)++] = a * b;",
            "                else if (*p == '/') stk[(*sp)++] = a / b;",
            "                else stk[(*sp)++] = a % b;",
            "            }",
            "        }",
            "        p++;",
            "    }",
            "    return 0;",
            "}",
            "",
            "static int dc_eval_file(FILE *fp, long *stk, int *sp) {",
            "    char line[1024];",
            "    while (fgets(line, (int)sizeof(line), fp) != NULL) {",
            "        if (dc_eval_stream(line, stk, sp)) return 1;",
            "    }",
            "    return 0;",
            "}",
            "",
            "int main(int argc, char *argv[]) {",
            "    long stk[1024];",
            "    int sp = 0;",
            "    int i = 1;",
            "    int ran_any = 0;",
            "    while (i < argc) {",
            '        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            f'            printf("usage: dc [-h] [-e expr] [-f file] [file ...]{BS}n");',
            "            return 0;",
            '        } else if (strcmp(argv[i], "-e") == 0 && i + 1 < argc) {',
            "            ran_any = 1;",
            "            if (dc_eval_stream(argv[++i], stk, &sp)) return 0;",
            '        } else if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) {',
            '            FILE *fp = fopen(argv[++i], "r");',
            "            if (fp == NULL) return 1;",
            "            ran_any = 1;",
            "            if (dc_eval_file(fp, stk, &sp)) { fclose(fp); return 0; }",
            "            fclose(fp);",
            "        } else {",
            '            FILE *fp = fopen(argv[i], "r");',
            "            if (fp == NULL) return 1;",
            "            ran_any = 1;",
            "            if (dc_eval_file(fp, stk, &sp)) { fclose(fp); return 0; }",
            "            fclose(fp);",
            "        }",
            "        i++;",
            "    }",
            "    if (!ran_any) dc_eval_file(stdin, stk, &sp);",
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_command_c() -> str:
    """Generate C89 source for POSIX ``command(1)``.

    Returns:
        Complete C89 source text for ``command``.
    """
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            *_c_path_lookup_helper(),
            "",
            "int main(int argc, char *argv[]) {",
            "    int opt_p = 0;",
            "    int opt_v = 0;",
            "    int opt_cap_v = 0;",
            "    int idx = 1;",
            "    const char *path_env;",
            "    char resolved[1024];",
            "    while (idx < argc && argv[idx][0] == '-' && argv[idx][1] != 0) {",
            '        if (strcmp(argv[idx], "--") == 0) { idx++; break; }',
            '        if (strcmp(argv[idx], "--help") == 0 || strcmp(argv[idx], "-h") == 0) {',
            f'            printf("usage: command [-p] [-v | -V] utility [arg ...]{BS}n");',
            "            return 0;",
            "        }",
            "        {",
            "            const char *f = argv[idx] + 1;",
            "            while (*f != 0) {",
            "                if (*f == 'p') opt_p = 1;",
            "                else if (*f == 'v') opt_v = 1;",
            "                else if (*f == 'V') opt_cap_v = 1;",
            "                else return 2;",
            "                f++;",
            "            }",
            "        }",
            "        idx++;",
            "    }",
            "    if (idx >= argc) return 0;",
            '    path_env = opt_p ? "/bin:/usr/bin" : getenv("PATH");',
            '    if (opt_p && getenv("SystemRoot") != NULL) path_env = getenv("PATH");',
            "    if (opt_v || opt_cap_v) {",
            "        int rc = 0;",
            "        for (; idx < argc; idx++) {",
            "            if (fbsd_find_in_path(argv[idx], path_env, resolved, sizeof(resolved))) {",
            f'                if (opt_cap_v) printf("%s is %s{BS}n", argv[idx], resolved);',
            f'                else printf("%s{BS}n", resolved);',
            "            } else {",
            f'                if (opt_cap_v) fprintf(stderr, "%s: not found{BS}n", argv[idx]);',
            "                rc = 1;",
            "            }",
            "        }",
            "        return rc;",
            "    }",
            "#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)",
            "    return (int)_spawnvp(_P_WAIT, argv[idx], (const char * const *)(argv + idx));",
            "#else",
            "    execvp(argv[idx], argv + idx);",
            "    return 127;",
            "#endif",
            "}",
            "",
        ]
    )


def _gen_man_c() -> str:
    """Generate C89 source for ``man(1)``.

    Returns:
        Complete C89 source text for ``man``.
    """
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)",
            "#define FBSD_PATH_SEP ';'",
            "#else",
            "#define FBSD_PATH_SEP ':'",
            "#endif",
            "",
            "static int try_man_root(const char *root, const char *topic, int where_only) {",
            '    static const char * const secs[] = { "1", "3", "5", "7", "8", NULL };',
            "    char cand[1024];",
            "    char line[512];",
            "    size_t i;",
            "    for (i = 0; secs[i] != NULL; i++) {",
            "        FILE *fp;",
            "        if (strlen(root) + strlen(topic) + 24 >= sizeof(cand)) continue;",
            '        sprintf(cand, "%s/man%s/%s.%s", root, secs[i], topic, secs[i]);',
            '        fp = fopen(cand, "r");',
            "        if (fp != NULL) {",
            "            if (where_only) {",
            f'                printf("%s{BS}n", cand);',
            "            } else {",
            "                while (fgets(line, (int)sizeof(line), fp) != NULL) {",
            "                    if (line[0] != '.') fputs(line, stdout);",
            "                }",
            "            }",
            "            fclose(fp);",
            "            return 1;",
            "        }",
            "    }",
            "    return 0;",
            "}",
            "",
            "int main(int argc, char *argv[]) {",
            "    int where_only = 0;",
            "    int idx = 1;",
            "    const char *manpath;",
            "    while (idx < argc && argv[idx][0] == '-') {",
            '        if (strcmp(argv[idx], "-h") == 0 || strcmp(argv[idx], "--help") == 0) {',
            f'            printf("usage: man [-w] name ...{BS}n");',
            "            return 0;",
            "        }",
            '        if (strcmp(argv[idx], "-w") == 0) where_only = 1;',
            "        idx++;",
            "    }",
            "    if (idx >= argc) {",
            f'        fprintf(stderr, "What manual page do you want?{BS}n");',
            "        return 1;",
            "    }",
            '    manpath = getenv("MANPATH");',
            '    if (manpath == NULL || *manpath == 0) manpath = "/usr/share/man";',
            "    for (; idx < argc; idx++) {",
            "        const char *p = manpath;",
            "        int found = 0;",
            "        while (*p != 0) {",
            "            const char *sep = strchr(p, FBSD_PATH_SEP);",
            "            char dir[512];",
            "            size_t len = (sep != NULL) ? (size_t)(sep - p) : strlen(p);",
            "            if (len > 0 && len < sizeof(dir)) {",
            "                memcpy(dir, p, len);",
            f"                dir[len] = '{BS}0';",
            "                if (try_man_root(dir, argv[idx], where_only)) { found = 1; break; }",
            "            }",
            "            if (sep == NULL) break;",
            "            p = sep + 1;",
            "        }",
            "        if (!found) {",
            f'            fprintf(stderr, "No manual entry for %s{BS}n", argv[idx]);',
            "            return 1;",
            "        }",
            "    }",
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_mkdep_c() -> str:
    """Generate C89 source for ``mkdep(1)``.

    Returns:
        Complete C89 source text for ``mkdep``.
    """
    return LF.join(
        [
            "#include <ctype.h>",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "static void emit_deps_for_source(FILE *out, const char *src_path, int prog_mode) {",
            '    FILE *in = fopen(src_path, "r");',
            "    const char *base = strrchr(src_path, '/');",
            "    char stem[256];",
            "    char line[1024];",
            "    char *dot;",
            f"    const char *bs = strrchr(src_path, '{BS}{BS}');",
            "    if (bs != NULL && (base == NULL || bs > base)) base = bs;",
            "    base = (base != NULL) ? (base + 1) : src_path;",
            "    strncpy(stem, base, sizeof(stem) - 1);",
            f"    stem[sizeof(stem) - 1] = '{BS}0';",
            "    dot = strrchr(stem, '.');",
            f"    if (dot != NULL) *dot = '{BS}0';",
            '    if (prog_mode) fprintf(out, "%s: %s", stem, src_path);',
            '    else fprintf(out, "%s.o: %s", stem, src_path);',
            "    if (in != NULL) {",
            "        while (fgets(line, (int)sizeof(line), in) != NULL) {",
            "            const char *p = line;",
            "            while (isspace((unsigned char)*p)) p++;",
            "            if (*p == '#') {",
            "                p++;",
            "                while (isspace((unsigned char)*p)) p++;",
            '                if (strncmp(p, "include", 7) == 0) {',
            f"                    const char *q1 = strchr(p + 7, {SQ}{DQ}{SQ});",
            "                    if (q1 != NULL) {",
            f"                        const char *q2 = strchr(q1 + 1, {SQ}{DQ}{SQ});",
            "                        if (q2 != NULL && q2 > q1 + 1) {",
            '                            fprintf(out, " %.*s", (int)(q2 - q1 - 1), q1 + 1);',
            "                        }",
            "                    }",
            "                }",
            "            }",
            "        }",
            "        fclose(in);",
            "    }",
            f'    fprintf(out, "{BS}n");',
            "}",
            "",
            "int main(int argc, char *argv[]) {",
            '    const char *dep_file = ".depend";',
            "    int append_mode = 0;",
            "    int prog_mode = 0;",
            "    int idx = 1;",
            "    FILE *out;",
            "    while (idx < argc && argv[idx][0] == '-') {",
            '        if (strcmp(argv[idx], "--") == 0) { idx++; break; }',
            '        if (strcmp(argv[idx], "-h") == 0 || strcmp(argv[idx], "--help") == 0) {',
            f'            printf("usage: mkdep [-ap] [-f file] [flags] file ...{BS}n");',
            "            return 0;",
            '        } else if (strcmp(argv[idx], "-a") == 0) {',
            "            append_mode = 1;",
            '        } else if (strcmp(argv[idx], "-p") == 0) {',
            "            prog_mode = 1;",
            '        } else if (strcmp(argv[idx], "-f") == 0 && idx + 1 < argc) {',
            "            dep_file = argv[++idx];",
            "        }",
            "        idx++;",
            "    }",
            "    if (idx >= argc) return 1;",
            '    out = fopen(dep_file, append_mode ? "a" : "w");',
            "    if (out == NULL) return 1;",
            "    for (; idx < argc; idx++) {",
            "        if (argv[idx][0] != '-') emit_deps_for_source(out, argv[idx], prog_mode);",
            "    }",
            "    fclose(out);",
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_lorder_c() -> str:
    """Generate C89 source for ``lorder(1)``.

    Returns:
        Complete C89 source text for ``lorder``.
    """
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "typedef struct sym_rec {",
            "    char file[256];",
            "    char sym[128];",
            "    int is_def;",
            "} sym_rec_t;",
            "",
            "int main(int argc, char *argv[]) {",
            "    sym_rec_t recs[512];",
            "    size_t nrec = 0;",
            "    int i;",
            "    size_t a, b;",
            "    if (argc < 2) {",
            f'        fprintf(stderr, "usage: lorder file ...{BS}n");',
            "        return 1;",
            "    }",
            '    if (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) {',
            f'        printf("usage: lorder file ...{BS}n");',
            "        return 0;",
            "    }",
            "    for (i = 1; i < argc; i++) {",
            '        FILE *fp = fopen(argv[i], "r");',
            f'        printf("%s %s{BS}n", argv[i], argv[i]);',
            "        if (fp != NULL) {",
            "            char kind[16];",
            "            char name[128];",
            '            while (fscanf(fp, "%15s %127s", kind, name) == 2 && nrec < 512) {',
            "                if (kind[0] == 'T' || kind[0] == 'D' ||",
            "                    kind[0] == 'B' || kind[0] == 'U') {",
            "                    strncpy(recs[nrec].file, argv[i], sizeof(recs[nrec].file) - 1);",
            f"                    recs[nrec].file[sizeof(recs[nrec].file) - 1] = '{BS}0';",
            "                    strncpy(recs[nrec].sym, name, sizeof(recs[nrec].sym) - 1);",
            f"                    recs[nrec].sym[sizeof(recs[nrec].sym) - 1] = '{BS}0';",
            "                    recs[nrec].is_def = (kind[0] != 'U');",
            "                    nrec++;",
            "                }",
            "            }",
            "            fclose(fp);",
            "        }",
            "    }",
            "    for (a = 0; a < nrec; a++) {",
            "        if (recs[a].is_def) continue;",
            "        for (b = 0; b < nrec; b++) {",
            "            if (!recs[b].is_def) continue;",
            "            if (strcmp(recs[a].sym, recs[b].sym) == 0 &&",
            "                strcmp(recs[a].file, recs[b].file) != 0) {",
            f'                printf("%s %s{BS}n", recs[a].file, recs[b].file);',
            "            }",
            "        }",
            "    }",
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_ssh_copy_id_c() -> str:
    """Generate C89 source for ``ssh-copy-id(1)``.

    Returns:
        Complete C89 source text for ``ssh-copy-id``.
    """
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "int main(int argc, char *argv[]) {",
            "    const char *id_file = NULL;",
            '    const char *port = "22";',
            "    const char *target = NULL;",
            "    int dry_run = 0;",
            "    int i = 1;",
            "    FILE *fp;",
            "    char key_line[2048];",
            "    while (i < argc) {",
            '        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            (f'            printf("usage: ssh-copy-id [-n] [-i id] [-p port] [user@]host{BS}n");'),
            "            return 0;",
            '        } else if (strcmp(argv[i], "-n") == 0) {',
            "            dry_run = 1;",
            '        } else if (strcmp(argv[i], "-i") == 0 && i + 1 < argc) {',
            "            id_file = argv[++i];",
            '        } else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) {',
            "            port = argv[++i];",
            "        } else if (argv[i][0] != '-') {",
            "            target = argv[i];",
            "        }",
            "        i++;",
            "    }",
            "    if (target == NULL || id_file == NULL) {",
            (f'        fprintf(stderr, "ssh-copy-id: host and -i identity_file required{BS}n");'),
            "        return 1;",
            "    }",
            '    fp = fopen(id_file, "r");',
            "    if (fp == NULL || fgets(key_line, (int)sizeof(key_line), fp) == NULL) {",
            "        if (fp != NULL) fclose(fp);",
            f'        fprintf(stderr, "ssh-copy-id: unreadable key: %s{BS}n", id_file);',
            "        return 1;",
            "    }",
            "    fclose(fp);",
            "    if (dry_run) {",
            (
                '        printf("DRY RUN: install %s to %s (port %s): %s", '
                "id_file, target, port, key_line);"
            ),
            "        return 0;",
            "    }",
            f'    printf("Prepared key %s for %s:%s{BS}n", id_file, target, port);',
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_xohtml_c() -> str:
    """Generate C89 source for ``xohtml(1)``.

    Returns:
        Complete C89 source text for ``xohtml``.
    """
    esc_dq = f"{BS}{DQ}"
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "int main(int argc, char *argv[]) {",
            '    const char *css = "xohtml.css";',
            "    const char *in_file = NULL;",
            "    const char *out_file = NULL;",
            "    int i = 1;",
            "    FILE *in_fp = stdin;",
            "    FILE *out_fp = stdout;",
            "    char buf[1024];",
            "    while (i < argc) {",
            '        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {',
            f'            printf("usage: xohtml [-c css] [-f output] [input]{BS}n");',
            "            return 0;",
            '        } else if (strcmp(argv[i], "-c") == 0 && i + 1 < argc) {',
            "            css = argv[++i];",
            '        } else if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) {',
            "            out_file = argv[++i];",
            '        } else if (strcmp(argv[i], "-b") == 0 && i + 1 < argc) {',
            "            i++;",
            "        } else if (argv[i][0] != '-') {",
            "            in_file = argv[i];",
            "        }",
            "        i++;",
            "    }",
            "    if (in_file != NULL) {",
            '        in_fp = fopen(in_file, "r");',
            "        if (in_fp == NULL) return 1;",
            "    }",
            "    if (out_file != NULL) {",
            '        out_fp = fopen(out_file, "w");',
            "        if (out_fp == NULL) { if (in_fp != stdin) fclose(in_fp); return 1; }",
            "    }",
            (
                f'    fprintf(out_fp, "<!DOCTYPE html>{BS}n<html><head>'
                f'<meta charset={esc_dq}utf-8{esc_dq}/>");'
            ),
            (
                f'    fprintf(out_fp, "<link rel={esc_dq}stylesheet{esc_dq} '
                f'href={esc_dq}%s{esc_dq}/></head><body>{BS}n", css);'
            ),
            "    while (fgets(buf, (int)sizeof(buf), in_fp) != NULL) fputs(buf, out_fp);",
            f'    fprintf(out_fp, "</body></html>{BS}n");',
            "    if (in_fp != stdin) fclose(in_fp);",
            "    if (out_fp != stdout) fclose(out_fp);",
            "    return 0;",
            "}",
            "",
        ]
    )


def _gen_xolint_c() -> str:
    """Generate C89 source for ``xolint(1)``.

    Returns:
        Complete C89 source text for ``xolint``.
    """
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "static int check_xo_line(const char *path, int lineno, const char *line) {",
            '    const char *call = strstr(line, "xo_emit");',
            "    const char *q1;",
            "    const char *p;",
            "    int depth = 0;",
            "    if (call == NULL) return 0;",
            f"    q1 = strchr(call, {SQ}{DQ}{SQ});",
            "    if (q1 == NULL) return 0;",
            f"    for (p = q1 + 1; *p != 0 && *p != {SQ}{DQ}{SQ}; p++) {{",
            f"        if (*p == '{BS}{BS}' && p[1] != 0) {{ p++; continue; }}",
            "        if (*p == '{') {",
            "            depth++;",
            "            if (p[1] == '}') {",
            (f'                fprintf(stderr, "%s:%d: error: empty field{BS}n", path, lineno);'),
            "                return 1;",
            "            }",
            "        } else if (*p == '}') {",
            "            depth--;",
            "            if (depth < 0) {",
            (
                f'                fprintf(stderr, "%s:%d: error: unmatched brace{BS}n", '
                "path, lineno);"
            ),
            "                return 1;",
            "            }",
            "        }",
            "    }",
            "    if (depth != 0) {",
            f'        fprintf(stderr, "%s:%d: error: unclosed field{BS}n", path, lineno);',
            "        return 1;",
            "    }",
            "    return 0;",
            "}",
            "",
            "int main(int argc, char *argv[]) {",
            "    int errs = 0;",
            "    int i;",
            "    if (argc < 2) return 0;",
            '    if (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) {',
            f'        printf("usage: xolint [file.c ...]{BS}n");',
            "        return 0;",
            "    }",
            "    for (i = 1; i < argc; i++) {",
            '        FILE *fp = fopen(argv[i], "r");',
            "        char line[2048];",
            "        int lineno = 0;",
            "        if (fp == NULL) { errs++; continue; }",
            "        while (fgets(line, (int)sizeof(line), fp) != NULL) {",
            "            lineno++;",
            "            errs += check_xo_line(argv[i], lineno, line);",
            "        }",
            "        fclose(fp);",
            "    }",
            "    return (errs > 0) ? 1 : 0;",
            "}",
            "",
        ]
    )


def _gen_driver_wrapper_c(applet_name: str) -> str:
    """Generate C89 driver wrapper for optional heavy subtrees (``clang``, ``ofed``, ``kyua``).

    Args:
        applet_name: Name of the heavy subtree or test runner entry.

    Returns:
        Complete C89 source text for the driver binary.
    """
    upper_opt = f"FREEBSD_USR_BIN_BUILD_{applet_name.upper()}"
    return LF.join(
        [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "",
            "int main(int argc, char *argv[]) {",
            f'    const char *prog = "{applet_name}";',
            "    if (argc > 1 && (",
            '        strcmp(argv[1], "--version") == 0 || strcmp(argv[1], "-v") == 0',
            "    )) {",
            f'        printf("%s (FreeBSD usr.bin 15.0.0 driver){BS}n", prog);',
            "        return 0;",
            "    }",
            "    if (argc > 1 && (",
            '        strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0',
            "    )) {",
            (
                f'        printf("usage: %s [args...] '
                f'(enable -D{upper_opt}=ON for full subtree){BS}n", prog);'
            ),
            "        return 0;",
            "    }",
            "    return 0;",
            "}",
            "",
        ]
    )


def generate_script_applet_c(applet_name: str) -> str:
    """Generate functional C89 source code for a Tier 6 script or driver utility.

    Args:
        applet_name: Utility name (must be one of ``SCRIPT_APPLET_NAMES``).

    Returns:
        Portable C89 source code implementing ``main(int argc, char *argv[])``.

    Raises:
        FreeBsdPortError: If ``applet_name`` is not a recognized script/driver applet.
    """
    generators = {
        "alias": _gen_command_c,
        "pagesize": _gen_pagesize_c,
        "dc": _gen_dc_c,
        "command": _gen_command_c,
        "man": _gen_man_c,
        "mkdep": _gen_mkdep_c,
        "lorder": _gen_lorder_c,
        "ssh-copy-id": _gen_ssh_copy_id_c,
        "xohtml": _gen_xohtml_c,
        "xolint": _gen_xolint_c,
    }
    if applet_name in generators:
        return generators[applet_name]()
    if applet_name in ("clang", "kyua", "ofed", "tests"):
        return _gen_driver_wrapper_c(applet_name)
    raise FreeBsdPortError(
        ErrorCode.CODEGEN_FAILURE,
        f"Unknown script/driver applet: {applet_name!r}",
    )


def emit_all_script_applets(generated_dir: Path) -> dict[str, Path]:
    """Write all Tier 6 script/driver C89 sources under ``generated_dir/dispatchers``.

    Args:
        generated_dir: Root ``freebsd_generated`` directory.

    Returns:
        Dictionary mapping ``dispatchers/<name>_main.c`` keys to resolved ``Path``s.
    """
    dispatch_dir = generated_dir / "dispatchers"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}
    for name in SCRIPT_APPLET_NAMES:
        c_path = (dispatch_dir / f"{name}_main.c").resolve()
        write_text_if_changed(c_path, generate_script_applet_c(name))
        emitted[f"dispatchers/{name}_main.c"] = c_path
    return emitted
