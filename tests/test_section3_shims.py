"""Unit tests for ``scripts.section3_shims``."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scripts.section3_shims import (
    emit_curses_section3_sources,
    emit_libarchive_win32_sources,
    emit_libdialog_section3_sources,
    emit_libedit_section3_sources,
    emit_libmp_section3_sources,
    emit_libsys_section3_sources,
)


def test_emit_all_section3_shims_and_compile(tmp_path: Path) -> None:
    """Emit all Section 3 shim headers/sources and compile + run C smoke checks.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    curses_files = emit_curses_section3_sources(tmp_path / "ncurses")
    assert "curses.h" in curses_files
    assert "term.h" in curses_files
    assert "termcap.h" in curses_files
    assert "fbsd_curses.c" in curses_files

    edit_files = emit_libedit_section3_sources(tmp_path / "libedit")
    assert "histedit.h" in edit_files
    assert "editline/readline.h" in edit_files
    assert "fbsd_edit.c" in edit_files

    mp_files = emit_libmp_section3_sources(tmp_path / "libmp")
    assert "mp.h" in mp_files
    assert "fbsd_mp.c" in mp_files

    sys_files = emit_libsys_section3_sources(tmp_path / "libsys")
    assert "security/pam_appl.h" in sys_files
    assert "rpcsvc/ypclnt.h" in sys_files
    assert "_FBSD_SYS_DATA void *ypresp_data;" in sys_files["rpcsvc/ypclnt.h"].read_text(
        encoding="utf-8"
    )
    assert "sys/nv.h" in sys_files
    assert "fbsd_sys.c" in sys_files

    la_files = emit_libarchive_win32_sources(tmp_path / "libarchive")
    assert "archive_windows.h" in la_files
    assert "bsdtar_windows.h" in la_files
    assert "fbsd_libarchive_win32.c" in la_files
    assert "#define waitpid __la_waitpid" in la_files["archive_windows.h"].read_text(
        encoding="utf-8"
    )
    assert "WaitForSingleObject" in la_files["fbsd_libarchive_win32.c"].read_text(encoding="utf-8")

    dlg_files = emit_libdialog_section3_sources(tmp_path / "libdialog")
    assert "dialog.h" in dlg_files
    assert "fbsd_dialog.c" in dlg_files

    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    assert cc is not None

    lf = chr(10)
    driver = tmp_path / "driver.c"
    driver.write_text(
        lf.join(
            [
                '#include "curses.h"',
                '#include "term.h"',
                '#include "dialog.h"',
                '#include "histedit.h"',
                '#include "mp.h"',
                '#include "security/pam_appl.h"',
                '#include "rpcsvc/ypclnt.h"',
                '#include "sys/nv.h"',
                "#include <assert.h>",
                "#include <string.h>",
                "int main(void) {",
                "    WINDOW *w = initscr();",
                "    MINT *a = mp_itom(6), *b = mp_itom(7), *c = mp_itom(0);",
                "    Tokenizer *tok = tok_init(NULL);",
                "    int argc = 0;",
                "    const char **argv = NULL;",
                "    nvlist_t *nvl = nvlist_create(0);",
                "    pam_handle_t *pamh = NULL;",
                "    char *dom = NULL;",
                "    assert(w != NULL);",
                "    assert(getattrs(w) == 0U);",
                '    mvwaddstr(w, 0, 0, "ok");',
                "    init_dialog(stdin, stdout);",
                '    assert(dialog_gauge("T", "P", 7, 40, 50) == 0);',
                "    end_dialog();",
                "    endwin();",
                "    mp_mult(a, b, c);",
                "    mp_mfree(a); mp_mfree(b); mp_mfree(c);",
                '    assert(tok_str(tok, "foo bar", &argc, &argv) == 0 && argc == 2);',
                "    tok_end(tok);",
                '    nvlist_add_string(nvl, "k", "v");',
                '    assert(strcmp(nvlist_get_string(nvl, "k"), "v") == 0);',
                "    nvlist_destroy(nvl);",
                '    assert(pam_start("login", "root", NULL, &pamh) == PAM_SUCCESS);',
                "    pam_end(pamh, PAM_SUCCESS);",
                "    assert(yp_get_default_domain(&dom) == 0 && dom != NULL);",
                "    return 0;",
                "}",
            ]
        )
        + lf,
        encoding="utf-8",
    )

    exe = tmp_path / "shim_test_bin"
    subprocess.run(
        [
            cc,
            f"-I{tmp_path / 'ncurses'}",
            f"-I{tmp_path / 'libdialog'}",
            f"-I{tmp_path / 'libedit'}",
            f"-I{tmp_path / 'libmp'}",
            f"-I{tmp_path / 'libsys'}",
            str(driver),
            str(curses_files["fbsd_curses.c"]),
            str(dlg_files["fbsd_dialog.c"]),
            str(edit_files["fbsd_edit.c"]),
            str(mp_files["fbsd_mp.c"]),
            str(sys_files["fbsd_sys.c"]),
            "-o",
            str(exe),
        ],
        check=True,
    )
    res = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    assert res.returncode == 0
