#[=======================================================================[.rst:
FreeBsdBootstrapTools
---------------------

Host-native bootstrap tool detection and build rules for FreeBSD ``usr.bin``
cross-compilation (MSVC ``ARM64`` / ``X86`` and OpenWatcom 32-bit DOS).

Provides:
  - ``freebsd_detect_host_cc``: Locates a native C compiler executable capable
    of producing runnable binaries on ``CMAKE_HOST_SYSTEM_NAME`` even when
    ``CMAKE_C_COMPILER`` is a cross-compiler (such as ``wcl386`` for DOS).
  - ``freebsd_ensure_bootstrap_tools``: Discovers or compiles host-native
    ``host_byacc`` (``contrib/byacc``) and system ``flex``/``lex`` inside
    ``${CMAKE_BINARY_DIR}/host_tools``, and records ``FREEBSD_MAKETAB_SRC``
    (``contrib/one-true-awk/maketab.c``) for ``awk`` code generation.
  - ``freebsd_compile_yacc_lex``: Processes ``.y`` grammars and ``.l`` scanners
    into ``${FREEBSD_GEN_DIR}/codegen/<target_id>/`` at configure or build time.
#]=======================================================================]

include_guard(GLOBAL)

# -----------------------------------------------------------------------------
# freebsd_detect_host_cc(OUT_VAR <var>)
#
# Arguments:
#   OUT_VAR : Name of variable in PARENT_SCOPE receiving host C compiler path.
# -----------------------------------------------------------------------------
function(freebsd_detect_host_cc)
    set(options "")
    set(oneValueArgs OUT_VAR)
    set(multiValueArgs "")
    cmake_parse_arguments(ARG "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    if(DEFINED ENV{HOST_CC} AND NOT "$ENV{HOST_CC}" STREQUAL "")
        find_program(_FBSD_HOST_CC NAMES "$ENV{HOST_CC}")
    endif()
    if(NOT _FBSD_HOST_CC)
        if(CMAKE_HOST_WIN32)
            find_program(_FBSD_HOST_CC NAMES cl clang gcc cc)
        else()
            find_program(_FBSD_HOST_CC NAMES cc clang gcc)
        endif()
    endif()
    if(ARG_OUT_VAR)
        set(${ARG_OUT_VAR} "${_FBSD_HOST_CC}" PARENT_SCOPE)
    endif()
endfunction()

# -----------------------------------------------------------------------------
# freebsd_ensure_bootstrap_tools(
#     FREEBSD_SRC_DIR <dir>
#     OUT_DIR         <dir>
# )
#
# Arguments:
#   FREEBSD_SRC_DIR : Path to upstream freebsd-src root directory.
#   OUT_DIR         : Destination directory for host_tools executables.
# -----------------------------------------------------------------------------
function(freebsd_ensure_bootstrap_tools)
    set(options "")
    set(oneValueArgs FREEBSD_SRC_DIR OUT_DIR)
    set(multiValueArgs "")
    cmake_parse_arguments(ARG "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    file(MAKE_DIRECTORY "${ARG_OUT_DIR}")
    freebsd_detect_host_cc(OUT_VAR _HOST_CC)

    find_program(_SYS_YACC NAMES byacc yacc bison win_bison)
    find_program(_SYS_LEX NAMES flex lex win_flex)

    if(_SYS_YACC)
        set(FREEBSD_HOST_YACC "${_SYS_YACC}" CACHE FILEPATH "Host yacc/byacc binary" FORCE)
    endif()
    if(_SYS_LEX)
        set(FREEBSD_HOST_LEX "${_SYS_LEX}" CACHE FILEPATH "Host flex/lex binary" FORCE)
    endif()

    # Build authentic Berkeley host_byacc from contrib/byacc when available
    set(_BYACC_DIR "${ARG_FREEBSD_SRC_DIR}/contrib/byacc")
    set(_HOST_BYACC_BIN "${ARG_OUT_DIR}/host_byacc${CMAKE_HOST_EXECUTABLE_SUFFIX}")
    if(_HOST_CC AND EXISTS "${_BYACC_DIR}/main.c")
        if(NOT EXISTS "${_HOST_BYACC_BIN}")
            set(_BYACC_SRCS
                "${_BYACC_DIR}/closure.c" "${_BYACC_DIR}/error.c" "${_BYACC_DIR}/graph.c"
                "${_BYACC_DIR}/lalr.c" "${_BYACC_DIR}/lr0.c" "${_BYACC_DIR}/main.c"
                "${_BYACC_DIR}/mkpar.c" "${_BYACC_DIR}/mstring.c" "${_BYACC_DIR}/output.c"
                "${_BYACC_DIR}/reader.c" "${_BYACC_DIR}/yaccpar.c" "${_BYACC_DIR}/symtab.c"
                "${_BYACC_DIR}/verbose.c" "${_BYACC_DIR}/warshall.c"
            )
            if(NOT CMAKE_HOST_WIN32)
                execute_process(
                    COMMAND "${_HOST_CC}" -O2 "-I${_BYACC_DIR}"
                            -DMAXTABLE=INT_MAX -DYYPATCH=20230201
                            ${_BYACC_SRCS} -o "${_HOST_BYACC_BIN}"
                    RESULT_VARIABLE _BYACC_RC
                    OUTPUT_QUIET ERROR_QUIET
                )
            elseif(NOT _SYS_YACC MATCHES "byacc"
                   AND _HOST_CC MATCHES "cl(\\.exe)?$"
                   AND NOT (CMAKE_C_COMPILER_ARCHITECTURE_ID MATCHES "ARM64"
                            AND NOT CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "ARM64"))
                execute_process(
                    COMMAND "${_HOST_CC}" /nologo /O2
                            /D_CRT_SECURE_NO_WARNINGS /D_CRT_NONSTDC_NO_DEPRECATE
                            "-I${_BYACC_DIR}" -DMAXTABLE=INT_MAX -DYYPATCH=20230201
                            ${_BYACC_SRCS} "/Fe:${_HOST_BYACC_BIN}"
                    WORKING_DIRECTORY "${ARG_OUT_DIR}"
                    RESULT_VARIABLE _BYACC_RC
                    OUTPUT_QUIET ERROR_QUIET
                )
            endif()
        endif()
        if(EXISTS "${_HOST_BYACC_BIN}")
            set(FREEBSD_HOST_YACC "${_HOST_BYACC_BIN}" CACHE FILEPATH "Built host_byacc" FORCE)
        endif()
    endif()

    set(FREEBSD_MAKETAB_SRC "${ARG_FREEBSD_SRC_DIR}/contrib/one-true-awk/maketab.c"
        CACHE FILEPATH "Upstream awk maketab.c source" FORCE)
endfunction()

# -----------------------------------------------------------------------------
# freebsd_compile_yacc_lex(
#     TARGET_ID         <id>
#     OUT_DIR           <dir>
#     [YACC_SOURCES     <y1> <y2> ...]
#     [LEX_SOURCES      <l1> <l2> ...]
#     OUT_SOURCES_VAR   <var>
#     [OUT_HEADERS_VAR  <var>]
#     OUT_INC_VAR       <var>
# )
#
# Arguments:
#   TARGET_ID       : Sanitized target identifier stem.
#   OUT_DIR         : Destination directory for generated .c/.h outputs.
#   YACC_SOURCES    : Input .y grammar file paths.
#   LEX_SOURCES     : Input .l scanner file paths.
#   OUT_SOURCES_VAR : Variable in PARENT_SCOPE receiving generated .c files.
#   OUT_HEADERS_VAR : Optional variable in PARENT_SCOPE receiving generated .h files.
#   OUT_INC_VAR     : Variable in PARENT_SCOPE receiving generated include dir.
# -----------------------------------------------------------------------------
function(freebsd_compile_yacc_lex)
    set(options "")
    set(oneValueArgs TARGET_ID OUT_DIR OUT_SOURCES_VAR OUT_HEADERS_VAR OUT_INC_VAR)
    set(multiValueArgs YACC_SOURCES LEX_SOURCES)
    cmake_parse_arguments(ARG "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    file(MAKE_DIRECTORY "${ARG_OUT_DIR}")
    set(_GEN_SRCS "")
    set(_YACC_HDRS "")

    foreach(_YFILE IN LISTS ARG_YACC_SOURCES)
        get_filename_component(_YSTEM "${_YFILE}" NAME_WE)
        set(_OUT_C "${ARG_OUT_DIR}/${_YSTEM}.tab.c")
        set(_OUT_H "${ARG_OUT_DIR}/${_YSTEM}.tab.h")
        set(_YTAB_H "${ARG_OUT_DIR}/y.tab.h")
        set(_STEM_H "${ARG_OUT_DIR}/${_YSTEM}.h")
        set(_EXTRA_HDRS "${_YTAB_H}")
        if(NOT "${_STEM_H}" STREQUAL "${_YTAB_H}")
            list(APPEND _EXTRA_HDRS "${_STEM_H}")
        endif()
        if(FREEBSD_HOST_YACC)
            get_filename_component(_YNAME "${FREEBSD_HOST_YACC}" NAME_WE)
            if(_YNAME MATCHES "bison")
                add_custom_command(
                    OUTPUT "${_OUT_C}" "${_OUT_H}" ${_EXTRA_HDRS}
                    COMMAND "${FREEBSD_HOST_YACC}" -y -d -o "${_OUT_C}" "${_YFILE}"
                    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${_OUT_H}" "${_YTAB_H}"
                    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${_OUT_H}" "${_STEM_H}"
                    DEPENDS "${_YFILE}"
                    COMMENT "Generating parser ${_YSTEM}.tab.c via bison -y"
                )
            else()
                add_custom_command(
                    OUTPUT "${_OUT_C}" "${_OUT_H}" ${_EXTRA_HDRS}
                    COMMAND "${FREEBSD_HOST_YACC}" -d -o "${_OUT_C}" "${_YFILE}"
                    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${_OUT_H}" "${_YTAB_H}"
                    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${_OUT_H}" "${_STEM_H}"
                    DEPENDS "${_YFILE}"
                    COMMENT "Generating parser ${_YSTEM}.tab.c via yacc/byacc"
                )
            endif()
            list(APPEND _GEN_SRCS "${_OUT_C}")
            list(APPEND _YACC_HDRS "${_OUT_H}" ${_EXTRA_HDRS})

            if(_YSTEM STREQUAL "awkgram" AND EXISTS "${FREEBSD_MAKETAB_SRC}")
                get_filename_component(_FBSD_BOOT_REPO_ROOT "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." REALPATH)
                find_program(_FBSD_BOOT_PY3 NAMES "${Python3_EXECUTABLE}" python3 python)
                set(_PROCTAB_C "${ARG_OUT_DIR}/proctab.c")
                if(_FBSD_BOOT_PY3)
                    add_custom_command(
                        OUTPUT "${_PROCTAB_C}"
                        COMMAND "${_FBSD_BOOT_PY3}" -c
                            "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from scripts.codegen_helpers import emit_awk_proctab_c; emit_awk_proctab_c(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))"
                            "${_FBSD_BOOT_REPO_ROOT}" "${_OUT_H}" "${FREEBSD_MAKETAB_SRC}" "${_PROCTAB_C}"
                        DEPENDS "${_OUT_H}" "${FREEBSD_MAKETAB_SRC}"
                        COMMENT "Generating awk proctab.c via emit_awk_proctab_c"
                        VERBATIM
                    )
                    list(APPEND _GEN_SRCS "${_PROCTAB_C}")
                endif()
            endif()
        endif()
    endforeach()

    foreach(_LFILE IN LISTS ARG_LEX_SOURCES)
        get_filename_component(_LSTEM "${_LFILE}" NAME_WE)
        set(_OUT_LC "${ARG_OUT_DIR}/${_LSTEM}.yy.c")
        if(FREEBSD_HOST_LEX)
            add_custom_command(
                OUTPUT "${_OUT_LC}"
                COMMAND "${FREEBSD_HOST_LEX}" -o "${_OUT_LC}" "${_LFILE}"
                DEPENDS "${_LFILE}" ${_YACC_HDRS}
                COMMENT "Generating scanner ${_LSTEM}.yy.c via flex/lex"
            )
            list(APPEND _GEN_SRCS "${_OUT_LC}")
        endif()
    endforeach()

    if(ARG_OUT_SOURCES_VAR)
        set(${ARG_OUT_SOURCES_VAR} "${_GEN_SRCS}" PARENT_SCOPE)
    endif()
    if(ARG_OUT_HEADERS_VAR)
        set(${ARG_OUT_HEADERS_VAR} "${_YACC_HDRS}" PARENT_SCOPE)
    endif()
    if(ARG_OUT_INC_VAR)
        set(${ARG_OUT_INC_VAR} "${ARG_OUT_DIR}" PARENT_SCOPE)
    endif()
endfunction()
