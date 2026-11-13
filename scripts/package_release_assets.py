#!/usr/bin/env python3
"""GitHub Releases suite, SDK, and per-binary archive packager.

Assembles release assets for ``v*`` tag builds across Windows (``X64``, ``X86``,
``ARM64``) and 32-bit Protected-Mode DOS (``dos32``) while enforcing GitHub
Releases' 1,000-asset API ceiling (default safe cap ``< 950``):

  - Suite bundles (``.zip``, ``-setup.exe``, ``.msi``, standalone multicall ``.exe``)
  - ``freebsd-usr-bin-<ver>-section3-sdk.zip`` (Section 3 ``.dll``/``.lib`` + headers)
  - ``<prog>-<ver>-windows.zip`` per binary (``x64/``, ``x86/``, ``arm64/`` ``.exe`` +
    Section 3 ``.dll``s + standalone ``CMakeLists.txt`` + licenses)
  - ``<prog>-<ver>-dos32.zip`` per binary (DOS ``<prog>.exe`` + ``DOS32A.EXE`` + licenses)
  - Deterministic ``SHA256SUMS.txt``
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import shutil
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts.errors import ErrorCode, FreeBsdPortError

LF: str = chr(10)

LICENSE_FILES: tuple[str, ...] = (
    "LICENSE-APACHE",
    "LICENSE-MIT",
    "LICENSE-CC0",
)


@dataclasses.dataclass(frozen=True)
class ReleaseConfig:
    """Typed configuration for packaging GitHub Release assets.

    Attributes:
        version: Release version string without leading ``v`` (e.g. ``15.0.0``).
        repo_root: Repository root containing ``LICENSE-*`` files.
        output_dir: Destination directory where release assets are written.
        windows_dirs: Mapping of arch label (``X64``, ``X86``, ``ARM64``) to build root.
        dos_dir: Optional OpenWatcom 32-bit DOS build root directory.
        per_binary_cmake_dir: Optional ``freebsd_generated/per_binary`` directory.
        max_assets: Maximum allowed file count in ``output_dir`` (default ``950``).
    """

    version: str
    repo_root: Path
    output_dir: Path
    windows_dirs: Mapping[str, Path]
    dos_dir: Path | None = None
    per_binary_cmake_dir: Path | None = None
    max_assets: int = 950


def _add_licenses_to_zip(zf: zipfile.ZipFile, repo_root: Path) -> None:
    """Write existing repository ``LICENSE-*`` files into ``zf``.

    Args:
        zf: Open ``ZipFile`` in write mode.
        repo_root: Repository root directory.
    """
    for lic_name in LICENSE_FILES:
        lic_path = repo_root / lic_name
        if lic_path.is_file():
            zf.write(lic_path, arcname=lic_name)


def _locate_bin_subdir(build_root: Path) -> Path:
    """Resolve the ``bin`` directory inside a single-config or multi-config build tree.

    Args:
        build_root: Architecture build directory.

    Returns:
        Directory containing compiled executables and runtime ``.dll``s.
    """
    for cand in (
        build_root / "bin" / "Release",
        build_root / "bin",
        build_root / "Release",
    ):
        if cand.is_dir():
            return cand
    return build_root


def _locate_lib_subdir(build_root: Path) -> Path | None:
    """Resolve the ``lib`` directory inside a build tree if present.

    Args:
        build_root: Architecture build directory.

    Returns:
        ``Path`` to ``lib`` directory or ``None`` if absent.
    """
    for cand in (build_root / "lib" / "Release", build_root / "lib"):
        if cand.is_dir():
            return cand
    return None


def _stage_arch_suite_bundles(
    arch: str,
    build_root: Path,
    version: str,
    repo_root: Path,
    out_dir: Path,
) -> list[Path]:
    """Copy or synthesize suite-level bundles for a single architecture.

    Args:
        arch: Architecture tag (e.g. ``X64``, ``X86``, ``ARM64``, ``dos32``).
        build_root: Build output root for ``arch``.
        version: Release version string.
        repo_root: Repository root directory.
        out_dir: Release assets output directory.

    Returns:
        List of suite asset ``Path``s written to ``out_dir``.
    """
    written: list[Path] = []
    prefix = f"freebsd-usr-bin-{version}-{arch}"
    for ext in (".zip", "-setup.exe", ".msi", ".exe"):
        pre_built = build_root / f"{prefix}{ext}"
        if pre_built.is_file():
            dst = out_dir / pre_built.name
            shutil.copyfile(pre_built, dst)
            written.append(dst)

    bin_dir = _locate_bin_subdir(build_root)
    mc_exe = bin_dir / "freebsd-usr-bin.exe"
    dst_mc = out_dir / f"{prefix}.exe"
    if mc_exe.is_file() and not dst_mc.is_file():
        shutil.copyfile(mc_exe, dst_mc)
        written.append(dst_mc)

    dst_zip = out_dir / f"{prefix}.zip"
    if not dst_zip.is_file():
        with zipfile.ZipFile(dst_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(bin_dir.iterdir()):
                if item.is_file():
                    zf.write(item, arcname=f"bin/{item.name}")
            _add_licenses_to_zip(zf, repo_root)
        written.append(dst_zip)

    return written


def _build_section3_sdk_zip(config: ReleaseConfig) -> Path | None:
    """Create ``freebsd-usr-bin-<ver>-section3-sdk.zip`` if any SDK files exist.

    Args:
        config: Active ``ReleaseConfig``.

    Returns:
        ``Path`` to generated SDK archive, or ``None`` if no Section 3 files exist.
    """
    entries: list[tuple[Path, str]] = []
    arch_roots: list[tuple[str, Path]] = [
        (arch.lower(), root) for arch, root in sorted(config.windows_dirs.items()) if root.is_dir()
    ]
    if config.dos_dir is not None and config.dos_dir.is_dir():
        arch_roots.append(("dos32", config.dos_dir))

    for arch_lbl, root in arch_roots:
        bin_dir = _locate_bin_subdir(root)
        for dll in sorted(bin_dir.glob("*.dll")):
            entries.append((dll, f"{arch_lbl}/bin/{dll.name}"))
        lib_dir = _locate_lib_subdir(root)
        if lib_dir is not None:
            for lib_f in sorted(lib_dir.iterdir()):
                if lib_f.is_file():
                    entries.append((lib_f, f"{arch_lbl}/lib/{lib_f.name}"))
        s3_inc = root / "freebsd_generated" / "section3" / "include"
        if s3_inc.is_dir():
            for hdr in sorted(s3_inc.rglob("*.h")):
                rel_h = hdr.relative_to(s3_inc).as_posix()
                entries.append((hdr, f"include/{rel_h}"))

    if not entries:
        return None

    sdk_zip = config.output_dir / f"freebsd-usr-bin-{config.version}-section3-sdk.zip"
    seen_arc: set[str] = set()
    with zipfile.ZipFile(sdk_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src_p, arc_p in entries:
            if arc_p not in seen_arc:
                zf.write(src_p, arcname=arc_p)
                seen_arc.add(arc_p)
        _add_licenses_to_zip(zf, config.repo_root)
    return sdk_zip


def _build_per_binary_windows_zips(config: ReleaseConfig) -> list[Path]:
    """Create ``<prog>-<ver>-windows.zip`` for every standalone Windows binary.

    Args:
        config: Active ``ReleaseConfig``.

    Returns:
        Sorted list of created per-binary Windows ``.zip`` ``Path``s.
    """
    prog_arch_exes: dict[str, list[tuple[str, Path, tuple[Path, ...]]]] = {}
    for arch, root in [(a, r) for a, r in sorted(config.windows_dirs.items()) if r.is_dir()]:
        bin_dir = _locate_bin_subdir(root)
        dlls = tuple(sorted(bin_dir.glob("*.dll")))
        for exe in sorted(bin_dir.glob("*.exe")):
            stem = exe.stem
            if stem.lower() != "freebsd-usr-bin":
                prog_arch_exes.setdefault(stem, []).append((arch.lower(), exe, dlls))

    written: list[Path] = []
    for prog in sorted(prog_arch_exes):
        zpath = config.output_dir / f"{prog}-{config.version}-windows.zip"
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arch_low, exe_p, dlls in prog_arch_exes[prog]:
                zf.write(exe_p, arcname=f"{arch_low}/{exe_p.name}")
                for dll_p in dlls:
                    zf.write(dll_p, arcname=f"{arch_low}/{dll_p.name}")
            if config.per_binary_cmake_dir is not None:
                cm_cand = config.per_binary_cmake_dir / prog / "CMakeLists.txt"
                if cm_cand.is_file():
                    zf.write(cm_cand, arcname="CMakeLists.txt")
            _add_licenses_to_zip(zf, config.repo_root)
        written.append(zpath)
    return written


def _build_per_binary_dos_zips(config: ReleaseConfig) -> list[Path]:
    """Create ``<prog>-<ver>-dos32.zip`` for every standalone 32-bit DOS binary.

    Args:
        config: Active ``ReleaseConfig``.

    Returns:
        Sorted list of created per-binary DOS ``.zip`` ``Path``s.
    """
    if config.dos_dir is None or not config.dos_dir.is_dir():
        return []

    bin_dir = _locate_bin_subdir(config.dos_dir)

    extender = config.dos_dir / "DOS32A.EXE"
    written: list[Path] = []
    for exe in sorted(bin_dir.glob("*.exe")):
        stem = exe.stem
        if stem.lower() not in ("freebsd-usr-bin", "dos32a", "dos4gw"):
            zpath = config.output_dir / f"{stem}-{config.version}-dos32.zip"
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(exe, arcname=exe.name)
                if extender.is_file():
                    zf.write(extender, arcname="DOS32A.EXE")
                _add_licenses_to_zip(zf, config.repo_root)
            written.append(zpath)
    return written


def write_sha256sums(assets: Sequence[Path], out_dir: Path) -> Path:
    """Compute SHA-256 digests and write ``SHA256SUMS.txt`` in ``out_dir``.

    Args:
        assets: Sequence of release asset ``Path``s.
        out_dir: Destination release directory.

    Returns:
        ``Path`` to ``SHA256SUMS.txt``.
    """
    unique_sorted = sorted({p.resolve() for p in assets if p.is_file()}, key=lambda p: p.name)
    lines: list[str] = []
    for asset_path in unique_sorted:
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {asset_path.name}")
    sums_path = out_dir / "SHA256SUMS.txt"
    sums_path.write_text(LF.join(lines) + LF, encoding="utf-8")
    return sums_path


def package_release_assets(config: ReleaseConfig) -> tuple[Path, ...]:
    """Assemble all suite, Section 3 SDK, per-binary, and checksum release assets.

    Args:
        config: Validated ``ReleaseConfig``.

    Returns:
        Sorted tuple of all generated release asset ``Path``s (including ``SHA256SUMS.txt``).

    Raises:
        FreeBsdPortError: If total asset count meets or exceeds ``config.max_assets``.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)
    collected: list[Path] = []

    for arch, win_root in sorted(config.windows_dirs.items()):
        if win_root.is_dir():
            collected.extend(
                _stage_arch_suite_bundles(
                    arch,
                    win_root,
                    config.version,
                    config.repo_root,
                    config.output_dir,
                )
            )

    if config.dos_dir is not None and config.dos_dir.is_dir():
        collected.extend(
            _stage_arch_suite_bundles(
                "dos32",
                config.dos_dir,
                config.version,
                config.repo_root,
                config.output_dir,
            )
        )

    sdk_zip = _build_section3_sdk_zip(config)
    if sdk_zip is not None:
        collected.append(sdk_zip)

    collected.extend(_build_per_binary_windows_zips(config))
    collected.extend(_build_per_binary_dos_zips(config))

    # +1 accounts for SHA256SUMS.txt
    if len(collected) + 1 >= config.max_assets:
        raise FreeBsdPortError(
            ErrorCode.PACKAGE_ASSET_LIMIT_EXCEEDED,
            (
                f"Release asset count ({len(collected) + 1}) "
                f"exceeds safe ceiling ({config.max_assets})"
            ),
            path=config.output_dir,
        )

    sums_file = write_sha256sums(collected, config.output_dir)
    collected.append(sums_file)
    return tuple(sorted({p.resolve() for p in collected}, key=lambda p: p.name))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for ``package_release_assets.py``.

    Args:
        argv: Optional CLI argument sequence.

    Returns:
        Parsed ``argparse.Namespace``.
    """
    parser = argparse.ArgumentParser(
        description="Package suite, Section 3 SDK, and per-binary GitHub Release assets."
    )
    parser.add_argument("--version", default="15.0.0", help="Release version (e.g. 15.0.0).")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("release_assets"),
        help="Destination directory for packaged release files.",
    )
    parser.add_argument("--win-x64", type=Path, default=None, help="Windows X64 build directory.")
    parser.add_argument("--win-x86", type=Path, default=None, help="Windows X86 build directory.")
    parser.add_argument(
        "--win-arm64", type=Path, default=None, help="Windows ARM64 build directory."
    )
    parser.add_argument("--dos-dir", type=Path, default=None, help="32-bit DOS build directory.")
    parser.add_argument(
        "--per-binary-cmake-dir",
        type=Path,
        default=None,
        help="Path to freebsd_generated/per_binary directory.",
    )
    parser.add_argument(
        "--max-assets",
        type=int,
        default=950,
        help="Maximum total release assets before raising PACKAGE_ASSET_LIMIT_EXCEEDED.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``package_release_assets.py``.

    Args:
        argv: Optional CLI argument sequence.

    Returns:
        Exit status code (``0`` on success, ``1`` on failure).
    """
    args = parse_args(argv)
    win_dirs: dict[str, Path] = {}
    if args.win_x64 is not None:
        win_dirs["X64"] = args.win_x64
    if args.win_x86 is not None:
        win_dirs["X86"] = args.win_x86
    if args.win_arm64 is not None:
        win_dirs["ARM64"] = args.win_arm64

    cfg = ReleaseConfig(
        version=args.version.lstrip("v"),
        repo_root=args.repo_root,
        output_dir=args.output_dir,
        windows_dirs=win_dirs,
        dos_dir=args.dos_dir,
        per_binary_cmake_dir=args.per_binary_cmake_dir,
        max_assets=args.max_assets,
    )
    try:
        package_release_assets(cfg)
    except FreeBsdPortError as exc:
        print(f"Release packaging error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
