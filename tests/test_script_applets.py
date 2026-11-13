"""Unit and functional C89 compilation tests for ``scripts.script_applets``."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.script_applets import (
    LF,
    SCRIPT_APPLET_NAMES,
    emit_all_script_applets,
    generate_script_applet_c,
)


def test_generate_and_emit_all_script_applets(tmp_path: Path) -> None:
    """Verify source emission for all Tier 6 script applets and invalid-name error handling.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    with pytest.raises(FreeBsdPortError) as exc_info:
        generate_script_applet_c("nonexistent_script_applet")
    assert exc_info.value.code is ErrorCode.CODEGEN_FAILURE

    emitted = emit_all_script_applets(tmp_path / "gen")
    assert len(emitted) == len(SCRIPT_APPLET_NAMES)
    for name in SCRIPT_APPLET_NAMES:
        c_file = emitted[f"dispatchers/{name}_main.c"]
        assert c_file.is_file()
        assert "int main(int argc, char *argv[])" in c_file.read_text(encoding="utf-8")


def test_compile_and_execute_generated_c89_applets(tmp_path: Path) -> None:
    """Compile every generated Tier 6 C89 applet and verify end-to-end functional behavior.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    emitted = emit_all_script_applets(tmp_path / "gen")
    cc_bin = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    assert cc_bin is not None

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bins: dict[str, Path] = {}
    for name in SCRIPT_APPLET_NAMES:
        out_bin = bin_dir / name
        comp = subprocess.run(
            [
                cc_bin,
                "-std=c89",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(emitted[f"dispatchers/{name}_main.c"]),
                "-o",
                str(out_bin),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert comp.returncode == 0, f"{name} failed to compile: {comp.stderr}"
        bins[name] = out_bin

    # 1. pagesize
    pg = subprocess.run([str(bins["pagesize"])], capture_output=True, text=True, check=False)
    assert pg.returncode == 0 and pg.stdout.strip().isdigit()
    assert (
        subprocess.run(
            [str(bins["pagesize"]), "extra"], capture_output=True, check=False
        ).returncode
        == 1
    )

    # 2. dc (-e arithmetic, stack ops, comments, divide-by-zero)
    dc = subprocess.run(
        [str(bins["dc"]), "-e", "6 7 * d p _2 + p 10 0 /"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert dc.returncode == 0
    assert dc.stdout.splitlines() == ["42", "40"]
    assert "divide by zero" in dc.stderr

    # 3. command (-v, -V, execution)
    env_with_bin = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    cmd_v = subprocess.run(
        [str(bins["command"]), "-v", "pagesize"],
        env=env_with_bin,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cmd_v.returncode == 0 and "pagesize" in cmd_v.stdout
    cmd_exec = subprocess.run(
        [str(bins["command"]), "pagesize"],
        env=env_with_bin,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cmd_exec.returncode == 0 and cmd_exec.stdout.strip().isdigit()

    # 4. man (-w and text display via MANPATH)
    man_root = tmp_path / "man"
    (man_root / "man1").mkdir(parents=True)
    (man_root / "man1" / "printf.1").write_text(
        f".Dd Nov 12{LF}PRINTF MANUAL BODY{LF}", encoding="utf-8"
    )
    man_env = dict(os.environ, MANPATH=str(man_root))
    man_w = subprocess.run(
        [str(bins["man"]), "-w", "printf"], env=man_env, capture_output=True, text=True, check=False
    )
    assert man_w.returncode == 0 and "printf.1" in man_w.stdout
    man_txt = subprocess.run(
        [str(bins["man"]), "printf"], env=man_env, capture_output=True, text=True, check=False
    )
    assert man_txt.returncode == 0 and "PRINTF MANUAL BODY" in man_txt.stdout

    # 5. mkdep
    src_c = tmp_path / "demo.c"
    src_c.write_text(f'#include "local_hdr.h"{LF}int x;{LF}', encoding="utf-8")
    dep_out = tmp_path / ".depend"
    mkd = subprocess.run(
        [str(bins["mkdep"]), "-f", str(dep_out), str(src_c)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert mkd.returncode == 0
    assert "demo.o:" in dep_out.read_text(encoding="utf-8")
    assert "local_hdr.h" in dep_out.read_text(encoding="utf-8")

    # 6. lorder
    obj_a = tmp_path / "a.sym"
    obj_b = tmp_path / "b.sym"
    obj_a.write_text(f"U helper_fn{LF}", encoding="utf-8")
    obj_b.write_text(f"T helper_fn{LF}", encoding="utf-8")
    lor = subprocess.run(
        [str(bins["lorder"]), str(obj_a), str(obj_b)], capture_output=True, text=True, check=False
    )
    assert lor.returncode == 0
    assert f"{obj_a} {obj_b}" in lor.stdout

    # 7. ssh-copy-id (-n dry run)
    pub_key = tmp_path / "id_ed25519.pub"
    pub_key.write_text(f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5 test@host{LF}", encoding="utf-8")
    sci = subprocess.run(
        [str(bins["ssh-copy-id"]), "-n", "-i", str(pub_key), "-p", "2222", "user@example.com"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sci.returncode == 0 and "DRY RUN" in sci.stdout

    # 8. xohtml
    html_out = tmp_path / "out.html"
    xoh = subprocess.run(
        [str(bins["xohtml"]), "-c", "custom.css", "-f", str(html_out)],
        input=f"<div class='xo'>ok</div>{LF}",
        capture_output=True,
        text=True,
        check=False,
    )
    assert xoh.returncode == 0
    assert "custom.css" in html_out.read_text(encoding="utf-8")

    # 9. xolint (good file vs bad file)
    good_xo = tmp_path / "good_xo.c"
    bad_xo = tmp_path / "bad_xo.c"
    good_xo.write_text(f'xo_emit("{{:count/%d}}", 5);{LF}', encoding="utf-8")
    bad_xo.write_text(f'xo_emit("{{:unclosed", 5);{LF}', encoding="utf-8")
    assert subprocess.run([str(bins["xolint"]), str(good_xo)], check=False).returncode == 0
    assert (
        subprocess.run(
            [str(bins["xolint"]), str(bad_xo)], capture_output=True, check=False
        ).returncode
        == 1
    )

    # 10. clang / ofed / kyua / tests driver --version & --help
    for drv in ("clang", "ofed", "kyua", "tests"):
        v_res = subprocess.run(
            [str(bins[drv]), "--version"], capture_output=True, text=True, check=False
        )
        h_res = subprocess.run(
            [str(bins[drv]), "--help"], capture_output=True, text=True, check=False
        )
        assert v_res.returncode == 0 and drv in v_res.stdout
        assert h_res.returncode == 0 and "usage:" in h_res.stdout
