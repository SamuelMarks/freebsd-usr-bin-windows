#[=======================================================================[.rst:
FreeBsdInternalLibs
-------------------

Builds true FreeBSD Section 3 backing libraries (``lib/*`` and ``contrib/*``)
for ``usr.bin`` executables while preserving Section 1 utilities strictly as
CLI executables (e.g., ``printf(3)`` from CRT/``auto-win-msvc`` vs. ``printf(1)``
executable from ``usr.bin/printf``).

Platform linkage model:
  - **Windows (MSVC ``X64``, ``X86``, ``ARM64``) & Unix**: Built as ``SHARED``
    libraries (``.dll`` + ``.lib`` import library + SDK headers) when
    ``FREEBSD_SECTION3_SHARED=ON``, using ``CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON``
    plus optional generated ``.def`` files for ``DATA`` exports so zero ``.c``
    or ``.h`` files in ``../freebsd-src`` are modified.
  - **32-bit Protected-Mode DOS (OpenWatcom, ``FREEBSD_TARGET_DOS=ON``)**:
    Built as ``STATIC`` libraries (``.lib``) because DOS ``LE`` executables do
    not load Win32 PE DLLs.

Supports ``FREEBSD_REQUIRED_SECTION3_LIBS`` filtering so standalone per-binary
``CMakeLists.txt`` builds compile only the transitive Section 3 dependencies
required by that single utility.
#]=======================================================================]

include_guard(GLOBAL)

if(MSVC AND NOT CMAKE_HOST_WIN32 AND NOT CMAKE_NM)
    find_program(_FBSD_S3_HOST_NM
        NAMES llvm-nm x86_64-w64-mingw32-nm nm
        PATHS /opt/homebrew/opt/llvm/bin /usr/local/opt/llvm/bin
    )
    if(_FBSD_S3_HOST_NM)
        set(CMAKE_NM "${_FBSD_S3_HOST_NM}" CACHE FILEPATH "Path to nm for WINDOWS_EXPORT_ALL_SYMBOLS" FORCE)
    endif()
endif()

if(NOT DEFINED FREEBSD_SECTION3_SHARED)
    if(FREEBSD_TARGET_DOS)
        set(FREEBSD_SECTION3_SHARED OFF)
    else()
        set(FREEBSD_SECTION3_SHARED ON)
    endif()
endif()

set(_FBSD_S3_GEN_DIR "${CMAKE_BINARY_DIR}/freebsd_generated/section3")
file(MAKE_DIRECTORY "${_FBSD_S3_GEN_DIR}/include")
file(MAKE_DIRECTORY "${_FBSD_S3_GEN_DIR}/src")
file(MAKE_DIRECTORY "${_FBSD_S3_GEN_DIR}/defs")

if(DEFINED FREEBSD_GEN_DIR AND EXISTS "${FREEBSD_GEN_DIR}/codegen")
    set(_FBSD_CODEGEN_DIR "${FREEBSD_GEN_DIR}/codegen")
    set(_FBSD_GEN_BASE "${FREEBSD_GEN_DIR}")
else()
    set(_FBSD_GEN_BASE "${CMAKE_BINARY_DIR}/freebsd_generated")
    set(_FBSD_CODEGEN_DIR "${_FBSD_GEN_BASE}/codegen")
endif()
if(NOT DEFINED FREEBSD_GEN_INC)
    set(FREEBSD_GEN_INC "${_FBSD_GEN_BASE}/include")
endif()

get_filename_component(_FBSD_INTERNAL_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." REALPATH)
if(NOT EXISTS "${_FBSD_CODEGEN_DIR}/ncurses/fbsd_curses.c" AND DEFINED FREEBSD_SRC_DIR AND EXISTS "${FREEBSD_SRC_DIR}")
    find_program(_FBSD_S3_PY3 NAMES "${Python3_EXECUTABLE}" python3 python)
    if(_FBSD_S3_PY3 AND EXISTS "${_FBSD_INTERNAL_REPO_ROOT}/scripts/codegen_helpers.py")
        include("${CMAKE_CURRENT_LIST_DIR}/GenerateFreeBsdHeaders.cmake")
        if(NOT EXISTS "${_FBSD_GEN_BASE}/include/freebsd_compat_preinclude.h")
            freebsd_emit_compat_headers(
                INC_DIR "${_FBSD_GEN_BASE}/include"
                FREEBSD_SRC_DIR "${FREEBSD_SRC_DIR}"
            )
        endif()
        execute_process(
            COMMAND "${_FBSD_S3_PY3}" -c
                "import sys; from pathlib import Path; sys.path.insert(0, '${_FBSD_INTERNAL_REPO_ROOT}'); from scripts.codegen_helpers import emit_all_codegen_helpers; emit_all_codegen_helpers(Path('${FREEBSD_SRC_DIR}'), Path('${_FBSD_GEN_BASE}'))"
            RESULT_VARIABLE _s3_cg_rc
        )
    endif()
endif()

# -----------------------------------------------------------------------------
# _fbsd_should_build_section3(<target> <out_var>)
#
# Checks whether <target> is requested when FREEBSD_REQUIRED_SECTION3_LIBS is set.
#
# Arguments:
#   _target  : Canonical Section 3 CMake target name (e.g. fbsd_libutil).
#   _out_var : Variable in PARENT_SCOPE receiving TRUE or FALSE.
# -----------------------------------------------------------------------------
function(_fbsd_should_build_section3 _target _out_var)
    if(TARGET "${_target}")
        set(${_out_var} FALSE PARENT_SCOPE)
        return()
    endif()
    if(NOT DEFINED FREEBSD_REQUIRED_SECTION3_LIBS OR "${FREEBSD_REQUIRED_SECTION3_LIBS}" STREQUAL "")
        set(${_out_var} TRUE PARENT_SCOPE)
        return()
    endif()
    if("${_target}" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        set(${_out_var} TRUE PARENT_SCOPE)
    else()
        set(${_out_var} FALSE PARENT_SCOPE)
    endif()
endfunction()

# Expand transitive dependencies inside FREEBSD_REQUIRED_SECTION3_LIBS if set
if(DEFINED FREEBSD_REQUIRED_SECTION3_LIBS AND NOT "${FREEBSD_REQUIRED_SECTION3_LIBS}" STREQUAL "")
    if("fbsd_libarchive" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS
            fbsd_libz fbsd_libbz2 fbsd_liblzma fbsd_libzstd fbsd_libbsdxml fbsd_libmd)
    endif()
    if("fbsd_libmagic" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS
            fbsd_libz fbsd_libbz2 fbsd_liblzma fbsd_libzstd)
    endif()
    if("fbsd_liblzma" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS fbsd_libmd)
    endif()
    if("fbsd_libfetch" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS fbsd_libmd)
    endif()
    if("fbsd_libelftc" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS fbsd_libz)
    endif()
    if("fbsd_libbsddialog" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS fbsd_libcurses fbsd_libtinfow)
    endif()
    if("fbsd_libdpv" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS
            fbsd_libdialog fbsd_libfigpar fbsd_libutil fbsd_libcurses fbsd_libtinfow)
    endif()
    if("fbsd_libdialog" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS fbsd_libcurses fbsd_libtinfow)
    endif()
    if("fbsd_libcurses" IN_LIST FREEBSD_REQUIRED_SECTION3_LIBS)
        list(APPEND FREEBSD_REQUIRED_SECTION3_LIBS fbsd_libtinfow)
    endif()
    list(REMOVE_DUPLICATES FREEBSD_REQUIRED_SECTION3_LIBS)
endif()

# -----------------------------------------------------------------------------
# _fbsd_resolve_staged_or_upstream(<out_var> <rel_path>)
#
# Resolves <rel_path> to ${FREEBSD_GEN_DIR}/staged_src/<rel_path> if a
# declarative patch was applied, otherwise ${FREEBSD_SRC_DIR}/<rel_path>.
#
# Arguments:
#   _out_var  : Variable in PARENT_SCOPE receiving the resolved source path.
#   _rel_path : Path relative to upstream freebsd-src root.
# -----------------------------------------------------------------------------
function(_fbsd_resolve_staged_or_upstream _out_var _rel_path)
    if(EXISTS "${_FBSD_GEN_BASE}/staged_src/${_rel_path}")
        set(${_out_var} "${_FBSD_GEN_BASE}/staged_src/${_rel_path}" PARENT_SCOPE)
    else()
        set(${_out_var} "${FREEBSD_SRC_DIR}/${_rel_path}" PARENT_SCOPE)
    endif()
endfunction()

# -----------------------------------------------------------------------------
# freebsd_add_section3_library(
#     <target>
#     OUTPUT_NAME     <name>
#     SOURCES         <src1> [<src2> ...]
#     [INCLUDES       <dir1> ...]
#     [DEFINES        <def1> ...]
#     [LIBS           <lib1> ...]
#     [DATA_EXPORTS   <sym1> ...]
#     [PUBLIC_HEADERS <hdr1> ...]
#     [NO_GNU_SOURCE]
# )
#
# Arguments:
#   target         : Canonical CMake target name (e.g. fbsd_libutil).
#   OUTPUT_NAME    : Base library output name without lib/dll suffix.
#   SOURCES        : C source files to compile into the Section 3 library.
#   INCLUDES       : Public/private include directories.
#   DEFINES        : Preprocessor definitions for compiling the library.
#   LIBS           : Dependent targets/libraries to link publicly.
#   DATA_EXPORTS   : Optional global variable symbols exported as DATA in .def.
#   PUBLIC_HEADERS : Public Section 3 header files installed into include/ (sdk).
#   NO_GNU_SOURCE  : Omit _GNU_SOURCE=1 on WIN32 (e.g., for zstd qsort_s).
# -----------------------------------------------------------------------------
function(freebsd_add_section3_library _TARGET)
    set(options NO_GNU_SOURCE)
    set(oneValueArgs OUTPUT_NAME)
    set(multiValueArgs SOURCES INCLUDES DEFINES LIBS DATA_EXPORTS PUBLIC_HEADERS)
    cmake_parse_arguments(ARG "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    _fbsd_should_build_section3("${_TARGET}" _DO_BUILD)
    if(NOT _DO_BUILD)
        return()
    endif()

    if(FREEBSD_SECTION3_SHARED AND NOT FREEBSD_TARGET_DOS)
        set(_LIB_TYPE SHARED)
    else()
        set(_LIB_TYPE STATIC)
    endif()

    if((MSVC OR FREEBSD_TARGET_DOS) AND COMMAND auto_win_msvc_transform_sources)
        auto_win_msvc_transform_sources(
            OUTPUT_DIR "${CMAKE_BINARY_DIR}/transformed_s3_${_TARGET}"
            OUTPUT_VAR _ACTIVE_S3_SRCS
            SOURCES ${ARG_SOURCES}
        )
    else()
        set(_ACTIVE_S3_SRCS ${ARG_SOURCES})
    endif()

    if(MSVC AND _LIB_TYPE STREQUAL "SHARED" AND ARG_DATA_EXPORTS)
        set(_DEF_FILE "${_FBSD_S3_GEN_DIR}/defs/${_TARGET}.def")
        string(CONFIGURE [=[LIBRARY "@ARG_OUTPUT_NAME@"
EXPORTS
]=] _DEF_CONTENT @ONLY)
        foreach(_DSYM IN LISTS ARG_DATA_EXPORTS)
            string(APPEND _DEF_CONTENT "    ${_DSYM} DATA
")
        endforeach()
        file(WRITE "${_DEF_FILE}" "${_DEF_CONTENT}")
        list(APPEND _ACTIVE_S3_SRCS "${_DEF_FILE}")
    endif()

    add_library(${_TARGET} ${_LIB_TYPE} ${_ACTIVE_S3_SRCS})
    if(MINGW AND _LIB_TYPE STREQUAL "SHARED")
        target_link_options(${_TARGET} PRIVATE "-Wl,--export-all-symbols")
    endif()
    set_target_properties(${_TARGET} PROPERTIES
        OUTPUT_NAME "${ARG_OUTPUT_NAME}"
        WINDOWS_EXPORT_ALL_SYMBOLS ON
        POSITION_INDEPENDENT_CODE ON
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
        ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    )

    target_include_directories(${_TARGET} BEFORE PUBLIC
        ${ARG_INCLUDES}
        "${_FBSD_S3_GEN_DIR}/include"
    )
    if(EXISTS "${_FBSD_GEN_BASE}/include")
        target_include_directories(${_TARGET} PRIVATE "${_FBSD_GEN_BASE}/include")
    endif()
    if(EXISTS "${CMAKE_BINARY_DIR}/posix_includes")
        target_include_directories(${_TARGET} PRIVATE "${CMAKE_BINARY_DIR}/posix_includes")
    endif()
    if(DEFINED auto_win_msvc_SOURCE_DIR AND EXISTS "${auto_win_msvc_SOURCE_DIR}/include")
        target_include_directories(${_TARGET} PRIVATE "${auto_win_msvc_SOURCE_DIR}/include")
    endif()

    set(_GNU_DEF "_GNU_SOURCE=1")
    if(ARG_NO_GNU_SOURCE AND WIN32)
        set(_GNU_DEF "")
    endif()

    target_compile_definitions(${_TARGET} PRIVATE
        WITHOUT_CAPSICUM=1
        WITHOUT_CASPER=1
        ${_GNU_DEF}
        ${ARG_DEFINES}
        $<$<BOOL:${FREEBSD_TARGET_DOS}>:__DOS__=1>
        $<$<BOOL:${MSVC}>:_CRT_SECURE_NO_WARNINGS>
        $<$<BOOL:${MSVC}>:_CRT_NONSTDC_NO_DEPRECATE>
        $<$<BOOL:${MSVC}>:_CRT_NONSTDC_NO_WARNINGS>
        $<$<BOOL:${WIN32}>:WIN32_LEAN_AND_MEAN>
        $<$<BOOL:${WIN32}>:NOMINMAX>
    )

    set(_S3_AWM_CFG "${CMAKE_BINARY_DIR}/posix_includes/auto-win-msvc-configure.h")
    set(_S3_PREINC "${_FBSD_GEN_BASE}/include/freebsd_compat_preinclude.h")
    if(EXISTS "${_S3_AWM_CFG}" AND EXISTS "${_S3_PREINC}")
        if(FREEBSD_TARGET_DOS)
            file(TO_NATIVE_PATH "${_S3_AWM_CFG}" _S3_AWM_NAT)
            file(TO_NATIVE_PATH "${_S3_PREINC}" _S3_PRE_NAT)
            target_compile_options(${_TARGET} PRIVATE
                "$<$<COMPILE_LANGUAGE:C>:-zastd=c99>"
                "$<$<COMPILE_LANGUAGE:C>:-ze>"
                "$<$<COMPILE_LANGUAGE:C>:-aa>"
                "-fi=${_S3_AWM_NAT}"
                "-fi=${_S3_PRE_NAT}"
                "-wcd=201"
                "-wcd=202"
            )
        elseif(MSVC)
            target_compile_options(${_TARGET} PRIVATE "/FI${_S3_AWM_CFG}" "/FI${_S3_PREINC}" "/wd4005" "/wd4244" "/wd4267" "/wd4716" "/wd4996")
        else()
            target_compile_options(${_TARGET} PRIVATE
                "SHELL:-include ${_S3_AWM_CFG}"
                "SHELL:-include ${_S3_PREINC}"
                "-Wno-unused-parameter"
                "-Wno-sign-compare"
                "$<$<AND:$<COMPILE_LANGUAGE:C>,$<C_COMPILER_ID:Clang,AppleClang>>:-Wno-incompatible-function-pointer-types>"
                "$<$<AND:$<COMPILE_LANGUAGE:C>,$<C_COMPILER_ID:GNU>>:-Wno-incompatible-pointer-types>"
            )
        endif()
    endif()

    set_target_properties(${_TARGET} PROPERTIES
        C_STANDARD 11
        C_STANDARD_REQUIRED OFF
    )
    if(TARGET fbsd_libcompat)
        target_link_libraries(${_TARGET} PRIVATE fbsd_libcompat)
    elseif(EXISTS "${_FBSD_GEN_BASE}/src/freebsd_libcompat.c")
        target_sources(${_TARGET} PRIVATE "${_FBSD_GEN_BASE}/src/freebsd_libcompat.c")
    endif()
    if(TARGET auto-win-msvc)
        target_link_libraries(${_TARGET} PUBLIC auto-win-msvc)
    endif()
    if(ARG_LIBS)
        target_link_libraries(${_TARGET} PUBLIC ${ARG_LIBS})
    endif()

    install(TARGETS ${_TARGET}
        RUNTIME DESTINATION bin COMPONENT sdk
        LIBRARY DESTINATION lib COMPONENT sdk
        ARCHIVE DESTINATION lib COMPONENT sdk
    )
    if(_LIB_TYPE STREQUAL "SHARED")
        install(TARGETS ${_TARGET}
            RUNTIME DESTINATION bin COMPONENT suite
            LIBRARY DESTINATION lib COMPONENT suite
        )
    endif()
    if(ARG_PUBLIC_HEADERS)
        foreach(_HDR IN LISTS ARG_PUBLIC_HEADERS)
            if(EXISTS "${_HDR}")
                install(FILES "${_HDR}"
                    DESTINATION include
                    COMPONENT sdk
                )
            endif()
        endforeach()
    endif()
endfunction()

# -----------------------------------------------------------------------------
# _fbsd_define_portable_s3_unit(
#     <target> <out_name> <hdr_name> <hdr_body> <c_body> [extra_args...]
# )
#
# Helper to emit a portable C89 Section 3 backing unit + public header when
# synthetic test trees omit upstream FreeBSD sources.
#
# Arguments:
#   _TARGET   : Canonical Section 3 CMake target name.
#   _OUT_NAME : Base library output filename stem.
#   _HDR_NAME : Relative header path emitted under section3/include/.
#   _HDR_BODY : Public C89 header file contents.
#   _C_BODY   : Portable C89 source file contents.
# -----------------------------------------------------------------------------
function(_fbsd_define_portable_s3_unit _TARGET _OUT_NAME _HDR_NAME _HDR_BODY _C_BODY)
    set(_H_PATH "${_FBSD_S3_GEN_DIR}/include/${_HDR_NAME}")
    set(_C_PATH "${_FBSD_S3_GEN_DIR}/src/${_TARGET}.c")
    get_filename_component(_H_DIR "${_H_PATH}" DIRECTORY)
    file(MAKE_DIRECTORY "${_H_DIR}")
    file(WRITE "${_H_PATH}" "${_HDR_BODY}
")
    file(WRITE "${_C_PATH}" "${_C_BODY}
")
    freebsd_add_section3_library(${_TARGET}
        OUTPUT_NAME "${_OUT_NAME}"
        SOURCES "${_C_PATH}"
        PUBLIC_HEADERS "${_H_PATH}"
        ${ARGN}
    )
endfunction()

# =============================================================================
# 1. Core Compression & XML Libraries (fbsd_libz, fbsd_libbz2, fbsd_libbsdxml)
# =============================================================================
set(_ZLIB_DIR "${FREEBSD_SRC_DIR}/sys/contrib/zlib")
if(EXISTS "${_ZLIB_DIR}/zlib.h")
    set(_ZLIB_SRCS
        "${_ZLIB_DIR}/adler32.c" "${_ZLIB_DIR}/compress.c" "${_ZLIB_DIR}/crc32.c"
        "${_ZLIB_DIR}/deflate.c" "${_ZLIB_DIR}/gzclose.c" "${_ZLIB_DIR}/gzlib.c"
        "${_ZLIB_DIR}/gzread.c" "${_ZLIB_DIR}/gzwrite.c" "${_ZLIB_DIR}/infback.c"
        "${_ZLIB_DIR}/inffast.c" "${_ZLIB_DIR}/inflate.c" "${_ZLIB_DIR}/inftrees.c"
        "${_ZLIB_DIR}/trees.c" "${_ZLIB_DIR}/uncompr.c" "${_ZLIB_DIR}/zutil.c"
    )
    freebsd_add_section3_library(fbsd_libz
        OUTPUT_NAME "fbsd_z"
        SOURCES ${_ZLIB_SRCS}
        INCLUDES "${_ZLIB_DIR}"
        DEFINES $<$<NOT:$<OR:$<BOOL:${WIN32}>,$<BOOL:${FREEBSD_TARGET_DOS}>>>:HAVE_UNISTD_H=1>
                $<$<NOT:$<OR:$<BOOL:${WIN32}>,$<BOOL:${FREEBSD_TARGET_DOS}>>>:O_BINARY=0>
                HAVE_STDARG_H=1
        PUBLIC_HEADERS "${_ZLIB_DIR}/zlib.h" "${_ZLIB_DIR}/zconf.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libz "fbsd_z" "fbsd_zlib_shim.h"
        [=[const char *fbsd_zlib_version(void);]=]
        [=[#include "fbsd_zlib_shim.h"
const char *fbsd_zlib_version(void) { return "1.3.1"; }]=]
    )
endif()

set(_BZ2_DIR "${FREEBSD_SRC_DIR}/contrib/bzip2")
if(EXISTS "${_BZ2_DIR}/bzlib.h")
    set(_BZ2_SRCS
        "${_BZ2_DIR}/blocksort.c" "${_BZ2_DIR}/huffman.c" "${_BZ2_DIR}/crctable.c"
        "${_BZ2_DIR}/randtable.c" "${_BZ2_DIR}/compress.c" "${_BZ2_DIR}/decompress.c"
        "${_BZ2_DIR}/bzlib.c"
    )
    freebsd_add_section3_library(fbsd_libbz2
        OUTPUT_NAME "fbsd_bz2"
        SOURCES ${_BZ2_SRCS}
        INCLUDES "${_BZ2_DIR}"
        PUBLIC_HEADERS "${_BZ2_DIR}/bzlib.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libbz2 "fbsd_bz2" "fbsd_bzlib_shim.h"
        [=[const char *fbsd_BZ2_libversion(void);]=]
        [=[#include "fbsd_bzlib_shim.h"
const char *fbsd_BZ2_libversion(void) { return "1.0.8"; }]=]
    )
endif()

set(_EXPAT_DIR "${FREEBSD_SRC_DIR}/contrib/expat/lib")
if(EXISTS "${_EXPAT_DIR}/expat.h")
    file(WRITE "${_FBSD_S3_GEN_DIR}/include/bsdxml.h" [=[#include <expat.h>
]=])
    file(WRITE "${_FBSD_S3_GEN_DIR}/include/expat_config.h" [=[#ifndef EXPAT_CONFIG_H
#define EXPAT_CONFIG_H 1
#define BYTEORDER 1234
#define HAVE_MEMMOVE 1
#define HAVE_STDINT_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define STDC_HEADERS 1
#define PACKAGE "expat"
#define VERSION "2.6.0"
#define XML_CONTEXT_BYTES 1024
#define XML_DTD 1
#define XML_GE 1
#define XML_NS 1
#define XML_POOR_ENTROPY 1
#endif
]=])
    file(WRITE "${_FBSD_S3_GEN_DIR}/include/winconfig.h" [=[#ifndef EXPAT_WINCONFIG_H
#define EXPAT_WINCONFIG_H 1
#include <string.h>
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#undef WIN32_LEAN_AND_MEAN
#endif
]=])
    set(_EXPAT_ENTROPY_C "${_FBSD_S3_GEN_DIR}/src/expat_entropy.c")
    file(WRITE "${_EXPAT_ENTROPY_C}" [=[#include <stddef.h>
#include <stdlib.h>
#include <time.h>
int writeRandomBytes_arc4random_buf(void *target, size_t count) {
    unsigned char *p = (unsigned char *)target;
    size_t i;
    unsigned int seed = (unsigned int)time(NULL) ^ 0x9E3779B9U;
    for (i = 0; i < count; i++) {
        seed = seed * 1664525U + 1013904223U;
        p[i] = (unsigned char)(seed >> 16);
    }
    return 1;
}
int writeRandomBytes_rand_s(void *target, size_t count) {
    return writeRandomBytes_arc4random_buf(target, count);
}
]=])
    set(_EXPAT_SRCS
        "${_EXPAT_DIR}/xmlparse.c" "${_EXPAT_DIR}/xmlrole.c" "${_EXPAT_DIR}/xmltok.c"
        "${_EXPAT_ENTROPY_C}"
    )
    if(EXISTS "${_EXPAT_DIR}/xcs.c")
        list(APPEND _EXPAT_SRCS "${_EXPAT_DIR}/xcs.c")
    endif()
    freebsd_add_section3_library(fbsd_libbsdxml
        OUTPUT_NAME "fbsd_bsdxml"
        SOURCES ${_EXPAT_SRCS}
        INCLUDES "${_FBSD_S3_GEN_DIR}/include" "${_EXPAT_DIR}"
        DEFINES HAVE_EXPAT_CONFIG_H=1 XML_GE=1 XML_CONTEXT_BYTES=1024 HAVE_MEMMOVE=1 XML_POOR_ENTROPY=1
        PUBLIC_HEADERS "${_EXPAT_DIR}/expat.h" "${_FBSD_S3_GEN_DIR}/include/bsdxml.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libbsdxml "fbsd_bsdxml" "bsdxml.h"
        [=[const char *fbsd_bsdxml_version(void);]=]
        [=[#include "bsdxml.h"
const char *fbsd_bsdxml_version(void) { return "2.6.0"; }]=]
    )
endif()

# =============================================================================
# 2. Digest & Compression Libraries (fbsd_libmd, fbsd_liblzma, fbsd_libzstd)
# =============================================================================
set(_MD_DIR "${FREEBSD_SRC_DIR}/lib/libmd")
if(EXISTS "${_MD_DIR}/md5.h" AND EXISTS "${_FBSD_CODEGEN_DIR}/libmd/md5hl.c")
    file(GLOB _MD_HL_SRCS "${_FBSD_CODEGEN_DIR}/libmd/*hl.c")
    if(EXISTS "${FREEBSD_SRC_DIR}/sys/crypto/md4c.c")
        set(_MD4_C "${FREEBSD_SRC_DIR}/sys/crypto/md4c.c")
        set(_MD5_C "${FREEBSD_SRC_DIR}/sys/crypto/md5c.c")
    else()
        set(_MD4_C "${FREEBSD_SRC_DIR}/sys/kern/md4c.c")
        set(_MD5_C "${FREEBSD_SRC_DIR}/sys/kern/md5c.c")
    endif()
    set(_MD_SRCS
        "${_MD4_C}"
        "${_MD5_C}"
        "${_MD_DIR}/rmd160c.c"
        "${_MD_DIR}/sha0c.c"
        "${_MD_DIR}/sha1c.c"
        "${FREEBSD_SRC_DIR}/sys/crypto/sha2/sha256c.c"
        "${FREEBSD_SRC_DIR}/sys/crypto/sha2/sha512c.c"
        "${FREEBSD_SRC_DIR}/sys/crypto/skein/skein.c"
        "${FREEBSD_SRC_DIR}/sys/crypto/skein/skein_block.c"
        ${_MD_HL_SRCS}
    )
    freebsd_add_section3_library(fbsd_libmd
        OUTPUT_NAME "fbsd_md"
        SOURCES ${_MD_SRCS}
        INCLUDES "${_FBSD_CODEGEN_DIR}/libmd" "${_MD_DIR}"
                 "${FREEBSD_SRC_DIR}/sys/crypto"
                 "${FREEBSD_SRC_DIR}/sys/kern"
                 "${FREEBSD_SRC_DIR}/sys/crypto/sha2"
                 "${FREEBSD_SRC_DIR}/sys/crypto/skein"
        DEFINES SKEIN_LOOP=995
        PUBLIC_HEADERS "${_MD_DIR}/md4.h" "${_MD_DIR}/md5.h" "${_MD_DIR}/ripemd.h"
                       "${_MD_DIR}/sha.h" "${FREEBSD_SRC_DIR}/sys/crypto/sha2/sha256.h"
                       "${FREEBSD_SRC_DIR}/sys/crypto/sha2/sha512.h"
                       "${FREEBSD_SRC_DIR}/sys/crypto/skein/skein.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libmd "fbsd_md" "fbsd_md_s3.h"
        [=[const char *fbsd_libmd_abi_version(void);]=]
        [=[#include "fbsd_md_s3.h"
const char *fbsd_libmd_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_XZ_DIR "${FREEBSD_SRC_DIR}/contrib/xz/src")
if(EXISTS "${_XZ_DIR}/liblzma/api/lzma.h" AND EXISTS "${_FBSD_CODEGEN_DIR}/liblzma/config.h")
    file(GLOB _LZMA_COMMON "${_XZ_DIR}/liblzma/common/*.c")
    file(GLOB _LZMA_LZ "${_XZ_DIR}/liblzma/lz/*.c")
    file(GLOB _LZMA_LZMA "${_XZ_DIR}/liblzma/lzma/*.c")
    file(GLOB _LZMA_RC "${_XZ_DIR}/liblzma/rangecoder/*.c")
    list(FILTER _LZMA_LZMA EXCLUDE REGEX [=[_tablegen\.c$]=])
    list(FILTER _LZMA_RC EXCLUDE REGEX [=[_tablegen\.c$]=])
    file(GLOB _LZMA_DELTA "${_XZ_DIR}/liblzma/delta/*.c")
    file(GLOB _LZMA_SIMPLE "${_XZ_DIR}/liblzma/simple/*.c")
    if(FREEBSD_TARGET_DOS)
        list(FILTER _LZMA_COMMON EXCLUDE REGEX [=[_mt\.c$]=])
        list(FILTER _LZMA_COMMON EXCLUDE REGEX [=[outqueue\.c$]=])
    endif()
    set(_LZMA_SRCS
        "${_XZ_DIR}/common/tuklib_physmem.c"
        "${_XZ_DIR}/common/tuklib_cpucores.c"
        ${_LZMA_COMMON}
        "${_XZ_DIR}/liblzma/check/check.c"
        "${_XZ_DIR}/liblzma/check/crc32_fast.c"
        "${_XZ_DIR}/liblzma/check/crc64_fast.c"
        ${_LZMA_LZ} ${_LZMA_LZMA} ${_LZMA_RC} ${_LZMA_DELTA} ${_LZMA_SIMPLE}
    )
    if(EXISTS "${_XZ_DIR}/liblzma/check/sha256.c")
        list(APPEND _LZMA_SRCS "${_XZ_DIR}/liblzma/check/sha256.c")
    endif()
    freebsd_add_section3_library(fbsd_liblzma
        OUTPUT_NAME "fbsd_lzma"
        SOURCES ${_LZMA_SRCS}
        INCLUDES "${_XZ_DIR}/liblzma/api" "${_FBSD_CODEGEN_DIR}/liblzma"
                 "${FREEBSD_SRC_DIR}/sys/crypto/sha2"
                 "${_XZ_DIR}/liblzma/common" "${_XZ_DIR}/liblzma/check"
                 "${_XZ_DIR}/liblzma/lz" "${_XZ_DIR}/liblzma/rangecoder"
                 "${_XZ_DIR}/liblzma/lzma" "${_XZ_DIR}/liblzma/delta"
                 "${_XZ_DIR}/liblzma/simple" "${_XZ_DIR}/common"
        DEFINES HAVE_CONFIG_H=1 TUKLIB_SYMBOL_PREFIX=lzma_ LZMA_API_STATIC=1
        LIBS fbsd_libmd
        PUBLIC_HEADERS "${_XZ_DIR}/liblzma/api/lzma.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_liblzma "fbsd_lzma" "fbsd_lzma_s3.h"
        [=[const char *fbsd_liblzma_abi_version(void);]=]
        [=[#include "fbsd_lzma_s3.h"
const char *fbsd_liblzma_abi_version(void) { return "5.6.0"; }]=]
    )
endif()

set(_ZSTD_DIR "${FREEBSD_SRC_DIR}/sys/contrib/zstd/lib")
if(EXISTS "${_ZSTD_DIR}/zstd.h")
    file(GLOB _ZSTD_SRCS
        "${_ZSTD_DIR}/common/*.c"
        "${_ZSTD_DIR}/compress/*.c"
        "${_ZSTD_DIR}/decompress/*.c"
        "${_ZSTD_DIR}/dictBuilder/*.c"
        "${_ZSTD_DIR}/deprecated/*.c"
    )
    freebsd_add_section3_library(fbsd_libzstd
        NO_GNU_SOURCE
        OUTPUT_NAME "fbsd_zstd"
        SOURCES ${_ZSTD_SRCS}
        INCLUDES "${_ZSTD_DIR}" "${_ZSTD_DIR}/common" "${_ZSTD_DIR}/dictBuilder"
        DEFINES ZSTD_DISABLE_ASM=1
                $<$<NOT:$<BOOL:${FREEBSD_TARGET_DOS}>>:ZSTD_MULTITHREAD=1>
        PUBLIC_HEADERS "${_ZSTD_DIR}/zstd.h" "${_ZSTD_DIR}/zdict.h" "${_ZSTD_DIR}/zstd_errors.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libzstd "fbsd_zstd" "fbsd_zstd_s3.h"
        [=[const char *fbsd_libzstd_abi_version(void);]=]
        [=[#include "fbsd_zstd_s3.h"
const char *fbsd_libzstd_abi_version(void) { return "1.5.6"; }]=]
    )
endif()

# =============================================================================
# 3. Core BSD Userland Libraries (libsbuf, libutil, libxo, libopenbsd, libnetbsd,
#    libregex, libdiff, libcalendar, libmp, libtelnet, libpkgconf)
# =============================================================================
_fbsd_define_portable_s3_unit(fbsd_libsbuf "fbsd_sbuf" "sys/sbuf.h"
[=[#ifndef FBSD_SYS_SBUF_H_
#define FBSD_SYS_SBUF_H_
#include <stdarg.h>
#include <stddef.h>
#include <sys/types.h>
#define SBUF_FIXEDLEN   0x00000000
#define SBUF_AUTOEXTEND 0x00000001
struct sbuf;
typedef int (sbuf_drain_func)(void *, const char *, int);
struct sbuf *sbuf_new(struct sbuf *s, char *buf, int length, int flags);
struct sbuf *sbuf_new_auto(void);
void sbuf_clear(struct sbuf *s);
int sbuf_setpos(struct sbuf *s, ssize_t pos);
int sbuf_bcat(struct sbuf *s, const void *ptr, size_t len);
int sbuf_bcpy(struct sbuf *s, const void *ptr, size_t len);
int sbuf_cat(struct sbuf *s, const char *str);
int sbuf_cpy(struct sbuf *s, const char *str);
int sbuf_printf(struct sbuf *s, const char *fmt, ...);
int sbuf_vprintf(struct sbuf *s, const char *fmt, va_list ap);
int sbuf_putc(struct sbuf *s, int c);
void sbuf_set_drain(struct sbuf *s, sbuf_drain_func *func, void *arg);
int sbuf_trim(struct sbuf *s);
int sbuf_error(const struct sbuf *s);
int sbuf_finish(struct sbuf *s);
char *sbuf_data(struct sbuf *s);
ssize_t sbuf_len(struct sbuf *s);
int sbuf_done(const struct sbuf *s);
void sbuf_delete(struct sbuf *s);
#endif]=]
[=[#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sys/sbuf.h"
struct sbuf {
    char *buf;
    size_t len;
    size_t cap;
    int dyn_struct;
    int dyn_buf;
    int finished;
    int err;
    sbuf_drain_func *drain_fn;
    void *drain_arg;
};
static int sbuf_reserve(struct sbuf *s, size_t extra) {
    if (s->len + extra + 1 > s->cap) {
        size_t ncap;
        char *nb;
        if (s->drain_fn != NULL && s->len > 0) {
            int d = s->drain_fn(s->drain_arg, s->buf, (int)s->len);
            if (d > 0) { s->len = 0; s->buf[0] = '\0'; }
        }
        if (s->len + extra + 1 <= s->cap) return 0;
        if (!s->dyn_buf) { s->err = -1; return -1; }
        ncap = (s->cap == 0) ? 128 : s->cap * 2;
        while (ncap < s->len + extra + 1) ncap *= 2;
        nb = (char *)realloc(s->buf, ncap);
        if (nb == NULL) { s->err = -1; return -1; }
        s->buf = nb; s->cap = ncap;
    }
    return 0;
}
struct sbuf *sbuf_new(struct sbuf *s, char *buf, int length, int flags) {
    int dyn_s = 0;
    if (s == NULL) {
        s = (struct sbuf *)calloc(1, sizeof(*s));
        if (s == NULL) return NULL;
        dyn_s = 1;
    } else {
        memset(s, 0, sizeof(*s));
    }
    s->dyn_struct = dyn_s;
    if (buf != NULL && length > 0 && !(flags & SBUF_AUTOEXTEND)) {
        s->buf = buf; s->cap = (size_t)length; s->dyn_buf = 0;
    } else {
        s->dyn_buf = 1;
        if (sbuf_reserve(s, length > 0 ? (size_t)length : 64) != 0) {
            if (dyn_s) free(s);
            return NULL;
        }
    }
    s->buf[0] = '\0';
    return s;
}
struct sbuf *sbuf_new_auto(void) { return sbuf_new(NULL, NULL, 0, SBUF_AUTOEXTEND); }
void sbuf_clear(struct sbuf *s) { if (s) { s->len = 0; s->finished = 0; s->err = 0; if (s->buf) s->buf[0] = '\0'; } }
int sbuf_setpos(struct sbuf *s, ssize_t pos) {
    if (!s || pos < 0 || (size_t)pos > s->len) return -1;
    s->len = (size_t)pos; s->buf[s->len] = '\0'; return 0;
}
int sbuf_bcat(struct sbuf *s, const void *ptr, size_t len) {
    if (!s || sbuf_reserve(s, len) != 0) return -1;
    if (len > 0 && ptr != NULL) memcpy(s->buf + s->len, ptr, len);
    s->len += len; s->buf[s->len] = '\0'; return 0;
}
int sbuf_bcpy(struct sbuf *s, const void *ptr, size_t len) { sbuf_clear(s); return sbuf_bcat(s, ptr, len); }
int sbuf_cat(struct sbuf *s, const char *str) { return sbuf_bcat(s, str, str ? strlen(str) : 0); }
int sbuf_cpy(struct sbuf *s, const char *str) { sbuf_clear(s); return sbuf_cat(s, str); }
int sbuf_vprintf(struct sbuf *s, const char *fmt, va_list ap) {
    char tmp[2048];
    if (!s || !fmt) return -1;
    vsnprintf(tmp, sizeof(tmp), fmt, ap);
    return sbuf_cat(s, tmp);
}
int sbuf_printf(struct sbuf *s, const char *fmt, ...) {
    int r; va_list ap; va_start(ap, fmt); r = sbuf_vprintf(s, fmt, ap); va_end(ap); return r;
}
int sbuf_putc(struct sbuf *s, int c) { char ch = (char)c; return sbuf_bcat(s, &ch, 1); }
void sbuf_set_drain(struct sbuf *s, sbuf_drain_func *func, void *arg) { if (s) { s->drain_fn = func; s->drain_arg = arg; } }
int sbuf_trim(struct sbuf *s) {
    if (!s) return -1;
    while (s->len > 0 && isspace((unsigned char)s->buf[s->len - 1])) s->len--;
    s->buf[s->len] = '\0'; return 0;
}
int sbuf_error(const struct sbuf *s) { return s ? s->err : -1; }
int sbuf_finish(struct sbuf *s) {
    if (!s) return -1;
    if (s->drain_fn != NULL && s->len > 0) {
        int d = s->drain_fn(s->drain_arg, s->buf, (int)s->len);
        if (d > 0) { s->len = 0; s->buf[0] = '\0'; }
    }
    s->finished = 1; return s->err;
}
char *sbuf_data(struct sbuf *s) { return s ? s->buf : NULL; }
ssize_t sbuf_len(struct sbuf *s) { return s ? (ssize_t)s->len : -1; }
int sbuf_done(const struct sbuf *s) { return s ? s->finished : 0; }
void sbuf_delete(struct sbuf *s) {
    if (!s) return;
    if (s->dyn_buf) free(s->buf);
    if (s->dyn_struct) free(s);
}
]=]
)

_fbsd_define_portable_s3_unit(fbsd_libutil "fbsd_util" "fbsd_libutil_s3.h"
[=[#ifndef FBSD_LIBUTIL_S3_H_
#define FBSD_LIBUTIL_S3_H_
#include <stdint.h>
#include <stddef.h>
int fbsd_expand_number(const char *buf, uint64_t *num);
int fbsd_humanize_number(char *buf, size_t len, int64_t bytes, const char *suffix, int scale, int flags);
#endif]=]
[=[#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fbsd_libutil_s3.h"
int fbsd_expand_number(const char *buf, uint64_t *num) {
    char *endp = NULL;
    unsigned long long val;
    unsigned int shift = 0;
    if (buf == NULL || num == NULL) { errno = EINVAL; return -1; }
    val = strtoull(buf, &endp, 0);
    if (endp == buf) { errno = EINVAL; return -1; }
    if (endp != NULL && *endp != '\0') {
        switch (tolower((unsigned char)*endp)) {
            case 'b': shift = 0; break;
            case 'k': shift = 10; break;
            case 'm': shift = 20; break;
            case 'g': shift = 30; break;
            case 't': shift = 40; break;
            case 'p': shift = 50; break;
            case 'e': shift = 60; break;
            default: errno = EINVAL; return -1;
        }
    }
    *num = ((uint64_t)val) << shift;
    return 0;
}
int fbsd_humanize_number(char *buf, size_t len, int64_t bytes, const char *suffix, int scale, int flags) {
    (void)scale; (void)flags;
    if (buf == NULL || len == 0) return -1;
    return snprintf(buf, len, "%lld%s", (long long)bytes, suffix ? suffix : "");
}
]=]
)

set(_XO_DIR "${FREEBSD_SRC_DIR}/contrib/libxo/libxo")
if(EXISTS "${_XO_DIR}/libxo.c" AND EXISTS "${FREEBSD_SRC_DIR}/lib/libxo/libxo/xo_config.h")
    _fbsd_resolve_staged_or_upstream(_XO_SYSLOG_C "contrib/libxo/libxo/xo_syslog.c")
    freebsd_add_section3_library(fbsd_libxo
        OUTPUT_NAME "fbsd_xo"
        SOURCES "${_XO_DIR}/libxo.c" "${_XO_DIR}/xo_encoder.c" "${_XO_SYSLOG_C}"
        INCLUDES "${_FBSD_GEN_BASE}/include/libxo" "${_XO_DIR}" "${FREEBSD_SRC_DIR}/lib/libxo" "${FREEBSD_SRC_DIR}/lib/libxo/libxo"
        DEFINES "dlfunc=dlsym" "__isthreaded=0"
        DATA_EXPORTS xo_version xo_version_extra
        PUBLIC_HEADERS "${_FBSD_GEN_BASE}/include/libxo/xo.h" "${_FBSD_GEN_BASE}/include/libxo/xo_encoder.h"
    )
    if(TARGET fbsd_libxo AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libxo PUBLIC FBSD_XO_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libxo "fbsd_xo" "fbsd_xo_s3.h"
        [=[int fbsd_xo_parse_args(int argc, char **argv);]=]
        [=[#include "fbsd_xo_s3.h"
int fbsd_xo_parse_args(int argc, char **argv) { (void)argv; return argc; }]=]
    )
endif()

set(_OBSD_DIR "${FREEBSD_SRC_DIR}/lib/libopenbsd")
if(EXISTS "${_OBSD_DIR}/ohash.c")
    set(_OBSD_SHIM_C "${_FBSD_S3_GEN_DIR}/src/fbsd_openbsd_shim.c")
    file(WRITE "${_OBSD_SHIM_C}" [=[#if !defined(__FreeBSD__) && !defined(__OpenBSD__)
int getdtablecount(void) { return 3; }
#else
typedef int fbsd_openbsd_shim_unused_t;
#endif
]=])
    set(_OBSD_SRCS "${_OBSD_DIR}/ohash.c" "${_OBSD_SHIM_C}")
    if(NOT WIN32 AND NOT FREEBSD_TARGET_DOS)
        list(APPEND _OBSD_SRCS "${_OBSD_DIR}/imsg-buffer.c" "${_OBSD_DIR}/imsg.c")
    endif()
    set(_OBSD_INC_DIRS "${_OBSD_DIR}")
    if(IS_DIRECTORY "${_FBSD_CODEGEN_DIR}/libopenbsd")
        set(_OBSD_INC_DIRS "${_FBSD_CODEGEN_DIR}/libopenbsd")
    endif()
    freebsd_add_section3_library(fbsd_libopenbsd
        OUTPUT_NAME "fbsd_openbsd"
        SOURCES ${_OBSD_SRCS}
        INCLUDES ${_OBSD_INC_DIRS}
        PUBLIC_HEADERS "${_OBSD_DIR}/imsg.h" "${_OBSD_DIR}/ohash.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libopenbsd "fbsd_openbsd" "fbsd_openbsd_s3.h"
        [=[const char *fbsd_libopenbsd_abi_version(void);]=]
        [=[#include "fbsd_openbsd_s3.h"
const char *fbsd_libopenbsd_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_NBSD_DIR "${FREEBSD_SRC_DIR}/lib/libnetbsd")
if(EXISTS "${_NBSD_DIR}/efun.c")
    set(_NBSD_SRCS "${_NBSD_DIR}/efun.c" "${_NBSD_DIR}/strsuftoll.c" "${_NBSD_DIR}/util.c")
    if(CMAKE_SYSTEM_NAME STREQUAL "FreeBSD" OR APPLE)
        list(APPEND _NBSD_SRCS "${_NBSD_DIR}/sockaddr_snprintf.c")
    endif()
    set(_NBSD_INC_DIRS "${_NBSD_DIR}")
    if(IS_DIRECTORY "${_FBSD_CODEGEN_DIR}/libnetbsd")
        set(_NBSD_INC_DIRS "${_FBSD_CODEGEN_DIR}/libnetbsd")
    endif()
    freebsd_add_section3_library(fbsd_libnetbsd
        OUTPUT_NAME "fbsd_netbsd"
        SOURCES ${_NBSD_SRCS}
        INCLUDES ${_NBSD_INC_DIRS}
        DEFINES "__va_list=va_list"
        PUBLIC_HEADERS "${_NBSD_DIR}/efun.h" "${_NBSD_DIR}/util.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libnetbsd "fbsd_netbsd" "fbsd_netbsd_s3.h"
        [=[const char *fbsd_libnetbsd_abi_version(void);]=]
        [=[#include "fbsd_netbsd_s3.h"
const char *fbsd_libnetbsd_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_RX_DIR "${FREEBSD_SRC_DIR}/lib/libc/regex")
if(EXISTS "${_RX_DIR}/regcomp.c" AND EXISTS "${_FBSD_CODEGEN_DIR}/libregex/regex.h")
    freebsd_add_section3_library(fbsd_libregex
        OUTPUT_NAME "fbsd_regex"
        SOURCES "${_RX_DIR}/regcomp.c" "${_RX_DIR}/regerror.c"
                "${_RX_DIR}/regexec.c" "${_RX_DIR}/regfree.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/libregex" "${_RX_DIR}"
                 "${FREEBSD_SRC_DIR}/lib/libc/include"
        DEFINES LIBREGEX=1 POSIX_MISTAKE=1 POSIX_REGEX_H=1
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/libregex/regex.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libregex "fbsd_regex" "fbsd_regex_s3.h"
        [=[const char *fbsd_libregex_abi_version(void);]=]
        [=[#include "fbsd_regex_s3.h"
const char *fbsd_libregex_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_LDIFF_DIR "${FREEBSD_SRC_DIR}/contrib/libdiff")
if(EXISTS "${_LDIFF_DIR}/lib/diff_main.c")
    file(GLOB _LDIFF_SRCS "${_LDIFF_DIR}/lib/*.c")
    freebsd_add_section3_library(fbsd_libdiff
        OUTPUT_NAME "fbsd_diff"
        SOURCES ${_LDIFF_SRCS}
        INCLUDES "${_LDIFF_DIR}/include"
        PUBLIC_HEADERS "${_LDIFF_DIR}/include/diff_main.h" "${_LDIFF_DIR}/include/diff_output.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libdiff "fbsd_diff" "fbsd_diff_s3.h"
        [=[const char *fbsd_libdiff_abi_version(void);]=]
        [=[#include "fbsd_diff_s3.h"
const char *fbsd_libdiff_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_CAL_DIR "${FREEBSD_SRC_DIR}/lib/libcalendar")
if(EXISTS "${_CAL_DIR}/calendar.c")
    freebsd_add_section3_library(fbsd_libcalendar
        OUTPUT_NAME "fbsd_calendar"
        SOURCES "${_CAL_DIR}/calendar.c" "${_CAL_DIR}/easter.c"
        INCLUDES "${_CAL_DIR}"
        PUBLIC_HEADERS "${_CAL_DIR}/calendar.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libcalendar "fbsd_calendar" "fbsd_calendar_s3.h"
        [=[const char *fbsd_libcalendar_abi_version(void);]=]
        [=[#include "fbsd_calendar_s3.h"
const char *fbsd_libcalendar_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

if(EXISTS "${_FBSD_CODEGEN_DIR}/libmp/fbsd_mp.c")
    freebsd_add_section3_library(fbsd_libmp
        OUTPUT_NAME "fbsd_mp"
        SOURCES "${_FBSD_CODEGEN_DIR}/libmp/fbsd_mp.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/libmp"
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/libmp/mp.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libmp "fbsd_mp" "fbsd_mp_s3.h"
        [=[const char *fbsd_libmp_abi_version(void);]=]
        [=[#include "fbsd_mp_s3.h"
const char *fbsd_libmp_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_TELNET_DIR "${FREEBSD_SRC_DIR}/contrib/telnet")
if(EXISTS "${_TELNET_DIR}/libtelnet/genget.c")
    freebsd_add_section3_library(fbsd_libtelnet
        OUTPUT_NAME "fbsd_telnet"
        SOURCES "${_TELNET_DIR}/libtelnet/genget.c"
                "${_TELNET_DIR}/libtelnet/getent.c"
                "${_TELNET_DIR}/libtelnet/misc.c"
        INCLUDES "${_TELNET_DIR}"
        PUBLIC_HEADERS "${_TELNET_DIR}/libtelnet/misc.h" "${_TELNET_DIR}/libtelnet/misc-proto.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libtelnet "fbsd_telnet" "fbsd_telnet_s3.h"
        [=[const char *fbsd_libtelnet_abi_version(void);]=]
        [=[#include "fbsd_telnet_s3.h"
const char *fbsd_libtelnet_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_PKGCONF_DIR "${FREEBSD_SRC_DIR}/contrib/pkgconf")
if(EXISTS "${_PKGCONF_DIR}/libpkgconf/libpkgconf.h" AND EXISTS "${_FBSD_CODEGEN_DIR}/pkgconf/libpkgconf/config.h")
    file(GLOB _PKGCONF_RAW_SRCS "${_PKGCONF_DIR}/libpkgconf/*.c")
    set(_PKGCONF_SRCS "")
    foreach(_pc_raw ${_PKGCONF_RAW_SRCS})
        get_filename_component(_pc_name "${_pc_raw}" NAME)
        _fbsd_resolve_staged_or_upstream(_pc_src "contrib/pkgconf/libpkgconf/${_pc_name}")
        list(APPEND _PKGCONF_SRCS "${_pc_src}")
    endforeach()
    set(_PKGCONF_INCS "${_FBSD_CODEGEN_DIR}/pkgconf")
    if(EXISTS "${_FBSD_GEN_BASE}/staged_src/contrib/pkgconf/libpkgconf/libpkgconf.h")
        list(APPEND _PKGCONF_INCS
            "${_FBSD_GEN_BASE}/staged_src/contrib/pkgconf"
            "${_FBSD_GEN_BASE}/staged_src/contrib/pkgconf/libpkgconf"
        )
    endif()
    list(APPEND _PKGCONF_INCS "${_PKGCONF_DIR}" "${_PKGCONF_DIR}/libpkgconf")
    _fbsd_resolve_staged_or_upstream(_PKGCONF_PUB_HDR "contrib/pkgconf/libpkgconf/libpkgconf.h")
    freebsd_add_section3_library(fbsd_libpkgconf
        OUTPUT_NAME "fbsd_pkgconf"
        SOURCES ${_PKGCONF_SRCS}
        INCLUDES ${_PKGCONF_INCS}
        DEFINES PKGCONFIG_IS_STATIC=1
        PUBLIC_HEADERS "${_PKGCONF_PUB_HDR}"
    )
    if(TARGET fbsd_libpkgconf)
        target_compile_definitions(fbsd_libpkgconf PUBLIC PKGCONFIG_IS_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libpkgconf "fbsd_pkgconf" "fbsd_pkgconf_s3.h"
        [=[const char *fbsd_libpkgconf_abi_version(void);]=]
        [=[#include "fbsd_pkgconf_s3.h"
const char *fbsd_libpkgconf_abi_version(void) { return "2.3.0"; }]=]
    )
endif()

# =============================================================================
# 4. Archive, Magic, ELF Toolchain, Network & TUI Section 3 Libraries
# =============================================================================
set(_LA_DIR "${FREEBSD_SRC_DIR}/contrib/libarchive/libarchive")
if(EXISTS "${_LA_DIR}/archive.h" AND EXISTS "${_FBSD_CODEGEN_DIR}/libarchive/config.h")
    file(GLOB _LA_ALL_C "${_LA_DIR}/archive_*.c")
    list(FILTER _LA_ALL_C EXCLUDE REGEX [=[archive_disk_acl_(freebsd|linux|darwin|sunos)\.c$]=])
    if(WIN32)
        list(FILTER _LA_ALL_C EXCLUDE REGEX [=[_posix\.c$]=])
        list(FILTER _LA_ALL_C EXCLUDE REGEX [=[archive_read_disk_set_standard_lookup\.c$]=])
        list(FILTER _LA_ALL_C EXCLUDE REGEX [=[archive_write_disk_set_standard_lookup\.c$]=])
        set(_LA_SRCS ${_LA_ALL_C} "${_FBSD_CODEGEN_DIR}/libarchive/fbsd_libarchive_win32.c")
    else()
        list(FILTER _LA_ALL_C EXCLUDE REGEX [=[_windows\.c$]=])
        list(FILTER _LA_ALL_C EXCLUDE REGEX [=[archive_entry_copy_bhfi\.c$]=])
        set(_LA_SRCS ${_LA_ALL_C} "${_LA_DIR}/filter_fork_posix.c")
    endif()
    if(EXISTS "${_LA_DIR}/xxhash.c")
        list(APPEND _LA_SRCS "${_LA_DIR}/xxhash.c")
    endif()
    freebsd_add_section3_library(fbsd_libarchive
        OUTPUT_NAME "fbsd_archive"
        SOURCES ${_LA_SRCS}
        INCLUDES "${_LA_DIR}" "${_FBSD_CODEGEN_DIR}/libarchive"
        DEFINES HAVE_CONFIG_H=1 LIBARCHIVE_STATIC=1 FBSD_SKIP_PREINCLUDE_ENDIAN=1
        LIBS fbsd_libz fbsd_libbz2 fbsd_liblzma fbsd_libzstd fbsd_libbsdxml fbsd_libmd $<$<BOOL:${WIN32}>:bcrypt>
        PUBLIC_HEADERS "${_LA_DIR}/archive.h" "${_LA_DIR}/archive_entry.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libarchive "fbsd_archive" "fbsd_archive_s3.h"
        [=[const char *fbsd_libarchive_abi_version(void);]=]
        [=[#include "fbsd_archive_s3.h"
const char *fbsd_libarchive_abi_version(void) { return "3.7.7"; }]=]
        LIBS fbsd_libz fbsd_libbz2 fbsd_liblzma fbsd_libzstd fbsd_libbsdxml fbsd_libmd
    )
endif()

set(_FILE_DIR "${FREEBSD_SRC_DIR}/contrib/file/src")
if(EXISTS "${_FILE_DIR}/magic.c" AND EXISTS "${_FBSD_CODEGEN_DIR}/libmagic/magic.h")
    set(_MAGIC_SRCS
        "${_FILE_DIR}/apprentice.c" "${_FILE_DIR}/apptype.c" "${_FILE_DIR}/ascmagic.c"
        "${_FILE_DIR}/buffer.c" "${_FILE_DIR}/cdf.c" "${_FILE_DIR}/cdf_time.c"
        "${_FILE_DIR}/compress.c" "${_FILE_DIR}/der.c" "${_FILE_DIR}/encoding.c"
        "${_FILE_DIR}/fmtcheck.c"
        "${_FILE_DIR}/fsmagic.c" "${_FILE_DIR}/funcs.c" "${_FILE_DIR}/is_json.c"
        "${_FILE_DIR}/is_csv.c" "${_FILE_DIR}/is_simh.c" "${_FILE_DIR}/is_tar.c"
        "${_FILE_DIR}/magic.c" "${_FILE_DIR}/print.c"
        "${_FILE_DIR}/readelf.c" "${_FILE_DIR}/seccomp.c" "${_FILE_DIR}/softmagic.c"
    )
    if(EXISTS "${_FILE_DIR}/swap.c")
        list(APPEND _MAGIC_SRCS "${_FILE_DIR}/swap.c")
    endif()
    _fbsd_resolve_staged_or_upstream(_MAGIC_READCDF_C "contrib/file/src/readcdf.c")
    list(APPEND _MAGIC_SRCS "${_MAGIC_READCDF_C}")
    freebsd_add_section3_library(fbsd_libmagic
        OUTPUT_NAME "fbsd_magic"
        SOURCES ${_MAGIC_SRCS}
        INCLUDES "${_FBSD_CODEGEN_DIR}/libmagic" "${_FILE_DIR}"
        DEFINES HAVE_CONFIG_H=1
        LIBS fbsd_libz fbsd_libbz2 fbsd_liblzma fbsd_libzstd $<$<BOOL:${WIN32}>:shlwapi>
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/libmagic/magic.h"
    )
    if(TARGET fbsd_libmagic AND WIN32 AND NOT MSVC)
        target_compile_options(fbsd_libmagic PRIVATE "-UWIN32")
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libmagic "fbsd_magic" "fbsd_magic_s3.h"
        [=[const char *fbsd_libmagic_abi_version(void);]=]
        [=[#include "fbsd_magic_s3.h"
const char *fbsd_libmagic_abi_version(void) { return "5.45"; }]=]
        LIBS fbsd_libz fbsd_libbz2 fbsd_liblzma fbsd_libzstd
    )
endif()

set(_ELFTC_DIR "${FREEBSD_SRC_DIR}/contrib/elftoolchain")
if(EXISTS "${_ELFTC_DIR}/libelf/libelf.h" AND EXISTS "${_FBSD_CODEGEN_DIR}/elftoolchain/gensrcs/libelf_fsize.c")
    file(GLOB _ELFTC_ELF_C "${_ELFTC_DIR}/libelf/*.c")
    list(FILTER _ELFTC_ELF_C EXCLUDE REGEX [=[libelf_align\.c$]=])
    _fbsd_resolve_staged_or_upstream(_ELFTC_ALIGN_C "contrib/elftoolchain/libelf/libelf_align.c")
    list(APPEND _ELFTC_ELF_C "${_ELFTC_ALIGN_C}")
    file(GLOB _ELFTC_TC_C "${_ELFTC_DIR}/libelftc/*.c")
    list(FILTER _ELFTC_TC_C EXCLUDE REGEX [=[elftc_version\.c$]=])
    file(GLOB _ELFTC_DW_C "${_ELFTC_DIR}/libdwarf/*.c")
    list(FILTER _ELFTC_DW_C EXCLUDE REGEX [=[zlib_stub\.c$]=])
    list(FILTER _ELFTC_DW_C EXCLUDE REGEX [=[libdwarf_lineno\.c$]=])
    _fbsd_resolve_staged_or_upstream(_ELFTC_DW_LINENO_C "contrib/elftoolchain/libdwarf/libdwarf_lineno.c")
    list(APPEND _ELFTC_DW_C "${_ELFTC_DW_LINENO_C}")
    file(GLOB _ELFTC_PE_C "${_ELFTC_DIR}/libpe/*.c")
    file(GLOB _ELFTC_M4_C "${_FBSD_CODEGEN_DIR}/elftoolchain/gensrcs/*.c")
    freebsd_add_section3_library(fbsd_libelftc
        OUTPUT_NAME "fbsd_elftc"
        SOURCES ${_ELFTC_ELF_C} ${_ELFTC_TC_C} ${_ELFTC_DW_C} ${_ELFTC_PE_C}
                ${_ELFTC_M4_C} "${_FBSD_CODEGEN_DIR}/elftoolchain/libelftc_version.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/elftoolchain"
                 "${_ELFTC_DIR}/common" "${_ELFTC_DIR}/libelf"
                 "${_ELFTC_DIR}/libelftc" "${_ELFTC_DIR}/libdwarf" "${_ELFTC_DIR}/libpe"
        DEFINES ELFTC_HAVE_UTIMES=1
                LIBELF_ARCH=EM_X86_64 LIBELF_BYTEORDER=ELFDATA2LSB LIBELF_CLASS=ELFCLASS64
        LIBS fbsd_libz
        PUBLIC_HEADERS "${_ELFTC_DIR}/libelf/libelf.h" "${_ELFTC_DIR}/libelf/gelf.h"
                       "${_ELFTC_DIR}/libelftc/libelftc.h" "${_ELFTC_DIR}/libdwarf/libdwarf.h"
                       "${_ELFTC_DIR}/libdwarf/dwarf.h" "${_ELFTC_DIR}/libpe/libpe.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libelftc "fbsd_elftc" "fbsd_elftc_s3.h"
        [=[const char *fbsd_libelftc_abi_version(void);]=]
        [=[#include "fbsd_elftc_s3.h"
const char *fbsd_libelftc_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_FETCH_DIR "${FREEBSD_SRC_DIR}/lib/libfetch")
if(EXISTS "${_FETCH_DIR}/fetch.c" AND EXISTS "${_FBSD_CODEGEN_DIR}/libfetch/ftperr.h")
    _fbsd_resolve_staged_or_upstream(_FETCH_FTP_C "lib/libfetch/ftp.c")
    set(_FETCH_PUB_HDR "${_FETCH_DIR}/fetch.h")
    if(EXISTS "${_FBSD_CODEGEN_DIR}/libfetch/fetch.h")
        set(_FETCH_PUB_HDR "${_FBSD_CODEGEN_DIR}/libfetch/fetch.h")
    endif()
    freebsd_add_section3_library(fbsd_libfetch
        OUTPUT_NAME "fbsd_fetch"
        SOURCES "${_FETCH_DIR}/fetch.c" "${_FETCH_DIR}/common.c"
                "${_FETCH_FTP_C}" "${_FETCH_DIR}/http.c" "${_FETCH_DIR}/file.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/libfetch" "${_FETCH_DIR}"
        DEFINES FTP_COMBINE_CWDS=1
        LIBS fbsd_libmd
        DATA_EXPORTS fetchAuthMethod fetchLastErrCode fetchLastErrString fetchTimeout fetchRestartCalls fetchDebug
        PUBLIC_HEADERS "${_FETCH_PUB_HDR}"
    )
    if(TARGET fbsd_libfetch AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libfetch PUBLIC FBSD_FETCH_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libfetch "fbsd_fetch" "fbsd_fetch_s3.h"
        [=[const char *fbsd_libfetch_abi_version(void);]=]
        [=[#include "fbsd_fetch_s3.h"
const char *fbsd_libfetch_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()

set(_LDNS_DIR "${FREEBSD_SRC_DIR}/contrib/ldns")
if(EXISTS "${_LDNS_DIR}/buffer.c" AND EXISTS "${_FBSD_CODEGEN_DIR}/ldns/ldns/config.h")
    set(_LDNS_SRCS
        "${_LDNS_DIR}/buffer.c" "${_LDNS_DIR}/dane.c" "${_LDNS_DIR}/dname.c"
        "${_LDNS_DIR}/dnssec.c" "${_LDNS_DIR}/dnssec_sign.c" "${_LDNS_DIR}/dnssec_verify.c"
        "${_LDNS_DIR}/dnssec_zone.c" "${_LDNS_DIR}/duration.c" "${_LDNS_DIR}/edns.c"
        "${_LDNS_DIR}/error.c" "${_LDNS_DIR}/higher.c" "${_LDNS_DIR}/host2str.c"
        "${_LDNS_DIR}/host2wire.c" "${_LDNS_DIR}/keys.c" "${_LDNS_DIR}/net.c"
        "${_LDNS_DIR}/packet.c" "${_LDNS_DIR}/parse.c" "${_LDNS_DIR}/radix.c"
        "${_LDNS_DIR}/rbtree.c" "${_LDNS_DIR}/rdata.c" "${_LDNS_DIR}/resolver.c"
        "${_LDNS_DIR}/rr.c" "${_LDNS_DIR}/rr_functions.c" "${_LDNS_DIR}/sha1.c"
        "${_LDNS_DIR}/sha2.c" "${_LDNS_DIR}/str2host.c" "${_LDNS_DIR}/tsig.c"
        "${_LDNS_DIR}/update.c" "${_LDNS_DIR}/util.c" "${_LDNS_DIR}/wire2host.c"
        "${_LDNS_DIR}/zone.c" "${_LDNS_DIR}/compat/b64_ntop.c" "${_LDNS_DIR}/compat/b64_pton.c"
    )
    freebsd_add_section3_library(fbsd_libldns
        OUTPUT_NAME "fbsd_ldns"
        SOURCES ${_LDNS_SRCS}
        INCLUDES "${_FBSD_CODEGEN_DIR}/ldns" "${_FBSD_CODEGEN_DIR}/ldns/ldns" "${_LDNS_DIR}"
        DEFINES HAVE_CONFIG_H=1
        DATA_EXPORTS ldns_signing_algorithms ldns_error_str
                     ldns_algorithms ldns_cert_algorithms ldns_rr_classes ldns_rcodes
                     ldns_opcodes ldns_edns_flags ldns_output_format_nocomments
                     ldns_output_format_onlykeyids ldns_output_format_default
                     ldns_output_format_bubblebabble ldns_rbtree_null_node
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/ldns/ldns/ldns.h"
    )
    if(TARGET fbsd_libldns AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libldns PUBLIC FBSD_LDNS_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libldns "fbsd_ldns" "fbsd_ldns_s3.h"
        [=[const char *fbsd_libldns_abi_version(void);]=]
        [=[#include "fbsd_ldns_s3.h"
const char *fbsd_libldns_abi_version(void) { return "1.8.4"; }]=]
    )
endif()

if(EXISTS "${_FBSD_CODEGEN_DIR}/ncurses/fbsd_curses.c")
    set(_CURSES_VER_C "${_FBSD_S3_GEN_DIR}/src/fbsd_curses_ver.c")
    file(WRITE "${_CURSES_VER_C}" [=[const char *fbsd_libcurses_abi_version(void) { return "6.5"; }
]=])
    freebsd_add_section3_library(fbsd_libtinfow
        OUTPUT_NAME "fbsd_tinfow"
        SOURCES "${_FBSD_CODEGEN_DIR}/ncurses/fbsd_curses.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/ncurses"
        DATA_EXPORTS stdscr curscr newscr LINES COLS COLORS COLOR_PAIRS TABSIZE ESCDELAY
                     acs_map _nc_wacs ttytype cur_term PC UP BC ospeed
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/ncurses/term.h" "${_FBSD_CODEGEN_DIR}/ncurses/termcap.h"
    )
    if(TARGET fbsd_libtinfow AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libtinfow PUBLIC FBSD_CURSES_STATIC=1)
    endif()
    freebsd_add_section3_library(fbsd_libcurses
        OUTPUT_NAME "fbsd_curses"
        SOURCES "${_CURSES_VER_C}"
        INCLUDES "${_FBSD_CODEGEN_DIR}/ncurses"
        LIBS fbsd_libtinfow
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/ncurses/curses.h" "${_FBSD_CODEGEN_DIR}/ncurses/ncurses.h"
                       "${_FBSD_CODEGEN_DIR}/ncurses/unctrl.h"
    )
    if(TARGET fbsd_libcurses AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libcurses PUBLIC FBSD_CURSES_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libtinfow "fbsd_tinfow" "fbsd_tinfow_s3.h"
        [=[const char *fbsd_libtinfow_abi_version(void);]=]
        [=[#include "fbsd_tinfow_s3.h"
const char *fbsd_libtinfow_abi_version(void) { return "6.5"; }]=]
    )
    _fbsd_define_portable_s3_unit(fbsd_libcurses "fbsd_curses" "fbsd_curses_s3.h"
        [=[const char *fbsd_libcurses_abi_version(void);]=]
        [=[#include "fbsd_curses_s3.h"
const char *fbsd_libcurses_abi_version(void) { return "6.5"; }]=]
        LIBS fbsd_libtinfow
    )
endif()

if(EXISTS "${_FBSD_CODEGEN_DIR}/libedit/fbsd_edit.c")
    freebsd_add_section3_library(fbsd_libedit
        OUTPUT_NAME "fbsd_edit"
        SOURCES "${_FBSD_CODEGEN_DIR}/libedit/fbsd_edit.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/libedit"
        DATA_EXPORTS rl_readline_name rl_line_buffer rl_point rl_end
                     rl_attempted_completion_over rl_attempted_completion_function
                     rl_completion_entry_function
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/libedit/histedit.h"
    )
    if(TARGET fbsd_libedit AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libedit PUBLIC FBSD_EDIT_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libedit "fbsd_edit" "fbsd_edit_s3.h"
        [=[const char *fbsd_libedit_abi_version(void);]=]
        [=[#include "fbsd_edit_s3.h"
const char *fbsd_libedit_abi_version(void) { return "3.1"; }]=]
    )
endif()

set(_BSDDLG_DIR "${FREEBSD_SRC_DIR}/contrib/bsddialog/lib")
if(EXISTS "${_BSDDLG_DIR}/bsddialog.h" AND EXISTS "${_FBSD_CODEGEN_DIR}/ncurses/curses.h")
    file(GLOB _BSDDLG_SRCS "${_BSDDLG_DIR}/*.c")
    list(FILTER _BSDDLG_SRCS EXCLUDE REGEX [=[menubox\.c$]=])
    _fbsd_resolve_staged_or_upstream(_BSDDLG_MENUBOX_C "contrib/bsddialog/lib/menubox.c")
    list(APPEND _BSDDLG_SRCS "${_BSDDLG_MENUBOX_C}")
    freebsd_add_section3_library(fbsd_libbsddialog
        OUTPUT_NAME "fbsd_bsddialog"
        SOURCES ${_BSDDLG_SRCS}
        INCLUDES "${_BSDDLG_DIR}" "${_FBSD_CODEGEN_DIR}/ncurses"
        LIBS fbsd_libcurses fbsd_libtinfow
        PUBLIC_HEADERS "${_BSDDLG_DIR}/bsddialog.h" "${_BSDDLG_DIR}/bsddialog_theme.h"
                       "${_BSDDLG_DIR}/bsddialog_progressview.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libbsddialog "fbsd_bsddialog" "fbsd_bsddialog_s3.h"
        [=[const char *fbsd_libbsddialog_abi_version(void);]=]
        [=[#include "fbsd_bsddialog_s3.h"
const char *fbsd_libbsddialog_abi_version(void) { return "1.0.4"; }]=]
        LIBS fbsd_libcurses fbsd_libtinfow
    )
endif()

if(EXISTS "${_FBSD_CODEGEN_DIR}/libdialog/fbsd_dialog.c" AND EXISTS "${_FBSD_CODEGEN_DIR}/ncurses/curses.h")
    freebsd_add_section3_library(fbsd_libdialog
        OUTPUT_NAME "fbsd_dialog"
        SOURCES "${_FBSD_CODEGEN_DIR}/libdialog/fbsd_dialog.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/libdialog" "${_FBSD_CODEGEN_DIR}/ncurses"
        LIBS fbsd_libcurses fbsd_libtinfow
        DATA_EXPORTS dialog_state dialog_vars dlg_color_table
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/libdialog/dialog.h"
                       "${_FBSD_CODEGEN_DIR}/libdialog/dlg_colors.h"
                       "${_FBSD_CODEGEN_DIR}/libdialog/dlg_config.h"
                       "${_FBSD_CODEGEN_DIR}/libdialog/dlg_keys.h"
    )
    if(TARGET fbsd_libdialog AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libdialog PUBLIC FBSD_DIALOG_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libdialog "fbsd_dialog" "fbsd_dialog_s3.h"
        [=[const char *fbsd_libdialog_abi_version(void);]=]
        [=[#include "fbsd_dialog_s3.h"
const char *fbsd_libdialog_abi_version(void) { return "1.3"; }]=]
        LIBS fbsd_libcurses fbsd_libtinfow
    )
endif()

set(_FIGPAR_DIR "${FREEBSD_SRC_DIR}/lib/libfigpar")
if(EXISTS "${_FIGPAR_DIR}/figpar.c")
    freebsd_add_section3_library(fbsd_libfigpar
        OUTPUT_NAME "fbsd_figpar"
        SOURCES "${_FIGPAR_DIR}/figpar.c" "${_FIGPAR_DIR}/string_m.c"
        INCLUDES "${_FIGPAR_DIR}"
        DATA_EXPORTS figpar_dummy_config
        PUBLIC_HEADERS "${_FIGPAR_DIR}/figpar.h" "${_FIGPAR_DIR}/string_m.h"
    )
else()
    _fbsd_define_portable_s3_unit(fbsd_libfigpar "fbsd_figpar" "fbsd_figpar_s3.h"
        [=[const char *fbsd_libfigpar_abi_version(void);]=]
        [=[#include "fbsd_figpar_s3.h"
const char *fbsd_libfigpar_abi_version(void) { return "15.0.0"; }]=]
    )
endif()

set(_DPV_DIR "${FREEBSD_SRC_DIR}/lib/libdpv")
if(EXISTS "${_DPV_DIR}/dpv.c" AND EXISTS "${_FIGPAR_DIR}/figpar.h")
    set(_DPV_INC_DIRS "${_DPV_DIR}" "${_FIGPAR_DIR}" "${_FBSD_CODEGEN_DIR}/libdialog" "${_FBSD_CODEGEN_DIR}/ncurses")
    set(_DPV_PUB_HDR "${_DPV_DIR}/dpv.h")
    if(EXISTS "${_FBSD_CODEGEN_DIR}/libdpv/dpv.h")
        list(INSERT _DPV_INC_DIRS 0 "${_FBSD_CODEGEN_DIR}/libdpv")
        set(_DPV_PUB_HDR "${_FBSD_CODEGEN_DIR}/libdpv/dpv.h")
    endif()
    freebsd_add_section3_library(fbsd_libdpv
        OUTPUT_NAME "fbsd_dpv"
        SOURCES "${_DPV_DIR}/dialog_util.c" "${_DPV_DIR}/dialogrc.c" "${_DPV_DIR}/dprompt.c"
                "${_DPV_DIR}/dpv.c" "${_DPV_DIR}/status.c" "${_DPV_DIR}/util.c"
        INCLUDES ${_DPV_INC_DIRS}
        DEFINES DIALOG="dialog" XDIALOG="Xdialog"
        LIBS fbsd_libdialog fbsd_libfigpar fbsd_libutil fbsd_libcurses fbsd_libtinfow
        DATA_EXPORTS dpv_overall_read dpv_interrupt dpv_abort
        PUBLIC_HEADERS "${_DPV_PUB_HDR}"
    )
    if(TARGET fbsd_libdpv AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libdpv PUBLIC FBSD_DPV_STATIC=1)
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libdpv "fbsd_dpv" "fbsd_dpv_s3.h"
        [=[const char *fbsd_libdpv_abi_version(void);]=]
        [=[#include "fbsd_dpv_s3.h"
const char *fbsd_libdpv_abi_version(void) { return "15.0.0"; }]=]
        LIBS fbsd_libdialog fbsd_libfigpar
    )
endif()

if(EXISTS "${_FBSD_CODEGEN_DIR}/libsys/fbsd_sys.c")
    freebsd_add_section3_library(fbsd_libsys
        OUTPUT_NAME "fbsd_sys"
        SOURCES "${_FBSD_CODEGEN_DIR}/libsys/fbsd_sys.c"
        INCLUDES "${_FBSD_CODEGEN_DIR}/libsys"
        DATA_EXPORTS openpam_debug openpam_ttyconv_timeout pam_item_name _pam_item_name ypresp_allfn ypresp_data
        PUBLIC_HEADERS "${_FBSD_CODEGEN_DIR}/libsys/security/pam_appl.h"
                       "${_FBSD_CODEGEN_DIR}/libsys/security/openpam.h"
                       "${_FBSD_CODEGEN_DIR}/libsys/rpcsvc/ypclnt.h"
                       "${_FBSD_CODEGEN_DIR}/libsys/sys/nv.h"
    )
    if(TARGET fbsd_libsys AND NOT FREEBSD_SECTION3_SHARED)
        target_compile_definitions(fbsd_libsys PUBLIC FBSD_SYS_STATIC=1)
    endif()
    if(TARGET fbsd_libsys AND UNIX)
        find_library(FBSD_CRYPT_LIB crypt)
        if(FBSD_CRYPT_LIB)
            target_link_libraries(fbsd_libsys PUBLIC "${FBSD_CRYPT_LIB}")
        elseif(NOT APPLE)
            target_compile_definitions(fbsd_libsys PRIVATE FBSD_NEED_FALLBACK_CRYPT=1)
        endif()
    endif()
else()
    _fbsd_define_portable_s3_unit(fbsd_libsys "fbsd_sys" "fbsd_sys_s3.h"
        [=[const char *fbsd_libsys_abi_version(void);]=]
        [=[#include "fbsd_sys_s3.h"
const char *fbsd_libsys_abi_version(void) { return "FreeBSD-15.0.0"; }]=]
    )
endif()
