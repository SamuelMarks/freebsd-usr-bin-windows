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

if(POLICY CMP0091)
    cmake_policy(SET CMP0091 NEW)
    set(CMAKE_POLICY_DEFAULT_CMP0091 NEW)
endif()
if(POLICY CMP0114)
    cmake_policy(SET CMP0114 NEW)
endif()
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()
if(POLICY CMP0141)
    cmake_policy(SET CMP0141 NEW)
    set(CMAKE_POLICY_DEFAULT_CMP0141 NEW)
endif()
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

project(freebsd_usr_bin_windows VERSION 15.0.0 LANGUAGES C)

if(MSVC AND NOT CMAKE_HOST_WIN32 AND NOT CMAKE_NM)
    find_program(_FBSD_HOST_NM
        NAMES llvm-nm x86_64-w64-mingw32-nm nm
        PATHS /opt/homebrew/opt/llvm/bin /usr/local/opt/llvm/bin
    )
    if(_FBSD_HOST_NM)
        set(CMAKE_NM "${_FBSD_HOST_NM}" CACHE FILEPATH "Path to nm for WINDOWS_EXPORT_ALL_SYMBOLS" FORCE)
    endif()
endif()

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED OFF)
set(FREEBSD_VERSION "15.0.0" CACHE STRING "Upstream FreeBSD release version")

option(BUILD_TESTING "Enable CTest functional test suite" ON)
option(FREEBSD_BUILD_INDIVIDUAL "Build standalone per-binary executables via generated per-binary CMakeLists.txt" ON)
option(FREEBSD_BUILD_MULTICALL "Build unified freebsd-usr-bin multicall executable" ON)
option(FREEBSD_SECTION3_SHARED "Build FreeBSD Section 3 backing libraries as SHARED (.dll/.so/.dylib) on non-DOS targets" ON)
option(FREEBSD_USR_BIN_BUILD_CLANG "Compile full contrib/llvm-project 43-tool usr.bin/clang subtree" OFF)
option(FREEBSD_USR_BIN_BUILD_OFED "Compile full contrib/ofed InfiniBand usr.bin/ofed subtree" OFF)
option(FREEBSD_USR_BIN_BUILD_KYUA "Compile full contrib/kyua C++20 usr.bin/kyua subtree" OFF)

# -----------------------------------------------------------------------------
# 1. Detect OpenWatcom / 32-bit Protected-Mode DOS Target
# -----------------------------------------------------------------------------
set(FREEBSD_TARGET_DOS OFF)
if(WATCOM OR CMAKE_SYSTEM_NAME STREQUAL "DOS" OR CMAKE_C_COMPILER_ID MATCHES "Watcom")
    set(FREEBSD_TARGET_DOS ON)
    set(BUILD_SHARED_LIBS OFF CACHE BOOL "Disable shared libraries on DOS" FORCE)
    set(FREEBSD_SECTION3_SHARED OFF CACHE BOOL "Static Section 3 libraries on DOS" FORCE)
else()
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
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
if(MSVC)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS _CRT_RAND_S)
endif()

if(NOT DEFINED FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC)
    foreach(_awm_cand
        "${CMAKE_CURRENT_SOURCE_DIR}/../auto-win-msvc"
        "${CMAKE_CURRENT_SOURCE_DIR}/auto-win-msvc"
    )
        if(EXISTS "${_awm_cand}/CMakeLists.txt")
            get_filename_component(_awm_abs "${_awm_cand}" ABSOLUTE)
            set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_awm_abs}" CACHE PATH "Local auto-win-msvc" FORCE)
            break()
        endif()
    endforeach()
endif()

FetchContent_Declare(
    auto_win_msvc
    GIT_REPOSITORY https://github.com/SamuelMarks/auto-win-msvc.git
    GIT_TAG master
)
FetchContent_MakeAvailable(auto_win_msvc)

set(BUILD_TESTING "${_saved_build_testing}" CACHE BOOL "" FORCE)

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

freebsd_generate_all(
    FREEBSD_SRC_DIR "${FREEBSD_SRC_DIR}"
    OUT_DIR "${FREEBSD_GEN_DIR}"
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

add_library(fbsd_libcompat STATIC ${_LIBCOMPAT_ACTIVE})
set_target_properties(fbsd_libcompat PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(fbsd_libcompat BEFORE PRIVATE
    "${FREEBSD_GEN_INC}"
    "${AWM_POSIX_INCLUDES}"
    "${auto_win_msvc_SOURCE_DIR}/include"
)
target_compile_definitions(fbsd_libcompat PRIVATE
    _GNU_SOURCE=1
    WITHOUT_CAPSICUM=1
    WITHOUT_CASPER=1
    $<$<BOOL:${FREEBSD_TARGET_DOS}>:__DOS__=1>
    $<$<BOOL:${MSVC}>:_CRT_SECURE_NO_WARNINGS>
    $<$<BOOL:${MSVC}>:_CRT_NONSTDC_NO_DEPRECATE>
    $<$<BOOL:${MSVC}>:_CRT_NONSTDC_NO_WARNINGS>
    $<$<BOOL:${WIN32}>:WIN32_LEAN_AND_MEAN>
    $<$<BOOL:${WIN32}>:NOMINMAX>
)
set(_LC_AWM_CFG "${AWM_POSIX_INCLUDES}/auto-win-msvc-configure.h")
set(_LC_PREINC "${FREEBSD_GEN_INC}/freebsd_compat_preinclude.h")
if(EXISTS "${_LC_AWM_CFG}" AND EXISTS "${_LC_PREINC}")
    if(FREEBSD_TARGET_DOS)
        file(TO_NATIVE_PATH "${_LC_AWM_CFG}" _LC_AWM_NAT)
        file(TO_NATIVE_PATH "${_LC_PREINC}" _LC_PRE_NAT)
        target_compile_options(fbsd_libcompat PRIVATE
            "$<$<COMPILE_LANGUAGE:C>:-zastd=c99>"
            "$<$<COMPILE_LANGUAGE:C>:-ze>"
            "$<$<COMPILE_LANGUAGE:C>:-aa>"
            "-fi=${_LC_AWM_NAT}"
            "-fi=${_LC_PRE_NAT}"
            "-wcd=201"
            "-wcd=202"
        )
    elseif(MSVC)
        target_compile_options(fbsd_libcompat PRIVATE "/FI${_LC_AWM_CFG}" "/FI${_LC_PREINC}" "/wd4005" "/wd4244" "/wd4267" "/wd4996")
    else()
        target_compile_options(fbsd_libcompat PRIVATE
            "SHELL:-include ${_LC_AWM_CFG}"
            "SHELL:-include ${_LC_PREINC}"
            "-Wno-unused-parameter"
            "-Wno-sign-compare"
        )
    endif()
endif()
target_link_libraries(fbsd_libcompat PUBLIC auto-win-msvc)

include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/FreeBsdInternalLibs.cmake")

# -----------------------------------------------------------------------------
# 6. Per-Binary Standalone Executables (Generated per_binary/<prog>/CMakeLists.txt)
# -----------------------------------------------------------------------------
if(FREEBSD_BUILD_INDIVIDUAL AND EXISTS "${FREEBSD_GEN_DIR}/per_binary_subdirs.cmake")
    if(NOT DEFINED FREEBSD_ENABLED_BINARIES)
        if(FREEBSD_TARGET_DOS OR NOT (FREEBSD_HOST_YACC AND FREEBSD_HOST_LEX))
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
if(FREEBSD_BUILD_MULTICALL)
    set(FREEBSD_ACTIVE_SOURCES ${FREEBSD_MULTICALL_SOURCES})

    if(COMMAND auto_win_msvc_transform_sources AND (MSVC OR FREEBSD_TARGET_DOS))
        auto_win_msvc_transform_sources(
            OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/transformed_freebsd"
            OUTPUT_VAR FREEBSD_TRANSFORMED_SOURCES
            SOURCES ${FREEBSD_ACTIVE_SOURCES}
        )
        set(FREEBSD_ACTIVE_SOURCES ${FREEBSD_TRANSFORMED_SOURCES})
    endif()

    add_executable(freebsd-usr-bin ${FREEBSD_ACTIVE_SOURCES})
    set_target_properties(freebsd-usr-bin PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    )

    target_include_directories(freebsd-usr-bin BEFORE PRIVATE
        "${FREEBSD_GEN_INC}"
        "${AWM_POSIX_INCLUDES}"
        "${auto_win_msvc_SOURCE_DIR}/include"
    )

    if(FREEBSD_TARGET_DOS)
        target_compile_definitions(freebsd-usr-bin PRIVATE
            __DOS__=1
            _GNU_SOURCE=1
            WITHOUT_CAPSICUM=1
            WITHOUT_CASPER=1
        )
        set(_awm_cfg "${AWM_POSIX_INCLUDES}/auto-win-msvc-configure.h")
        set(_fbsd_cfg "${FREEBSD_GEN_INC}/freebsd_compat_preinclude.h")
        file(TO_NATIVE_PATH "${_awm_cfg}" _awm_cfg_native)
        file(TO_NATIVE_PATH "${_fbsd_cfg}" _fbsd_cfg_native)
        target_compile_options(freebsd-usr-bin PRIVATE
            "$<$<COMPILE_LANGUAGE:C>:-zastd=c99>"
            "$<$<COMPILE_LANGUAGE:C>:-ze>"
            "$<$<COMPILE_LANGUAGE:C>:-aa>"
            "-fi=${_awm_cfg_native}"
            "-fi=${_fbsd_cfg_native}"
            "-wcd=201"
            "-wcd=202"
        )
        target_link_options(freebsd-usr-bin PRIVATE "option" "stack=524288")
    elseif(MSVC)
        target_compile_definitions(freebsd-usr-bin PRIVATE
            _CRT_SECURE_NO_WARNINGS
            _CRT_NONSTDC_NO_DEPRECATE
            _CRT_NONSTDC_NO_WARNINGS
            _CRT_STDIO_ISO_WIDE_SPECIFIERS=1
            WIN32_LEAN_AND_MEAN
            NOMINMAX
            _GNU_SOURCE=1
            WITHOUT_CAPSICUM=1
            WITHOUT_CASPER=1
        )
        target_compile_options(freebsd-usr-bin PRIVATE
            "/FI${AWM_POSIX_INCLUDES}/auto-win-msvc-configure.h"
            "/FI${FREEBSD_GEN_INC}/freebsd_compat_preinclude.h"
            "/wd4005" "/wd4018" "/wd4100" "/wd4127" "/wd4146"
            "/wd4244" "/wd4267" "/wd4389" "/wd4706" "/wd4996"
        )
        target_link_options(freebsd-usr-bin PRIVATE "/STACK:8388608")
    else()
        target_compile_definitions(freebsd-usr-bin PRIVATE
            _GNU_SOURCE=1
            WITHOUT_CAPSICUM=1
            WITHOUT_CASPER=1
        )
        target_compile_options(freebsd-usr-bin PRIVATE
            "SHELL:-include ${AWM_POSIX_INCLUDES}/auto-win-msvc-configure.h"
            "SHELL:-include ${FREEBSD_GEN_INC}/freebsd_compat_preinclude.h"
            "-Wno-unused-parameter"
            "-Wno-sign-compare"
        )
    endif()

    target_link_libraries(freebsd-usr-bin PRIVATE
        auto-win-msvc
        fbsd_libutil
        fbsd_libxo
        $<$<BOOL:${WIN32}>:bcrypt ws2_32>
    )
    if(UNIX)
        target_link_libraries(freebsd-usr-bin PRIVATE m)
    endif()

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
if(BUILD_TESTING AND NOT FREEBSD_TARGET_DOS)
    enable_testing()

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

        if(NOT _test_runner_prefix)
            find_package(Python3 REQUIRED COMPONENTS Interpreter)
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
