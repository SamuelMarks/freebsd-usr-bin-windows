# =============================================================================
# CMakeLists.txt - FreeBSD usr.bin Native Windows (MSVC) & 32-bit DOS Build
#
# Orchestrates locating ../freebsd-src/usr.bin (all 280 entries), deterministic
# build-time header, Section 3 SHARED/STATIC library, per-binary CMakeLists.txt,
# and multicall C source generation, C99/C11/GNU-to-C89/MSVC/Watcom AST source
# transformation via auto-win-msvc, POSIX/BSD/FreeBSD polyfill linking, CPack
# installer packaging (ZIP, NSIS, WiX), and CTest functional verification.
# =============================================================================

cmake_minimum_required(VERSION 3.24)

if(POLICY CMP0141)
    cmake_policy(SET CMP0141 NEW)
endif()

set(_fbsd_user_had_build_type OFF)
if(DEFINED CACHE{CMAKE_BUILD_TYPE})
    set(_fbsd_user_had_build_type ON)
endif()

project(freebsd_usr_bin_windows VERSION 15.0.0 LANGUAGES C)

option(BUILD_TESTING "Enable CTest functional test suite" ON)
option(FREEBSD_BUILD_INDIVIDUAL "Build standalone per-binary executables via generated per-binary CMakeLists.txt" ON)
option(FREEBSD_BUILD_MULTICALL "Build unified freebsd-usr-bin multicall executable" ON)
option(FREEBSD_SECTION3_SHARED "Build FreeBSD Section 3 backing libraries as SHARED (.dll/.so/.dylib) on non-DOS targets" ON)
option(FREEBSD_USR_BIN_BUILD_CLANG "Compile full contrib/llvm-project 43-tool usr.bin/clang subtree" OFF)
option(FREEBSD_USR_BIN_BUILD_OFED "Compile full contrib/ofed InfiniBand usr.bin/ofed subtree" OFF)
option(FREEBSD_USR_BIN_BUILD_KYUA "Compile full contrib/kyua C++20 usr.bin/kyua subtree" OFF)
option(FREEBSD_DOS_FULL_SUITE "Build full 130+ DOS binary and multicall suite even when BUILD_TESTING=ON" OFF)

# -----------------------------------------------------------------------------
# 1. Detect OpenWatcom / 16-bit Real-Mode (I86) & 32-bit Protected-Mode (I386) DOS
# -----------------------------------------------------------------------------
set(FREEBSD_TARGET_DOS OFF)
set(FREEBSD_DOS_I86 OFF)
if(WATCOM OR CMAKE_SYSTEM_NAME STREQUAL "DOS" OR CMAKE_C_COMPILER_ID MATCHES "Watcom")
    set(FREEBSD_TARGET_DOS ON)
    if(NOT _fbsd_user_had_build_type)
        set(CMAKE_BUILD_TYPE "MinSizeRel" CACHE STRING "Default build type for DOS" FORCE)
    endif()
    set(BUILD_SHARED_LIBS OFF CACHE BOOL "Disable shared libraries on DOS" FORCE)
    set(FREEBSD_SECTION3_SHARED OFF CACHE BOOL "Static Section 3 libraries on DOS" FORCE)
    get_filename_component(_fbsd_ow_cc_name "${CMAKE_C_COMPILER}" NAME)
    if(CMAKE_SYSTEM_PROCESSOR STREQUAL "I86"
       OR CMAKE_SIZEOF_VOID_P EQUAL 2
       OR _fbsd_ow_cc_name MATCHES "^wcl(\\.exe)?$")
        set(FREEBSD_DOS_I86 ON)
    endif()
    unset(_fbsd_ow_cc_name)
endif()

# -----------------------------------------------------------------------------
# 2. Locate Upstream FreeBSD Source Tree (../freebsd-src or ./freebsd-src)
# -----------------------------------------------------------------------------
if(NOT DEFINED FREEBSD_SRC_DIR OR "${FREEBSD_SRC_DIR}" STREQUAL "")
    set(_fbsd_candidates
        "${CMAKE_CURRENT_SOURCE_DIR}/../freebsd-src"
        "${CMAKE_CURRENT_SOURCE_DIR}/freebsd-src"
    )
    foreach(_cand IN LISTS _fbsd_candidates)
        get_filename_component(_cand_abs "${_cand}" ABSOLUTE)
        if(EXISTS "${_cand_abs}/usr.bin/Makefile")
            set(FREEBSD_SRC_DIR "${_cand_abs}" CACHE PATH "Path to upstream freebsd-src" FORCE)
            break()
        endif()
    endforeach()
endif()

if(NOT DEFINED FREEBSD_SRC_DIR OR NOT EXISTS "${FREEBSD_SRC_DIR}/usr.bin/Makefile")
    message(FATAL_ERROR "Upstream freebsd-src/usr.bin/Makefile not found at FREEBSD_SRC_DIR='${FREEBSD_SRC_DIR}'")
endif()
message(STATUS "Using FreeBSD source directory: ${FREEBSD_SRC_DIR}")

# -----------------------------------------------------------------------------
# 3. Integrate auto-win-msvc Compatibility Layer & Source Transformer
# -----------------------------------------------------------------------------
include(FetchContent)

set(_saved_build_testing "${BUILD_TESTING}")
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(AUTO_WIN_MSVC_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(AUTO_WIN_MSVC_UNICODE OFF CACHE BOOL "" FORCE)

option(FREEBSD_AUTO_WIN_MSVC_PREFER_LOCAL
    "Use sibling ../auto-win-msvc or ./auto-win-msvc checkout when present" ON)
if(NOT FREEBSD_AUTO_WIN_MSVC_PREFER_LOCAL AND _FBSD_AUTO_DETECTED_AWM)
    unset(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC CACHE)
    unset(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC)
    unset(_FBSD_AUTO_DETECTED_AWM CACHE)
endif()
if(FREEBSD_AUTO_WIN_MSVC_PREFER_LOCAL AND "${FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC}" STREQUAL "")
    foreach(_awm_cand
        "${CMAKE_CURRENT_SOURCE_DIR}/../auto-win-msvc"
        "${CMAKE_CURRENT_SOURCE_DIR}/auto-win-msvc"
    )
        if(EXISTS "${_awm_cand}/CMakeLists.txt")
            get_filename_component(_awm_abs "${_awm_cand}" ABSOLUTE)
            set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_awm_abs}")
            set(_FBSD_AUTO_DETECTED_AWM ON CACHE INTERNAL "Auto-detected local auto-win-msvc")
            break()
        endif()
    endforeach()
endif()

set(FETCHCONTENT_UPDATES_DISCONNECTED_AUTO_WIN_MSVC OFF CACHE BOOL
    "Always fetch latest master for auto_win_msvc" FORCE)
file(REMOVE "${CMAKE_BINARY_DIR}/CMakeFiles/fc-stamp/auto_win_msvc/update.stamp")
foreach(_fbsd_git_env
    GIT_ALTERNATE_OBJECT_DIRECTORIES
    GIT_COMMON_DIR
    GIT_CONFIG
    GIT_CONFIG_COUNT
    GIT_CONFIG_PARAMETERS
    GIT_DIR
    GIT_GRAFT_FILE
    GIT_IMPLICIT_WORK_TREE
    GIT_INDEX_FILE
    GIT_NAMESPACE
    GIT_NO_REPLACE_OBJECTS
    GIT_OBJECT_DIRECTORY
    GIT_PREFIX
    GIT_REPLACE_REF_BASE
    GIT_SHALLOW_FILE
    GIT_SUPER_PREFIX
    GIT_WORK_TREE
)
    unset(ENV{${_fbsd_git_env}})
endforeach()
unset(_fbsd_git_env)
FetchContent_Declare(
    auto_win_msvc
    GIT_REPOSITORY https://github.com/SamuelMarks/auto-win-msvc.git
    GIT_TAG master
    GIT_REMOTE_UPDATE_STRATEGY CHECKOUT
)
FetchContent_MakeAvailable(auto_win_msvc)

set(BUILD_TESTING "${_saved_build_testing}" CACHE BOOL "" FORCE)

foreach(_awm_tgt IN ITEMS auto-win-msvc linux-epoll wepoll pcre2-8-static pcre2-posix-static)
    if(TARGET ${_awm_tgt})
        if(NOT FREEBSD_TARGET_DOS)
            set_target_properties(${_awm_tgt} PROPERTIES POSITION_INDEPENDENT_CODE ON)
        endif()
        target_compile_definitions(${_awm_tgt} PRIVATE
            $<$<BOOL:${MSVC}>:_CRT_SECURE_NO_WARNINGS _CRT_RAND_S>
        )
    endif()
endforeach()

if(NOT EXISTS "${auto_win_msvc_SOURCE_DIR}/bsd-dev-headers/include/elf.h")
    message(FATAL_ERROR
        "auto-win-msvc at '${auto_win_msvc_SOURCE_DIR}' is outdated "
        "(missing bsd-dev-headers/include/elf.h and C99/glibc/Watcom portability fixes). "
        "Commit and push the latest ../auto-win-msvc changes to SamuelMarks/auto-win-msvc."
    )
endif()

if(EXISTS "${auto_win_msvc_SOURCE_DIR}/cmake/AutoWinMsvcTransform.cmake")
    include("${auto_win_msvc_SOURCE_DIR}/cmake/AutoWinMsvcTransform.cmake")
endif()

# -----------------------------------------------------------------------------
# 4. Generate Build-Time Headers, Manifests, Per-Binary CMakeLists, & Multicall
# -----------------------------------------------------------------------------
find_package(Python3 QUIET COMPONENTS Interpreter)
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/GenerateFreeBsdHeaders.cmake")

set(FREEBSD_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/freebsd_generated")
set(FREEBSD_GEN_INC "${FREEBSD_GEN_DIR}/include")
set(AWM_POSIX_INCLUDES "${CMAKE_CURRENT_BINARY_DIR}/posix_includes")

set(_fbsd_build_multicall_active "${FREEBSD_BUILD_MULTICALL}")
if(FREEBSD_TARGET_DOS AND (FREEBSD_DOS_I86 OR (BUILD_TESTING AND NOT FREEBSD_DOS_FULL_SUITE)))
    set(_fbsd_build_multicall_active OFF)
endif()
set(_fbsd_gen_extra_args "")
if(NOT _fbsd_build_multicall_active)
    list(APPEND _fbsd_gen_extra_args SKIP_MULTICALL)
endif()

freebsd_generate_all(
    FREEBSD_SRC_DIR "${FREEBSD_SRC_DIR}"
    OUT_DIR "${FREEBSD_GEN_DIR}"
    ${_fbsd_gen_extra_args}
)

include("${FREEBSD_GEN_DIR}/freebsd_usr_bin_targets.cmake")
include("${FREEBSD_GEN_DIR}/enabled_sources.cmake")

message(STATUS "Audited FreeBSD usr.bin entries: ${FREEBSD_USR_BIN_TOTAL_ENTRIES} (${FREEBSD_USR_BIN_UTILITY_COUNT} subdirectories)")

# -----------------------------------------------------------------------------
# 5. Host Bootstrap Tools & True Section 3 Backing Libraries (SHARED / STATIC)
# -----------------------------------------------------------------------------
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/FreeBsdBootstrapTools.cmake")
freebsd_ensure_bootstrap_tools(
    FREEBSD_SRC_DIR "${FREEBSD_SRC_DIR}"
    OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/host_tools"
)

function(_fbsd_configure_c_target _target)
    if("c_std_11" IN_LIST CMAKE_C_COMPILE_FEATURES)
        target_compile_features(${_target} PRIVATE c_std_11)
    endif()
    target_include_directories(${_target} BEFORE PRIVATE
        "${FREEBSD_GEN_INC}"
        "${AWM_POSIX_INCLUDES}"
        "${auto_win_msvc_SOURCE_DIR}/include"
    )
    target_compile_definitions(${_target} PRIVATE
        _GNU_SOURCE=1
        WITHOUT_CAPSICUM=1
        WITHOUT_CASPER=1
        $<$<BOOL:${FREEBSD_TARGET_DOS}>:__DOS__=1>
        $<$<BOOL:${MSVC}>:_CRT_SECURE_NO_WARNINGS _CRT_RAND_S _CRT_NONSTDC_NO_DEPRECATE _CRT_NONSTDC_NO_WARNINGS _CRT_STDIO_ISO_WIDE_SPECIFIERS=1>
        $<$<BOOL:${WIN32}>:WIN32_LEAN_AND_MEAN NOMINMAX>
    )
    set(_awm_cfg "${AWM_POSIX_INCLUDES}/auto-win-msvc-configure.h")
    set(_pre_cfg "${FREEBSD_GEN_INC}/freebsd_compat_preinclude.h")
    if(EXISTS "${_awm_cfg}" AND EXISTS "${_pre_cfg}")
        if(FREEBSD_TARGET_DOS)
            file(TO_NATIVE_PATH "${_awm_cfg}" _awm_nat)
            file(TO_NATIVE_PATH "${_pre_cfg}" _pre_nat)
            target_compile_options(${_target} PRIVATE
                $<$<BOOL:${FREEBSD_DOS_I86}>:-ml -zt=32>
                -zm -zc -os -d0
                "$<$<COMPILE_LANGUAGE:C>:-zastd=c99>"
                "$<$<COMPILE_LANGUAGE:C>:-ze>"
                "$<$<COMPILE_LANGUAGE:C>:-aa>"
                "-fi=${_awm_nat}"
                "-fi=${_pre_nat}"
                "-wcd=201"
                "-wcd=202"
            )
        elseif(MSVC)
            target_compile_options(${_target} PRIVATE
                "/FI${_awm_cfg}"
                "/FI${_pre_cfg}"
                "/wd4005" "/wd4018" "/wd4100" "/wd4127" "/wd4146"
                "/wd4244" "/wd4267" "/wd4389" "/wd4706" "/wd4716" "/wd4996"
            )
        else()
            target_compile_options(${_target} PRIVATE
                "SHELL:-include ${_awm_cfg}"
                "SHELL:-include ${_pre_cfg}"
                "-Wno-unused-parameter"
                "-Wno-sign-compare"
            )
        endif()
    endif()
endfunction()

# Shared static helper target for FreeBSD userland compatibility shims
set(_LIBCOMPAT_RAW "${FREEBSD_GEN_DIR}/src/freebsd_libcompat.c")
if(COMMAND auto_win_msvc_transform_sources AND (MSVC OR FREEBSD_TARGET_DOS))
    auto_win_msvc_transform_sources(
        OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/transformed_libcompat"
        OUTPUT_VAR _LIBCOMPAT_ACTIVE
        SOURCES "${_LIBCOMPAT_RAW}"
    )
else()
    set(_LIBCOMPAT_ACTIVE "${_LIBCOMPAT_RAW}")
endif()

add_library(fbsd_libcompat STATIC)
target_sources(fbsd_libcompat PRIVATE ${_LIBCOMPAT_ACTIVE})
if(NOT FREEBSD_TARGET_DOS)
    set_target_properties(fbsd_libcompat PROPERTIES POSITION_INDEPENDENT_CODE ON)
endif()
_fbsd_configure_c_target(fbsd_libcompat)
target_link_libraries(fbsd_libcompat PUBLIC auto-win-msvc)

if(FREEBSD_TARGET_DOS AND (FREEBSD_DOS_I86 OR (BUILD_TESTING AND NOT FREEBSD_DOS_FULL_SUITE)))
    if(NOT DEFINED FREEBSD_REQUIRED_SECTION3_LIBS)
        if(FREEBSD_DOS_I86)
            set(FREEBSD_REQUIRED_SECTION3_LIBS "fbsd_libutil")
        else()
            set(FREEBSD_REQUIRED_SECTION3_LIBS "fbsd_libutil;fbsd_libxo;fbsd_libbz2")
        endif()
    endif()
endif()

include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/FreeBsdInternalLibs.cmake")

# -----------------------------------------------------------------------------
# 6. Per-Binary Standalone Executables (Generated per_binary/<prog>/CMakeLists.txt)
# -----------------------------------------------------------------------------
if(FREEBSD_BUILD_INDIVIDUAL AND EXISTS "${FREEBSD_GEN_DIR}/per_binary_subdirs.cmake")
    if(NOT DEFINED FREEBSD_ENABLED_BINARIES)
        if(FREEBSD_TARGET_DOS AND (FREEBSD_DOS_I86 OR (BUILD_TESTING AND NOT FREEBSD_DOS_FULL_SUITE)))
            if(FREEBSD_DOS_I86)
                set(FREEBSD_ENABLED_BINARIES
                    true basename dirname jot pagesize printf seq uname
                )
            else()
                set(FREEBSD_ENABLED_BINARIES
                    true basename dirname jot pagesize printf seq uname xo bzip2
                )
            endif()
        elseif(FREEBSD_TARGET_DOS OR NOT (FREEBSD_HOST_YACC AND FREEBSD_HOST_LEX))
            set(FREEBSD_ENABLED_BINARIES
                ${FREEBSD_NATIVE_DIRECT_APPLETS}
                addr2line alias backlight biff bintrans bomtool brandelf
                bsdcat bsdcpio bsdiff bsdunzip bspatch btsockstat bzip2 bzip2recover
                c++filt c89 c99 cap_mkdb chat cksum clear cmp ctlstat ctags dpv
                elfcopy elfctl elfdump env etdump factor file2c finger
                from fsync gcore genl getconf gh-bc grdc hexdump host
                infocmp iscsictl kdump leave lessecho lesskey locate locate.bigram locate.code logins
                lsvfs lzmainfo mesg ministat mkstr ncal netstat nfsstat nohup
                pkgconf pom pr primes protect random readelf resizewin
                rpcgen sdiotool sdiff size smbutil sockstat soelim stdbuf strfile strings
                systat tabs tic toe tput tr truss tset tty ul uname units unstr unvis usbhidaction
                vfontedpr vmstat who xo xopo xstr xzdec yacc ypmatch
                clang command dc kyua lorder man mkdep ofed pagesize ssh-copy-id tests xohtml xolint
            )
            list(REMOVE_DUPLICATES FREEBSD_ENABLED_BINARIES)
        endif()
    endif()
    include("${FREEBSD_GEN_DIR}/per_binary_subdirs.cmake")
endif()

# -----------------------------------------------------------------------------
# 7. Define freebsd-usr-bin Multicall Executable Target
# -----------------------------------------------------------------------------
if(_fbsd_build_multicall_active)
    set(FREEBSD_ACTIVE_SOURCES ${FREEBSD_MULTICALL_SOURCES})

    if(COMMAND auto_win_msvc_transform_sources AND (MSVC OR FREEBSD_TARGET_DOS))
        auto_win_msvc_transform_sources(
            OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/transformed_freebsd"
            OUTPUT_VAR FREEBSD_TRANSFORMED_SOURCES
            SOURCES ${FREEBSD_ACTIVE_SOURCES}
        )
        set(FREEBSD_ACTIVE_SOURCES ${FREEBSD_TRANSFORMED_SOURCES})
    endif()

    add_executable(freebsd-usr-bin)
    target_sources(freebsd-usr-bin PRIVATE ${FREEBSD_ACTIVE_SOURCES})
    set_target_properties(freebsd-usr-bin PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    )
    _fbsd_configure_c_target(freebsd-usr-bin)

    if(FREEBSD_TARGET_DOS)
        target_link_options(freebsd-usr-bin PRIVATE "option" "stack=524288,eliminate")
    elseif(MSVC)
        target_link_options(freebsd-usr-bin PRIVATE "/STACK:8388608")
    endif()

    target_link_libraries(freebsd-usr-bin PRIVATE
        auto-win-msvc
        fbsd_libutil
        fbsd_libxo
        $<$<BOOL:${WIN32}>:bcrypt ws2_32>
        $<$<BOOL:${UNIX}>:m>
    )

    install(TARGETS freebsd-usr-bin RUNTIME DESTINATION bin COMPONENT suite)
endif()

# -----------------------------------------------------------------------------
# 8. Install & CPack Packaging Rules
# -----------------------------------------------------------------------------
foreach(_lic IN ITEMS LICENSE-APACHE LICENSE-MIT LICENSE-CC0 README.md)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${_lic}")
        install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/${_lic}" DESTINATION . COMPONENT suite)
    endif()
endforeach()

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/CPackConfig.cmake")
    include("${CMAKE_CURRENT_SOURCE_DIR}/CPackConfig.cmake")
endif()
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/CPackSourceConfig.cmake")
    include("${CMAKE_CURRENT_SOURCE_DIR}/CPackSourceConfig.cmake")
endif()
include(CPack)

# -----------------------------------------------------------------------------
# 9. CTest Functional Verification Suite (Multicall + Per-Binary + Section 3)
# -----------------------------------------------------------------------------
include(CTest)
if(BUILD_TESTING AND FREEBSD_TARGET_DOS)
    if(TARGET fbsd_bin_true)
        add_test(NAME dos_usr_bin_true COMMAND fbsd_bin_true)
    endif()

    if(TARGET fbsd_bin_basename)
        add_test(
            NAME dos_usr_bin_basename
            COMMAND fbsd_bin_basename usr/local/bin/example.c .c
        )
        set_tests_properties(dos_usr_bin_basename PROPERTIES
            PASS_REGULAR_EXPRESSION "example"
        )
    endif()

    if(TARGET fbsd_bin_dirname)
        add_test(
            NAME dos_usr_bin_dirname
            COMMAND fbsd_bin_dirname usr/local/bin/example.c
        )
        set_tests_properties(dos_usr_bin_dirname PROPERTIES
            PASS_REGULAR_EXPRESSION "usr.*local.*bin"
        )
    endif()

    if(TARGET fbsd_bin_printf)
        add_test(
            NAME dos_usr_bin_printf
            COMMAND fbsd_bin_printf %s:%x hex 255
        )
        set_tests_properties(dos_usr_bin_printf PROPERTIES
            PASS_REGULAR_EXPRESSION "hex:ff"
        )
    endif()

    if(TARGET fbsd_bin_seq)
        add_test(
            NAME dos_usr_bin_seq
            COMMAND fbsd_bin_seq 1 5
        )
        set_tests_properties(dos_usr_bin_seq PROPERTIES
            PASS_REGULAR_EXPRESSION "1.*2.*3.*4.*5"
        )
    endif()

    if(TARGET fbsd_bin_jot)
        add_test(
            NAME dos_usr_bin_jot
            COMMAND fbsd_bin_jot 4 10
        )
        set_tests_properties(dos_usr_bin_jot PROPERTIES
            PASS_REGULAR_EXPRESSION "10.*11.*12.*13"
        )
    endif()

    if(TARGET fbsd_bin_pagesize)
        add_test(
            NAME dos_usr_bin_pagesize
            COMMAND fbsd_bin_pagesize
        )
        set_tests_properties(dos_usr_bin_pagesize PROPERTIES
            PASS_REGULAR_EXPRESSION "(4096|8192|16384|65536)"
        )
    endif()

    if(TARGET fbsd_bin_uname)
        add_test(
            NAME dos_usr_bin_uname
            COMMAND fbsd_bin_uname -s
        )
        set_tests_properties(dos_usr_bin_uname PROPERTIES
            PASS_REGULAR_EXPRESSION "[A-Za-z]+"
        )
    endif()

    if(TARGET fbsd_bin_xo)
        add_test(
            NAME dos_usr_bin_xo_libxo_json
            COMMAND fbsd_bin_xo --json {:status/%s} ok
        )
        set_tests_properties(dos_usr_bin_xo_libxo_json PROPERTIES
            PASS_REGULAR_EXPRESSION [=["status":"ok"]=]
        )
    endif()

    if(TARGET fbsd_bin_bzip2)
        add_test(
            NAME dos_usr_bin_bzip2_section3
            COMMAND fbsd_bin_bzip2 --help
        )
        set_tests_properties(dos_usr_bin_bzip2_section3 PROPERTIES
            PASS_REGULAR_EXPRESSION "bzip2"
        )
    endif()
elseif(BUILD_TESTING AND NOT FREEBSD_TARGET_DOS)
    set(_test_runner_prefix "")
    if(CMAKE_CROSSCOMPILING AND CMAKE_SYSTEM_NAME STREQUAL "Windows")
        find_program(WINE_EXECUTABLE NAMES wine wine64)
        if(WINE_EXECUTABLE)
            set(_test_runner_prefix "${WINE_EXECUTABLE}")
        endif()
    endif()

    if(TARGET freebsd-usr-bin)
        add_test(
            NAME freebsd_usr_bin_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" --version
        )
        set_tests_properties(freebsd_usr_bin_version PROPERTIES
            PASS_REGULAR_EXPRESSION "freebsd-usr-bin 15.0.0.*280 entries"
        )

        add_test(
            NAME freebsd_usr_bin_list
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" --list
        )
        set_tests_properties(freebsd_usr_bin_list PROPERTIES
            PASS_REGULAR_EXPRESSION "basename"
        )

        add_test(
            NAME freebsd_usr_bin_true
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" true
        )

        add_test(
            NAME freebsd_usr_bin_false
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" false
        )
        set_tests_properties(freebsd_usr_bin_false PROPERTIES WILL_FAIL TRUE)

        add_test(
            NAME freebsd_usr_bin_basename
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" basename /usr/local/bin/example.c .c
        )
        set_tests_properties(freebsd_usr_bin_basename PROPERTIES
            PASS_REGULAR_EXPRESSION "example"
        )

        add_test(
            NAME freebsd_usr_bin_dirname
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" dirname /usr/local/bin/example.c
        )
        set_tests_properties(freebsd_usr_bin_dirname PROPERTIES
            PASS_REGULAR_EXPRESSION "usr.*local.*bin"
        )

        add_test(
            NAME freebsd_usr_bin_printf_multicall
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" printf "%s-%03d" "fbsd" "7"
        )
        set_tests_properties(freebsd_usr_bin_printf_multicall PROPERTIES
            PASS_REGULAR_EXPRESSION "fbsd-007"
        )

        add_test(
            NAME freebsd_usr_bin_seq
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" seq 1 5
        )
        set_tests_properties(freebsd_usr_bin_seq PROPERTIES
            PASS_REGULAR_EXPRESSION "1.*2.*3.*4.*5"
        )

        add_test(
            NAME freebsd_usr_bin_jot
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" jot 4 10
        )
        set_tests_properties(freebsd_usr_bin_jot PROPERTIES
            PASS_REGULAR_EXPRESSION "10.*11.*12.*13"
        )

        add_test(
            NAME freebsd_usr_bin_banner
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" banner OK
        )
        set_tests_properties(freebsd_usr_bin_banner PROPERTIES
            PASS_REGULAR_EXPRESSION "#"
        )

        add_test(
            NAME freebsd_usr_bin_pagesize
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" pagesize
        )
        set_tests_properties(freebsd_usr_bin_pagesize PROPERTIES
            PASS_REGULAR_EXPRESSION "(4096|8192|16384|65536)"
        )

        add_test(
            NAME freebsd_usr_bin_dc_multicall
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:freebsd-usr-bin>" dc -e "6 7 * p"
        )
        set_tests_properties(freebsd_usr_bin_dc_multicall PROPERTIES
            PASS_REGULAR_EXPRESSION "42"
        )

        if(NOT _test_runner_prefix AND Python3_Interpreter_FOUND)
            add_test(
                NAME freebsd_usr_bin_functional_suite
                COMMAND "${Python3_EXECUTABLE}" -m scripts.run_freebsd_usr_bin_tests
                        "$<TARGET_FILE:freebsd-usr-bin>"
                WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            )
        endif()
    endif()

    if(TARGET fbsd_bin_printf)
        add_test(
            NAME standalone_printf_bin
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_printf>" "%s:%x" "hex" "255"
        )
        set_tests_properties(standalone_printf_bin PROPERTIES
            PASS_REGULAR_EXPRESSION "hex:ff"
        )
    endif()

    if(TARGET fbsd_bin_dc)
        add_test(
            NAME standalone_dc_bin
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_dc>" -e "9 8 * p"
        )
        set_tests_properties(standalone_dc_bin PROPERTIES
            PASS_REGULAR_EXPRESSION "72"
        )
    endif()

    if(TARGET fbsd_bin_bzip2)
        add_test(
            NAME standalone_bzip2_section3_dll_help
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_bzip2>" --help
        )
    endif()

    if(TARGET fbsd_bin_bsdcat)
        add_test(
            NAME standalone_bsdcat_libarchive_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_bsdcat>" --version
        )
        set_tests_properties(standalone_bsdcat_libarchive_version PROPERTIES
            PASS_REGULAR_EXPRESSION "libarchive"
        )
    endif()

    if(TARGET fbsd_bin_xzdec)
        add_test(
            NAME standalone_xzdec_liblzma_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_xzdec>" --version
        )
        set_tests_properties(standalone_xzdec_liblzma_version PROPERTIES
            PASS_REGULAR_EXPRESSION "liblzma"
        )
    endif()

    if(TARGET fbsd_bin_readelf)
        add_test(
            NAME standalone_readelf_libelftc_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_readelf>" --version
        )
        set_tests_properties(standalone_readelf_libelftc_version PROPERTIES
            PASS_REGULAR_EXPRESSION "elftoolchain"
        )
    endif()

    if(TARGET fbsd_bin_cksum)
        add_test(
            NAME standalone_cksum_crc32
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_cksum>" "${CMAKE_CURRENT_SOURCE_DIR}/README.md"
        )
        set_tests_properties(standalone_cksum_crc32 PROPERTIES
            PASS_REGULAR_EXPRESSION "[0-9]+ [0-9]+ .*README\\.md"
        )
    endif()

    if(TARGET fbsd_bin_pkgconf)
        add_test(
            NAME standalone_pkgconf_section3_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_pkgconf>" --version
        )
        set_tests_properties(standalone_pkgconf_section3_version PROPERTIES
            PASS_REGULAR_EXPRESSION "[0-9]+\\.[0-9]+"
        )
    endif()

    if(TARGET fbsd_bin_xo)
        add_test(
            NAME standalone_xo_libxo_json
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_xo>" --json "{:status/%s}" "ok"
        )
        set_tests_properties(standalone_xo_libxo_json PROPERTIES
            PASS_REGULAR_EXPRESSION [=["status":"ok"]=]
        )
    endif()

    if(TARGET fbsd_bin_ncal)
        add_test(
            NAME standalone_ncal_libcalendar_tinfow
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_ncal>" -h -C 11 2026
        )
        set_tests_properties(standalone_ncal_libcalendar_tinfow PROPERTIES
            PASS_REGULAR_EXPRESSION "November 2026"
        )
    endif()

    if(TARGET fbsd_bin_yacc)
        add_test(
            NAME standalone_yacc_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_yacc>" -V
        )
        set_tests_properties(standalone_yacc_version PROPERTIES
            PASS_REGULAR_EXPRESSION "yacc"
        )
    endif()

    if(TARGET fbsd_bin_awk)
        add_test(
            NAME standalone_awk_eval
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_awk>" "BEGIN { print 6 * 7 }"
        )
        set_tests_properties(standalone_awk_eval PROPERTIES
            PASS_REGULAR_EXPRESSION "42"
        )
    endif()

    if(TARGET fbsd_bin_bsdtar)
        add_test(
            NAME standalone_bsdtar_libarchive_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_bsdtar>" --version
        )
        set_tests_properties(standalone_bsdtar_libarchive_version PROPERTIES
            PASS_REGULAR_EXPRESSION "bsdtar"
        )
    endif()

    if(TARGET fbsd_bin_xz)
        add_test(
            NAME standalone_xz_liblzma_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_xz>" --version
        )
        set_tests_properties(standalone_xz_liblzma_version PROPERTIES
            PASS_REGULAR_EXPRESSION "xz"
        )
    endif()

    if(TARGET fbsd_bin_grep)
        add_test(
            NAME standalone_grep_libregex_match
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_grep>" -c "FreeBSD" "${CMAKE_CURRENT_SOURCE_DIR}/README.md"
        )
        set_tests_properties(standalone_grep_libregex_match PROPERTIES
            PASS_REGULAR_EXPRESSION "[1-9][0-9]*"
        )
    endif()

    if(TARGET fbsd_bin_diff)
        add_test(
            NAME standalone_diff_libdiff_identical
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_diff>" "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT" "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT"
        )
    endif()

    if(TARGET fbsd_bin_id)
        add_test(
            NAME standalone_id_numeric_uid
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_id>" -u
        )
        set_tests_properties(standalone_id_numeric_uid PROPERTIES
            PASS_REGULAR_EXPRESSION "[0-9]+"
        )
    endif()

    if(TARGET fbsd_bin_drill)
        add_test(
            NAME standalone_drill_libldns_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_drill>" -v
        )
        set_tests_properties(standalone_drill_libldns_version PROPERTIES
            PASS_REGULAR_EXPRESSION "drill"
        )
    endif()

    if(TARGET fbsd_bin_nm)
        add_test(
            NAME standalone_nm_libelftc_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_nm>" -V
        )
        set_tests_properties(standalone_nm_libelftc_version PROPERTIES
            PASS_REGULAR_EXPRESSION "nm"
        )
    endif()

    if(TARGET fbsd_bin_tput)
        add_test(
            NAME standalone_tput_ncurses_version
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_tput>" -V
        )
        set_tests_properties(standalone_tput_ncurses_version PROPERTIES
            PASS_REGULAR_EXPRESSION "ncurses"
        )
    endif()

    if(TARGET fbsd_bin_vmstat)
        add_test(
            NAME standalone_vmstat_libxo_json
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_vmstat>" --libxo json -s
        )
        set_tests_properties(standalone_vmstat_libxo_json PROPERTIES
            PASS_REGULAR_EXPRESSION "free-pages"
        )
    endif()

    if(TARGET fbsd_bin_netstat)
        add_test(
            NAME standalone_netstat_libxo_json
            COMMAND ${_test_runner_prefix} "$<TARGET_FILE:fbsd_bin_netstat>" --libxo json -r
        )
        set_tests_properties(standalone_netstat_libxo_json PROPERTIES
            PASS_REGULAR_EXPRESSION "127\\.0\\.0\\.1"
        )
    endif()
endif()
