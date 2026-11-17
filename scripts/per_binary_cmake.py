"""Out-of-tree per-binary ``CMakeLists.txt`` and subproject index generator.

Emits ``${CMAKE_BINARY_DIR}/freebsd_generated/per_binary/<prog>/CMakeLists.txt``
for every concrete FreeBSD ``usr.bin`` ``BinarySpec`` plus the orchestrator
manifest ``${CMAKE_BINARY_DIR}/freebsd_generated/per_binary_subdirs.cmake``.

Each generated ``CMakeLists.txt`` supports dual execution modes:
  1. **Standalone Top-Level Mode** (``cmake -S .../per_binary/<prog> -B build``):
     Self-contained CMake project locating ``freebsd-src`` and ``auto-win-msvc``,
     building only ``<prog>``'s transitive Section 3 libraries, compiling
     ``<prog>``, registering ``CTest`` smoke checks, and configuring ``CPack``.
  2. **Root Subdirectory Mode** (``add_subdirectory()`` from root ``CMakeLists.txt``):
     Creates ``fbsd_bin_<id>`` with ``OUTPUT_NAME "<prog>"``, stages runtime
     Section 3 ``.dll``s on Windows, creates ``LINKS`` alias binaries, and
     registers ``COMPONENT <prog>`` and ``COMPONENT suite`` install rules.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from scripts.errors import ErrorCode, FreeBsdPortError
from scripts.multicall_prefixer import sanitize_applet_id
from scripts.parse_freebsd_usr_bin import BinarySpec

LF: str = chr(10)


def _posix(path: Path | str) -> str:
    """Convert ``path`` to a forward-slash CMake-safe string.

    Args:
        path: Input ``Path`` or path string.

    Returns:
        POSIX-formatted path string.
    """
    return Path(path).resolve().as_posix()


def render_per_binary_cmakelists(
    spec: BinarySpec,
    repo_root: Path,
    freebsd_src: Path,
    generated_dir: Path,
) -> str:
    """Render the dual-mode ``CMakeLists.txt`` content for ``spec``.

    Args:
        spec: Parsed ``BinarySpec`` describing the target binary.
        repo_root: Root directory of ``freebsd-usr-bin-windows``.
        freebsd_src: Root directory of ``../freebsd-src``.
        generated_dir: Out-of-tree ``freebsd_generated`` directory.

    Returns:
        Complete ``CMakeLists.txt`` text for ``spec.prog``.

    Raises:
        FreeBsdPortError: If ``spec`` has no compilable C/C++/Yacc/Lex sources.
    """
    if not spec.sources and not spec.yacc_sources and not spec.lex_sources:
        raise FreeBsdPortError(
            ErrorCode.CMAKE_EMIT_ERROR,
            f"Cannot emit CMakeLists.txt for binary with zero sources: {spec.prog!r}",
        )

    safe_id = sanitize_applet_id(spec.prog)
    langs = "C CXX" if spec.is_cxx else "C"
    repo_posix = _posix(repo_root)
    fbsd_posix = _posix(freebsd_src)
    gen_posix = _posix(generated_dir)
    gen_inc_posix = _posix(generated_dir / "include")

    lines = [
        f"# Automatically generated per-binary CMakeLists.txt for {spec.prog} ({spec.subdir})",
        "cmake_minimum_required(VERSION 3.24)",
        "",
        "if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)",
        "    set(_FBSD_STANDALONE_BINARY ON)",
        "    set(CMAKE_POLICY_VERSION_MINIMUM 3.5)",
        f"    project(freebsd_usr_bin_{safe_id} VERSION 15.0.0 LANGUAGES {langs})",
        "    set(CMAKE_C_STANDARD 11)",
        "    set(CMAKE_C_STANDARD_REQUIRED OFF)",
        "else()",
        "    set(_FBSD_STANDALONE_BINARY OFF)",
        "endif()",
    ]
    if spec.is_cxx:
        lines.extend(
            [
                "if(NOT FREEBSD_TARGET_DOS)",
                "    enable_language(CXX)",
                "    set(CMAKE_CXX_STANDARD 17)",
                "    set(CMAKE_CXX_STANDARD_REQUIRED OFF)",
                "endif()",
            ]
        )
    lines.extend(
        [
            "",
            f'set(FREEBSD_REPO_ROOT "{repo_posix}" CACHE PATH "freebsd-usr-bin-windows root")',
            f'set(FREEBSD_SRC_DIR "{fbsd_posix}" CACHE PATH "Upstream freebsd-src root")',
            f'set(FREEBSD_GEN_DIR "{gen_posix}" CACHE PATH "Generated FreeBSD artifacts dir")',
            f'set(FREEBSD_GEN_INC "{gen_inc_posix}" CACHE PATH "Generated FreeBSD include dir")',
            "",
            "if(_FBSD_STANDALONE_BINARY)",
            '    option(FREEBSD_USE_AUTO_WIN_MSVC "Link auto-win-msvc polyfill library" ON)',
            '    option(FREEBSD_SECTION3_SHARED "Build Section 3 libs as SHARED" ON)',
            '    if(WATCOM OR CMAKE_SYSTEM_NAME STREQUAL "DOS")',
            "        set(FREEBSD_TARGET_DOS ON)",
            "        set(FREEBSD_SECTION3_SHARED OFF)",
            "    else()",
            "        set(FREEBSD_TARGET_DOS OFF)",
            "        set(CMAKE_POSITION_INDEPENDENT_CODE ON)",
            "    endif()",
            "    if(FREEBSD_USE_AUTO_WIN_MSVC)",
            "        if(MSVC)",
            "            add_compile_definitions(_CRT_SECURE_NO_WARNINGS _CRT_RAND_S)",
            "        endif()",
            "        include(FetchContent)",
            '        set(BUILD_TESTING OFF CACHE BOOL "" FORCE)',
            '        set(AUTO_WIN_MSVC_BUILD_TESTING OFF CACHE BOOL "" FORCE)',
            '        set(_LOCAL_AWM "${FREEBSD_REPO_ROOT}/../auto-win-msvc")',
            (
                "        if(NOT DEFINED FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "
                'AND EXISTS "${_LOCAL_AWM}/CMakeLists.txt")'
            ),
            '            set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_LOCAL_AWM}")',
            "        endif()",
            "        FetchContent_Declare(",
            "            auto_win_msvc",
            "            GIT_REPOSITORY https://github.com/SamuelMarks/auto-win-msvc.git",
            "            GIT_TAG master",
            "            GIT_SHALLOW TRUE",
            "        )",
            "        FetchContent_MakeAvailable(auto_win_msvc)",
            '        if(EXISTS "${auto_win_msvc_SOURCE_DIR}/cmake/AutoWinMsvcTransform.cmake")',
            '            include("${auto_win_msvc_SOURCE_DIR}/cmake/AutoWinMsvcTransform.cmake")',
            "        endif()",
            "    endif()",
        ]
    )

    if spec.yacc_sources or spec.lex_sources:
        lines.extend(
            [
                '    if(EXISTS "${FREEBSD_REPO_ROOT}/cmake/FreeBsdBootstrapTools.cmake")',
                '        include("${FREEBSD_REPO_ROOT}/cmake/FreeBsdBootstrapTools.cmake")',
                "    endif()",
            ]
        )

    if spec.section3_targets:
        s3_joined = ";".join(spec.section3_targets)
        lines.extend(
            [
                f'    set(FREEBSD_REQUIRED_SECTION3_LIBS "{s3_joined}")',
                '    if(EXISTS "${FREEBSD_REPO_ROOT}/cmake/FreeBsdInternalLibs.cmake")',
                '        include("${FREEBSD_REPO_ROOT}/cmake/FreeBsdInternalLibs.cmake")',
                "    endif()",
            ]
        )

    lines.extend(["endif()", ""])

    lines.append(f"set(_FBSD_{safe_id.upper()}_RAW_SOURCES")
    for src in spec.sources:
        lines.append(f'    "{_posix(src)}"')
    lines.append(")")
    lines.extend(
        [
            'if(_FBSD_STANDALONE_BINARY AND EXISTS "${FREEBSD_GEN_DIR}/src/freebsd_libcompat.c")',
            (
                f"    list(APPEND _FBSD_{safe_id.upper()}_RAW_SOURCES "
                '"${FREEBSD_GEN_DIR}/src/freebsd_libcompat.c")'
            ),
            "endif()",
        ]
    )

    if spec.yacc_sources or spec.lex_sources:
        lines.extend(
            [
                "if(COMMAND freebsd_compile_yacc_lex)",
                "    freebsd_compile_yacc_lex(",
                f'        TARGET_ID "{safe_id}"',
                f'        OUT_DIR "${{FREEBSD_GEN_DIR}}/codegen/{safe_id}"',
            ]
        )
        if spec.yacc_sources:
            y_joined = " ".join(f'"{_posix(y)}"' for y in spec.yacc_sources)
            lines.append(f"        YACC_SOURCES {y_joined}")
        if spec.lex_sources:
            l_joined = " ".join(f'"{_posix(lx)}"' for lx in spec.lex_sources)
            lines.append(f"        LEX_SOURCES {l_joined}")
        lines.extend(
            [
                f"        OUT_SOURCES_VAR _FBSD_{safe_id.upper()}_CODEGEN_SOURCES",
                f"        OUT_INC_VAR _FBSD_{safe_id.upper()}_CODEGEN_INC",
                "    )",
                (
                    f"    list(APPEND _FBSD_{safe_id.upper()}_RAW_SOURCES "
                    f"${{_FBSD_{safe_id.upper()}_CODEGEN_SOURCES}})"
                ),
                "endif()",
            ]
        )

    lines.extend(
        [
            "",
            "if((MSVC OR FREEBSD_TARGET_DOS) AND COMMAND auto_win_msvc_transform_sources)",
            "    auto_win_msvc_transform_sources(",
            f'        OUTPUT_DIR "${{CMAKE_CURRENT_BINARY_DIR}}/transformed_{safe_id}"',
            f"        OUTPUT_VAR _FBSD_{safe_id.upper()}_ACTIVE_SOURCES",
            f"        SOURCES ${{_FBSD_{safe_id.upper()}_RAW_SOURCES}}",
            "    )",
            "else()",
            (
                f"    set(_FBSD_{safe_id.upper()}_ACTIVE_SOURCES "
                f"${{_FBSD_{safe_id.upper()}_RAW_SOURCES}})"
            ),
            "endif()",
            "",
            "if(_FBSD_STANDALONE_BINARY)",
            f'    set(_FBSD_TARGET "{spec.prog}")',
            "else()",
            f'    set(_FBSD_TARGET "fbsd_bin_{safe_id}")',
            "endif()",
            "",
            f"add_executable(${{_FBSD_TARGET}} ${{_FBSD_{safe_id.upper()}_ACTIVE_SOURCES}})",
            "set_target_properties(${_FBSD_TARGET} PROPERTIES",
            f'    OUTPUT_NAME "{spec.prog}"',
            '    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"',
            ")",
            "",
            "target_include_directories(${_FBSD_TARGET} BEFORE PRIVATE",
        ]
    )
    for inc in spec.include_dirs:
        lines.append(f'    "{_posix(inc)}"')
    if spec.yacc_sources or spec.lex_sources:
        lines.append(f"    ${{_FBSD_{safe_id.upper()}_CODEGEN_INC}}")
    lines.extend(
        [
            f'    "{gen_inc_posix}"',
            '    "${CMAKE_BINARY_DIR}/posix_includes"',
            ")",
            "if(DEFINED auto_win_msvc_SOURCE_DIR)",
            (
                "    target_include_directories(${_FBSD_TARGET} PRIVATE "
                '"${auto_win_msvc_SOURCE_DIR}/include")'
            ),
            "endif()",
            "",
            "target_compile_definitions(${_FBSD_TARGET} PRIVATE",
            (
                "    $<$<NOT:$<BOOL:${WIN32}>>:_GNU_SOURCE=1>"
                if spec.prog == "zstd"
                else "    _GNU_SOURCE=1"
            ),
            "    WITHOUT_CAPSICUM=1",
            "    WITHOUT_CASPER=1",
        ]
    )
    dos_str_defs: list[tuple[str, str]] = []
    bracket_defs: list[str] = []
    for cdef in spec.compile_defs:
        cleaned = re.sub(r"^([A-Za-z0-9_]+=)'(\".*\")'$", r"\1\2", cdef)
        cleaned = cleaned.replace('\\"', '"')
        if '"' in cleaned or "\\" in cleaned:
            eq_idx = cleaned.find("=")
            if eq_idx > 0:
                dos_str_defs.append((cleaned[:eq_idx], cleaned[eq_idx + 1 :]))
            bracket_defs.append(f"        [=[{cleaned}]=]")
        else:
            lines.append(f'    "{cleaned}"')
    lines.extend(
        [
            "    $<$<BOOL:${FREEBSD_TARGET_DOS}>:__DOS__=1>",
            "    $<$<BOOL:${MSVC}>:_CRT_SECURE_NO_WARNINGS>",
            "    $<$<BOOL:${MSVC}>:_CRT_NONSTDC_NO_DEPRECATE>",
            "    $<$<BOOL:${MSVC}>:_CRT_NONSTDC_NO_WARNINGS>",
            "    $<$<BOOL:${MSVC}>:_CRT_STDIO_ISO_WIDE_SPECIFIERS=1>",
            "    $<$<BOOL:${WIN32}>:WIN32_LEAN_AND_MEAN>",
            "    $<$<BOOL:${WIN32}>:NOMINMAX>",
            ")",
            "",
        ]
    )
    if bracket_defs:
        lines.append("if(NOT FREEBSD_TARGET_DOS)")
        lines.append("    target_compile_definitions(${_FBSD_TARGET} PRIVATE")
        lines.extend(bracket_defs)
        lines.append("    )")
        lines.append("endif()")
    lines.extend(
        [
            'set(_AWM_CFG "${CMAKE_BINARY_DIR}/posix_includes/auto-win-msvc-configure.h")',
            'set(_PREINC "${FREEBSD_GEN_DIR}/include/freebsd_compat_preinclude.h")',
            'if(EXISTS "${_AWM_CFG}")',
            "    if(FREEBSD_TARGET_DOS)",
            '        file(TO_NATIVE_PATH "${_AWM_CFG}" _AWM_NAT)',
            '        target_compile_options(${_FBSD_TARGET} PRIVATE "-fi=${_AWM_NAT}")',
            "    elseif(MSVC)",
            '        target_compile_options(${_FBSD_TARGET} PRIVATE "/FI${_AWM_CFG}")',
            "    else()",
            '        target_compile_options(${_FBSD_TARGET} PRIVATE "SHELL:-include ${_AWM_CFG}")',
            "    endif()",
            "endif()",
        ]
    )
    if dos_str_defs:
        hdr_body = LF.join(
            f"#ifndef {d_key}{LF}#define {d_key} {d_val}{LF}#endif" for d_key, d_val in dos_str_defs
        )
        lines.extend(
            [
                "if(FREEBSD_TARGET_DOS)",
                f'    set(_DOS_STRDEFS "${{CMAKE_CURRENT_BINARY_DIR}}/fbsd_strdefs_{safe_id}.h")',
                (
                    f'    file(WRITE "${{_DOS_STRDEFS}}" [=[{hdr_body}{LF}]=]'
                    f' "#include \\"${{_PREINC}}\\"\\n")'
                ),
                '    file(TO_NATIVE_PATH "${_DOS_STRDEFS}" _DOS_STRDEFS_NAT)',
                '    target_compile_options(${_FBSD_TARGET} PRIVATE "-fi=${_DOS_STRDEFS_NAT}")',
                'elseif(EXISTS "${_PREINC}")',
                "    if(MSVC)",
                '        target_compile_options(${_FBSD_TARGET} PRIVATE "/FI${_PREINC}")',
                "    else()",
                (
                    "        target_compile_options(${_FBSD_TARGET} PRIVATE "
                    '"SHELL:-include ${_PREINC}")'
                ),
                "    endif()",
                "endif()",
            ]
        )
    else:
        lines.extend(
            [
                'if(EXISTS "${_PREINC}")',
                "    if(FREEBSD_TARGET_DOS)",
                '        file(TO_NATIVE_PATH "${_PREINC}" _PRE_NAT)',
                '        target_compile_options(${_FBSD_TARGET} PRIVATE "-fi=${_PRE_NAT}")',
                "    elseif(MSVC)",
                '        target_compile_options(${_FBSD_TARGET} PRIVATE "/FI${_PREINC}")',
                "    else()",
                (
                    "        target_compile_options(${_FBSD_TARGET} PRIVATE "
                    '"SHELL:-include ${_PREINC}")'
                ),
                "    endif()",
                "endif()",
            ]
        )
    lines.extend(
        [
            "if(FREEBSD_TARGET_DOS)",
            (
                "    target_compile_options(${_FBSD_TARGET} PRIVATE "
                '"$<$<COMPILE_LANGUAGE:C>:-zastd=c99>" '
                '"$<$<COMPILE_LANGUAGE:C>:-ze>" '
                '"$<$<COMPILE_LANGUAGE:C>:-aa>" '
                '"-wcd=201" "-wcd=202")'
            ),
            '    target_link_options(${_FBSD_TARGET} PRIVATE "option" "stack=524288")',
            "elseif(MSVC)",
            (
                "    target_compile_options(${_FBSD_TARGET} PRIVATE "
                '"$<$<COMPILE_LANGUAGE:CXX>:/Zc:__cplusplus>" '
                + ('"$<$<COMPILE_LANGUAGE:C>:/Zc:__STDC__>" ' if spec.prog == "vacation" else "")
                + '"/wd4005" "/wd4244" "/wd4267" "/wd4996")'
            ),
            '    target_link_options(${_FBSD_TARGET} PRIVATE "/STACK:8388608")',
            "else()",
            (
                "    target_compile_options(${_FBSD_TARGET} PRIVATE "
                '"-Wno-unused-parameter" "-Wno-sign-compare" '
                '"$<$<AND:$<COMPILE_LANGUAGE:C>,$<C_COMPILER_ID:Clang,AppleClang>>:'
                '-Wno-incompatible-function-pointer-types>" '
                '"$<$<AND:$<COMPILE_LANGUAGE:C>,$<C_COMPILER_ID:GNU>>:'
                '-Wno-incompatible-pointer-types>")'
            ),
            "endif()",
            "",
            "if(TARGET fbsd_libcompat)",
            "    target_link_libraries(${_FBSD_TARGET} PRIVATE fbsd_libcompat)",
            "endif()",
            "if(TARGET auto-win-msvc)",
            "    target_link_libraries(${_FBSD_TARGET} PRIVATE auto-win-msvc)",
            "endif()",
            "if(WIN32)",
            "    target_link_libraries(${_FBSD_TARGET} PRIVATE bcrypt ws2_32)",
            "endif()",
            "if(UNIX)",
            "    target_link_libraries(${_FBSD_TARGET} PRIVATE m $<$<PLATFORM_ID:Darwin>:resolv>)",
            "endif()",
        ]
    )

    for s3_target in spec.section3_targets:
        lines.extend(
            [
                f"if(TARGET {s3_target})",
                f"    target_link_libraries(${{_FBSD_TARGET}} PRIVATE {s3_target})",
                "endif()",
            ]
        )

    if spec.section3_targets:
        lines.extend(
            [
                "if(WIN32 AND FREEBSD_SECTION3_SHARED)",
                "    add_custom_command(TARGET ${_FBSD_TARGET} POST_BUILD",
                (
                    '        COMMAND "${CMAKE_COMMAND}" -E '
                    '"$<IF:$<BOOL:$<TARGET_RUNTIME_DLLS:${_FBSD_TARGET}>>,'
                    'copy_if_different,true>"'
                ),
                "            $<TARGET_RUNTIME_DLLS:${_FBSD_TARGET}>",
                (
                    '            "$<$<BOOL:$<TARGET_RUNTIME_DLLS:${_FBSD_TARGET}>>:'
                    '$<TARGET_FILE_DIR:${_FBSD_TARGET}>>"'
                ),
                "        COMMAND_EXPAND_LISTS",
                "    )",
                "endif()",
            ]
        )

    for alias in spec.links:
        lines.extend(
            [
                "add_custom_command(TARGET ${_FBSD_TARGET} POST_BUILD",
                '    COMMAND "${CMAKE_COMMAND}" -E copy_if_different',
                '        "$<TARGET_FILE:${_FBSD_TARGET}>"',
                (
                    f'        "$<TARGET_FILE_DIR:${{_FBSD_TARGET}}>/'
                    f'{alias}${{CMAKE_EXECUTABLE_SUFFIX}}"'
                ),
                ")",
            ]
        )

    lines.extend(
        [
            "",
            f"install(TARGETS ${{_FBSD_TARGET}} RUNTIME DESTINATION bin COMPONENT {safe_id})",
            "install(TARGETS ${_FBSD_TARGET} RUNTIME DESTINATION bin COMPONENT suite)",
        ]
    )
    if spec.section3_targets:
        lines.extend(
            [
                "if(WIN32 AND FREEBSD_SECTION3_SHARED)",
                "    install(FILES $<TARGET_RUNTIME_DLLS:${_FBSD_TARGET}>",
                f"        DESTINATION bin COMPONENT {safe_id})",
                "endif()",
            ]
        )

    lines.extend(
        [
            "",
            "if(_FBSD_STANDALONE_BINARY)",
            "    include(CTest)",
            "    if(BUILD_TESTING AND NOT FREEBSD_TARGET_DOS)",
            f"        add_test(NAME {safe_id}_exists",
            '            COMMAND "${CMAKE_COMMAND}" -E true',
            "        )",
            "    endif()",
            f'    set(CPACK_PACKAGE_NAME "freebsd-usr-bin-{spec.prog}")',
            '    set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")',
            "    include(CPack)",
            "endif()",
            "",
        ]
    )
    return LF.join(lines)


def generate_per_binary_cmake(
    spec: BinarySpec,
    repo_root: Path,
    freebsd_src: Path,
    generated_dir: Path,
) -> Path:
    """Write ``${FREEBSD_GEN_DIR}/per_binary/<prog>/CMakeLists.txt`` for ``spec``.

    Args:
        spec: Concrete ``BinarySpec`` to emit.
        repo_root: Root directory of ``freebsd-usr-bin-windows``.
        freebsd_src: Root directory of ``../freebsd-src``.
        generated_dir: Out-of-tree ``freebsd_generated`` directory.

    Returns:
        Resolved ``Path`` to the written ``CMakeLists.txt``.
    """
    content = render_per_binary_cmakelists(spec, repo_root, freebsd_src, generated_dir)
    out_file = (generated_dir / "per_binary" / spec.prog / "CMakeLists.txt").resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(content, encoding="utf-8")
    return out_file


def emit_all_per_binary_cmake(
    binaries: Sequence[BinarySpec],
    repo_root: Path,
    freebsd_src: Path,
    generated_dir: Path,
) -> tuple[Path, tuple[Path, ...]]:
    """Emit ``per_binary/<prog>/CMakeLists.txt`` for all binaries and ``per_binary_subdirs.cmake``.

    Args:
        binaries: Sequence of all parsed ``BinarySpec`` items.
        repo_root: Root directory of ``freebsd-usr-bin-windows``.
        freebsd_src: Root directory of ``../freebsd-src``.
        generated_dir: Out-of-tree ``freebsd_generated`` directory.

    Returns:
        Tuple of ``(subdirs_cmake_path, tuple_of_per_binary_cmakelists_paths)``.
    """
    generated_dir.mkdir(parents=True, exist_ok=True)
    compilable = [b for b in binaries if b.sources or b.yacc_sources or b.lex_sources]
    written: list[Path] = []
    index_lines = [
        "# Automatically generated by scripts/per_binary_cmake.py",
        "set(FREEBSD_PER_BINARY_PROGS",
    ]
    for spec in compilable:
        index_lines.append(f'    "{spec.prog}"')
    index_lines.append(")")
    index_lines.append("")

    for spec in compilable:
        cm_path = generate_per_binary_cmake(spec, repo_root, freebsd_src, generated_dir)
        written.append(cm_path)
        safe_id = sanitize_applet_id(spec.prog)
        sub_src = _posix(cm_path.parent)
        index_lines.extend(
            [
                (
                    "if(NOT DEFINED FREEBSD_ENABLED_BINARIES "
                    f'OR "{spec.prog}" IN_LIST FREEBSD_ENABLED_BINARIES)'
                ),
                (
                    f'    add_subdirectory("{sub_src}" '
                    f'"${{CMAKE_BINARY_DIR}}/per_binary_build/{safe_id}")'
                ),
                "endif()",
            ]
        )

    index_path = (generated_dir / "per_binary_subdirs.cmake").resolve()
    index_path.write_text(LF.join(index_lines) + LF, encoding="utf-8")
    return index_path, tuple(written)
