"""Out-of-tree source staging, pure-Python unified diff patching, and cleanliness checks.

Applies declarative ``.patch`` files from ``patches/`` onto staged copies inside
``${CMAKE_BINARY_DIR}/freebsd_generated/staged_src/`` without modifying any file
in ``../freebsd-src`` and without requiring an external ``patch(1)`` binary on
Windows hosts.
"""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from scripts.errors import ErrorCode, FreeBsdPortError

TAB: str = chr(9)
LF: str = chr(10)
CR: str = chr(13)
BS: str = chr(92)
CRLF: str = f"{CR}{LF}"

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FREEBSD_VERSION_RE = re.compile(r"^\s*#\s*define\s+__FreeBSD_version\s+(\d+)", re.MULTILINE)
PATCH_VERSION_DIR_RE = re.compile(r"^freebsd(\d+)$")
PATCHED_HEADER_SUFFIXES: frozenset[str] = frozenset({".h", ".hh", ".hpp"})
STAGED_SIBLING_SUFFIXES: frozenset[str] = frozenset(
    {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}
)

GIT_REPO_ENV_VARS: frozenset[str] = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_SUPER_PREFIX",
        "GIT_WORK_TREE",
    }
)


@dataclasses.dataclass(frozen=True)
class PatchHunk:
    """Single ``@@ -orig +new @@`` hunk within a unified diff file patch.

    Attributes:
        orig_start: 1-based starting line in the original file (0 for empty files).
        orig_count: Line count in the original file covered by this hunk.
        new_start: 1-based starting line in the patched file.
        new_count: Line count in the patched file produced by this hunk.
        lines: Raw hunk body lines prefixed with ``' '``, ``'-'``, or ``'+'``.
    """

    orig_start: int
    orig_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class FilePatch:
    """Parsed unified diff targeting a single relative file path in ``freebsd-src``.

    Attributes:
        target_rel_path: Normalized POSIX relative path inside ``freebsd-src``.
        hunks: Ordered tuple of ``PatchHunk`` blocks to apply.
    """

    target_rel_path: str
    hunks: tuple[PatchHunk, ...]


def _normalize_patch_target(raw_header_path: str) -> str:
    """Normalize and validate a ``+++ b/path`` unified diff target path.

    Args:
        raw_header_path: Raw path token following ``+++ `` in a unified diff.

    Returns:
        Safe normalized POSIX relative path string.

    Raises:
        FreeBsdPortError: If the path is empty, absolute, or contains ``..``.
    """
    token = raw_header_path.split(TAB, 1)[0].strip()
    if token.startswith(("a/", "b/")):
        token = token[2:]
    if not token or token == "/dev/null":
        raise FreeBsdPortError(
            ErrorCode.PATCH_APPLY_ERROR,
            f"Invalid or empty patch target path: {raw_header_path!r}",
        )
    posix_path = PurePosixPath(token.replace(BS, "/"))
    if posix_path.is_absolute() or ".." in posix_path.parts:
        raise FreeBsdPortError(
            ErrorCode.PATCH_APPLY_ERROR,
            f"Unsafe absolute or parent-traversal patch path: {token!r}",
        )
    return posix_path.as_posix()


def parse_unified_diff(patch_text: str) -> tuple[FilePatch, ...]:
    """Parse unified diff text into one or more ``FilePatch`` objects.

    Args:
        patch_text: Full UTF-8 text of a ``.patch`` file.

    Returns:
        Tuple of parsed ``FilePatch`` records.

    Raises:
        FreeBsdPortError: If headers or hunks are malformed or missing.
    """
    lines = patch_text.splitlines()
    file_patches: list[FilePatch] = []
    idx = 0
    total = len(lines)

    while idx < total:
        line = lines[idx]
        if not line.strip() or line.startswith(("diff ", "index ", "#")):
            idx += 1
            continue
        if not line.startswith("--- "):
            raise FreeBsdPortError(
                ErrorCode.PATCH_APPLY_ERROR,
                f"Unexpected line outside unified diff header at line {idx + 1}: {line!r}",
            )
        if idx + 1 >= total or not lines[idx + 1].startswith("+++ "):
            raise FreeBsdPortError(
                ErrorCode.PATCH_APPLY_ERROR,
                f"Missing '+++ ' target header after line {idx + 1}",
            )

        target_rel = _normalize_patch_target(lines[idx + 1][4:])
        idx += 2
        hunks: list[PatchHunk] = []

        while idx < total and not lines[idx].startswith(("diff ", "--- ")):
            hline = lines[idx]
            if not hline.strip():
                idx += 1
                continue
            match = HUNK_HEADER_RE.match(hline)
            if match is None:
                raise FreeBsdPortError(
                    ErrorCode.PATCH_APPLY_ERROR,
                    f"Malformed hunk header at line {idx + 1}: {hline!r}",
                )
            orig_start = int(match.group(1))
            orig_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            idx += 1

            hunk_lines: list[str] = []
            seen_orig = 0
            seen_new = 0
            while idx < total and (seen_orig < orig_count or seen_new < new_count):
                bline = lines[idx]
                if bline.startswith(BS):
                    idx += 1
                    continue
                if not bline or bline[0] not in (" ", "-", "+"):
                    raise FreeBsdPortError(
                        ErrorCode.PATCH_APPLY_ERROR,
                        f"Invalid hunk body line at line {idx + 1}: {bline!r}",
                    )
                prefix = bline[0]
                if prefix == " ":
                    seen_orig += 1
                    seen_new += 1
                elif prefix == "-":
                    seen_orig += 1
                else:
                    seen_new += 1
                hunk_lines.append(bline)
                idx += 1

            if seen_orig != orig_count or seen_new != new_count:
                raise FreeBsdPortError(
                    ErrorCode.PATCH_APPLY_ERROR,
                    f"Incomplete hunk for {target_rel}: expected -{orig_count}/+{new_count}, "
                    f"got -{seen_orig}/+{seen_new}",
                )

            if idx < total and lines[idx].startswith(BS):
                idx += 1

            hunks.append(
                PatchHunk(
                    orig_start=orig_start,
                    orig_count=orig_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=tuple(hunk_lines),
                )
            )

        if not hunks:
            raise FreeBsdPortError(
                ErrorCode.PATCH_APPLY_ERROR,
                f"No hunks found for patch target {target_rel}",
            )
        file_patches.append(FilePatch(target_rel_path=target_rel, hunks=tuple(hunks)))

    if not file_patches:
        raise FreeBsdPortError(ErrorCode.PATCH_APPLY_ERROR, "Patch file contains no file diffs")

    return tuple(file_patches)


def _hunk_matches_at(work_lines: Sequence[str], start_idx: int, hunk: PatchHunk) -> bool:
    """Return whether ``hunk``'s context and removed lines match at ``start_idx``.

    Args:
        work_lines: Current file lines being patched.
        start_idx: Candidate 0-based line index in ``work_lines``.
        hunk: ``PatchHunk`` to check at ``start_idx``.

    Returns:
        ``True`` if every ``' '`` and ``'-'`` line matches verbatim.
    """
    cursor = start_idx
    for raw_hline in hunk.lines:
        if raw_hline[0] in (" ", "-"):
            if cursor >= len(work_lines) or work_lines[cursor] != raw_hline[1:]:
                return False
            cursor += 1
    return True


def _locate_hunk_start(
    work_lines: Sequence[str],
    expected_idx: int,
    hunk: PatchHunk,
) -> int | None:
    """Locate the nearest 0-based line index where ``hunk`` matches verbatim.

    Args:
        work_lines: Current file lines being patched.
        expected_idx: Expected 0-based start index adjusted by prior hunk deltas.
        hunk: ``PatchHunk`` whose context and removed lines must match.

    Returns:
        Matching 0-based start index, or ``None`` if no exact match exists.
    """
    max_idx = len(work_lines)
    if 0 <= expected_idx <= max_idx and _hunk_matches_at(work_lines, expected_idx, hunk):
        return expected_idx
    span = max(abs(expected_idx), abs(max_idx - expected_idx))
    for offset in range(1, span + 1):
        for candidate in (expected_idx - offset, expected_idx + offset):
            if 0 <= candidate <= max_idx and _hunk_matches_at(work_lines, candidate, hunk):
                return candidate
    return None


def detect_freebsd_major(freebsd_src: Path) -> int | None:
    """Detect the upstream FreeBSD major version from ``sys/sys/param.h``.

    Args:
        freebsd_src: Root directory of upstream ``freebsd-src``.

    Returns:
        Integer major version (e.g. ``15`` or ``16``), or ``None`` if unavailable.
    """
    param_h = freebsd_src / "sys" / "sys" / "param.h"
    if not param_h.is_file():
        return None
    match = FREEBSD_VERSION_RE.search(param_h.read_text(encoding="utf-8", errors="surrogateescape"))
    return int(match.group(1)) // 100000 if match is not None else None


def apply_unified_patch(original_text: str, file_patch: FilePatch) -> str:
    """Apply a parsed ``FilePatch`` to ``original_text`` in memory.

    Preserves the original file's line-ending convention (CRLF vs. LF) and
    trailing-newline presence, allowing exact-context line-offset shifts across
    minor upstream line movements while enforcing zero-fuzz verbatim context.

    Args:
        original_text: Unmodified text of the upstream source file.
        file_patch: Parsed ``FilePatch`` containing hunks to apply.

    Returns:
        Patched file contents as a string.

    Raises:
        FreeBsdPortError: If any hunk's context or removed lines fail to match.
    """
    newline = CRLF if CRLF in original_text else LF
    had_trailing_nl = original_text.endswith((CRLF, LF)) or original_text == ""
    work_lines = original_text.splitlines()
    delta = 0

    for hunk_idx, hunk in enumerate(file_patch.hunks, start=1):
        base_idx = 0 if hunk.orig_start == 0 else (hunk.orig_start - 1)
        expected_idx = 0 if hunk.orig_start == 0 else (base_idx + delta)
        matched_idx = _locate_hunk_start(work_lines, expected_idx, hunk)
        if matched_idx is None:
            if expected_idx < 0 or expected_idx > len(work_lines):
                raise FreeBsdPortError(
                    ErrorCode.PATCH_HUNK_MISMATCH,
                    f"Hunk #{hunk_idx} out of range at line {hunk.orig_start} "
                    f"for {file_patch.target_rel_path}",
                )
            orig_hlines = [ln[1:] for ln in hunk.lines if ln[0] in (" ", "-")]
            mismatches = [
                (expected_idx + idx, exp_line)
                for idx, exp_line in enumerate(orig_hlines)
                if expected_idx + idx >= len(work_lines)
                or work_lines[expected_idx + idx] != exp_line
            ]
            bad_idx, expected_line = mismatches[0]
            actual = work_lines[bad_idx] if bad_idx < len(work_lines) else "<EOF>"
            raise FreeBsdPortError(
                ErrorCode.PATCH_HUNK_MISMATCH,
                f"Hunk #{hunk_idx} mismatch in {file_patch.target_rel_path} "
                f"at line {bad_idx + 1}: expected {expected_line!r}, found {actual!r}",
            )

        span_len = sum(1 for raw_hline in hunk.lines if raw_hline[0] in (" ", "-"))
        replacement = [raw_hline[1:] for raw_hline in hunk.lines if raw_hline[0] in (" ", "+")]
        work_lines[matched_idx : matched_idx + span_len] = replacement
        delta = (matched_idx - base_idx) + len(replacement) - span_len

    joined = newline.join(work_lines)
    if had_trailing_nl and work_lines:
        return joined + newline
    return joined


def stage_patched_sources(
    freebsd_src: Path,
    patches_dir: Path,
    staged_dir: Path,
) -> dict[Path, Path]:
    """Apply all ``patches/**/*.patch`` files onto staged copies under ``staged_dir``.

    Subdirectories named ``freebsd<major>`` (for example ``patches/freebsd15/``
    and ``patches/freebsd16/``) are applied selectively when ``freebsd_src``'s
    detected major version matches ``<major>``.

    Args:
        freebsd_src: Root directory of upstream ``../freebsd-src``.
        patches_dir: Directory containing declarative ``.patch`` files.
        staged_dir: Out-of-tree destination directory for patched copies.

    Returns:
        Mapping from resolved upstream ``freebsd_src`` file ``Path`` to its
        resolved patched copy ``Path`` inside ``staged_dir``.

    Raises:
        FreeBsdPortError: If ``freebsd_src`` or a patch target is missing, or a
            patch fails to parse or apply cleanly.
    """
    src_root = freebsd_src.resolve()
    if not src_root.is_dir():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            "Upstream freebsd-src directory not found",
            path=freebsd_src,
        )

    if not patches_dir.is_dir():
        return {}

    major = detect_freebsd_major(src_root)
    staged_map: dict[Path, Path] = {}
    patched_header_dirs: set[Path] = set()
    for patch_file in sorted(patches_dir.rglob("*.patch")):
        rel_dirs = patch_file.relative_to(patches_dir).parts[:-1]
        ver_tags = [
            int(ver_match.group(1))
            for part in rel_dirs
            if (ver_match := PATCH_VERSION_DIR_RE.match(part)) is not None
        ]
        if ver_tags and major not in ver_tags:
            continue

        patch_text = patch_file.read_text(encoding="utf-8")
        file_patches = parse_unified_diff(patch_text)
        for fp in file_patches:
            orig_path = (src_root / fp.target_rel_path).resolve()
            if not orig_path.is_file():
                raise FreeBsdPortError(
                    ErrorCode.SOURCE_TREE_NOT_FOUND,
                    f"Patch target missing in freebsd-src ({patch_file.name})",
                    path=orig_path,
                )
            base_source = staged_map.get(orig_path, orig_path)
            current_text = base_source.read_text(encoding="utf-8", errors="surrogateescape")
            patched_text = apply_unified_patch(current_text, fp)

            dest_path = (staged_dir / fp.target_rel_path).resolve()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(patched_text, encoding="utf-8", errors="surrogateescape")
            staged_map[orig_path] = dest_path
            if orig_path.suffix in PATCHED_HEADER_SUFFIXES:
                patched_header_dirs.add(orig_path.parent)

    for hdr_dir in sorted(patched_header_dirs):
        dest_dir = (staged_dir / hdr_dir.relative_to(src_root)).resolve()
        for sib in sorted(hdr_dir.iterdir()):
            sib_resolved = sib.resolve()
            if (
                sib.is_file()
                and sib.suffix in STAGED_SIBLING_SUFFIXES
                and sib_resolved not in staged_map
            ):
                dest_sib = (dest_dir / sib.name).resolve()
                dest_sib.write_bytes(sib_resolved.read_bytes())
                staged_map[sib_resolved] = dest_sib

    return staged_map


def verify_upstream_clean(freebsd_src: Path) -> None:
    """Verify that ``freebsd_src`` has zero uncommitted edits or untracked files.

    Args:
        freebsd_src: Root path of ``../freebsd-src``.

    Raises:
        FreeBsdPortError: If ``freebsd_src`` does not exist or ``git status --porcelain``
            reports any modified or untracked files.
    """
    src_root = freebsd_src.resolve()
    if not src_root.is_dir():
        raise FreeBsdPortError(
            ErrorCode.SOURCE_TREE_NOT_FOUND,
            "Upstream freebsd-src directory not found",
            path=freebsd_src,
        )

    if not (src_root / ".git").exists():
        return

    clean_env = dict(os.environ)
    for git_var in GIT_REPO_ENV_VARS:
        clean_env.pop(git_var, None)

    res = subprocess.run(
        ["git", "-C", str(src_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        env=clean_env,
    )
    if res.returncode != 0 or res.stdout.strip():
        details = res.stdout.strip() or res.stderr.strip()
        raise FreeBsdPortError(
            ErrorCode.UPSTREAM_TREE_DIRTY,
            f"Upstream freebsd-src has modifications ({details})",
            path=src_root,
        )
