#[=======================================================================[.rst:
GenerateFreeBsdHeaders
----------------------

Deterministic CMake build-time generator for out-of-tree FreeBSD ``usr.bin``
compatibility headers, ``libxo``/``fgetwln`` C shims, multicall applet source
wrappers, unified ``freebsd-usr-bin`` dispatcher, and CMake source/target
manifests.

This module works alongside the POSIX/BSD/FreeBSD polyfill modules in
``../auto-win-msvc`` (``bsd-capsicum``, ``bsd-libutil``, ``bsd-fts``,
``bsd-vis``, ``bsd-stringlist``, ``bsd-sbuf``, ``bsd-db``, ``bsd-utmpx``,
``bsd-kvm-procstat``, ``bsd-rpc``, ``bsd-dev-headers``, ``bsd-sys-cdefs``,
``bsd-sys-param``, ``bsd-stdlib``, ``bsd-string``, ``linux-err``) without
creating or modifying any ``.c`` or ``.h`` file inside ``freebsd-src`` or the
repository source tree.

Module Variables
^^^^^^^^^^^^^^^^

``FREEBSD_NATIVE_DIRECT_APPLETS``
  List of single-file FreeBSD ``usr.bin`` utilities compiled directly from
  ``usr.bin/<applet>/<applet>.c`` after renaming ``main`` and file-static
  identifiers for multicall linkage.

``FREEBSD_STATIC_IDS_TO_RENAME``
  List of common file-static function and option-flag identifiers prefixed with
  ``fbsd_<applet_id>_`` during multicall source wrapping.

Functions and Macros
^^^^^^^^^^^^^^^^^^^^

``freebsd_expand_makefile_vars(<text> <env_prefix> <out_var>)``
  Expands ``bmake`` ``${VAR}`` expressions and ``:H``, ``:H:H``, ``:T``,
  ``:tl``, ``:tu``, and ``:U<fallback>`` modifiers.

``_freebsd_parse_makefile_impl(<mk_path> <curdir> <env_prefix> <visited_var>)``
  Recursively parses a FreeBSD ``Makefile`` and quoted ``.include`` directives
  to populate ``PROG``, ``PROG_CXX``, ``PROGS``, and ``LINKS`` variables.

``freebsd_emit_compat_headers(INC_DIR <dir> [FREEBSD_SRC_DIR <dir>] [OUT_HEADERS_VAR <var>])``
  Generates ``osreldate.h``, ``pathnames.h``, ``libxo/xo.h``, and
  ``freebsd_compat_preinclude.h`` under ``<dir>``.

``freebsd_emit_libcompat_c(SRC_DIR <dir> [OUT_FILE_VAR <var>])``
  Generates ``freebsd_libcompat.c`` under ``<dir>`` providing ``fbsd_fgetwln``,
  ``fbsd_wcwidth``, and text-mode ``libxo`` shims.

``freebsd_transform_applet_source(<input_var> <applet_id> <output_var>)``
  Transforms raw C source code stored in ``<input_var>`` into a multicall-safe
  translation unit defining ``fbsd_<applet_id>_main(int argc, char *argv[])``.

``freebsd_emit_multicall_applets_and_dispatcher(FREEBSD_SRC_DIR <dir> OUT_DIR <dir>)``
  Audits all ``usr.bin`` entries in ``<dir>`` and generates ``applets/*.c``,
  ``src/freebsd_multicall_main.c``, ``freebsd_usr_bin_targets.cmake``, and
  ``enabled_sources.cmake``.

``freebsd_generate_all(FREEBSD_SRC_DIR <dir> OUT_DIR <dir>)``
  Executes the complete FreeBSD ``usr.bin`` header, shim, manifest, and
  multicall C code generation pipeline.

Script Mode Variables
^^^^^^^^^^^^^^^^^^^^^

When executed via ``cmake [-DFREEBSD_SRC_DIR=...] [-DOUT_DIR=...] -P cmake/GenerateFreeBsdHeaders.cmake``:

``FREEBSD_SRC_DIR``
  Path to upstream ``freebsd-src`` (defaults to ``../freebsd-src`` relative to
  the repository root).

``OUT_DIR``
  Destination directory for generated files (defaults to
  ``build/freebsd_generated`` relative to the current working directory).
#]=======================================================================]

string(ASCII 92 _FBSD_BS)
string(ASCII 36 _FBSD_DL)
string(ASCII 34 _FBSD_DQ)
string(ASCII 13 _FBSD_CR)
string(ASCII 10 _FBSD_NL)
string(ASCII 9 _FBSD_TAB)
string(ASCII 31 _FBSD_US)

set(FREEBSD_NATIVE_DIRECT_APPLETS
    apply
    asa
    banner
    basename
    caesar
    col
    colrm
    column
    comm
    csplit
    cut
    dirname
    expand
    false
    file2c
    fmt
    fold
    from
    getopt
    head
    join
    jot
    lam
    logname
    look
    mesg
    mktemp
    morse
    nice
    nl
    nohup
    number
    paste
    pathchk
    pom
    printenv
    printf
    rev
    seq
    soelim
    split
    tee
    touch
    true
    truncate
    tsort
    tty
    uname
    unexpand
    unifdef
    uniq
    wc
    what
    which
    xstr
    yes
)

set(FREEBSD_STATIC_IDS_TO_RENAME
    usage
    cleanup
    process
    output
    filter
    err_exit
    warn_msg
    do_file
    print_line
    get_line
    next_line
    alloc_buf
    xmalloc
    xrealloc
    xstrdup
    cflag
    dflag
    eflag
    fflag
    iflag
    lflag
    mflag
    nflag
    oflag
    pflag
    qflag
    rflag
    sflag
    tflag
    uflag
    vflag
    wflag
    xflag
)

# -----------------------------------------------------------------------------
# freebsd_expand_makefile_vars(<text> <env_prefix> <out_var>)
#
# Expand FreeBSD bmake ${VAR} references and simple modifiers (:H, :H:H, :T,
# :tl, :tu, :U<fallback>) using caller-scoped variables prefixed with
# <env_prefix>.
#
# Arguments:
#   TEXT       - Input Makefile expression string to expand.
#   ENV_PREFIX - Variable prefix holding defined Makefile variables in caller.
#   OUT_VAR    - Name of caller variable receiving the expanded string.
# -----------------------------------------------------------------------------
function(freebsd_expand_makefile_vars TEXT ENV_PREFIX OUT_VAR)
    set(_cur "${TEXT}")
    set(_ref_match_re "${_FBSD_BS}${_FBSD_DL}${_FBSD_BS}{[A-Za-z0-9_.]+(:[^}]*)?${_FBSD_BS}}")
    set(_ref_split_re "^${_FBSD_BS}${_FBSD_DL}${_FBSD_BS}{([A-Za-z0-9_.]+)(:([^}]*))?${_FBSD_BS}}$")
    set(_ref_split_rep "${_FBSD_BS}1;${_FBSD_BS}2;${_FBSD_BS}3")
    set(_guard 0)
    while(_guard LESS 16)
        math(EXPR _guard "${_guard} + 1")
        set(_changed FALSE)
        string(REGEX MATCHALL "${_ref_match_re}" _refs "${_cur}")
        foreach(_ref IN LISTS _refs)
            string(REGEX REPLACE "${_ref_split_re}" "${_ref_split_rep}" _parts "${_ref}")
            list(GET _parts 0 _vname)
            list(GET _parts 1 _has_mod)
            list(GET _parts 2 _mod)
            if(DEFINED "${ENV_PREFIX}${_vname}")
                set(_val "${${ENV_PREFIX}${_vname}}")
                if(_mod STREQUAL "H")
                    get_filename_component(_val "${_val}" DIRECTORY)
                elseif(_mod STREQUAL "H:H")
                    get_filename_component(_val "${_val}" DIRECTORY)
                    get_filename_component(_val "${_val}" DIRECTORY)
                elseif(_mod STREQUAL "T")
                    get_filename_component(_val "${_val}" NAME)
                elseif(_mod STREQUAL "tl")
                    string(TOLOWER "${_val}" _val)
                elseif(_mod STREQUAL "tu")
                    string(TOUPPER "${_val}" _val)
                endif()
                string(REPLACE "${_ref}" "${_val}" _cur "${_cur}")
                set(_changed TRUE)
            elseif(_has_mod MATCHES "^:U")
                string(SUBSTRING "${_mod}" 1 -1 _uval)
                string(REPLACE "${_ref}" "${_uval}" _cur "${_cur}")
                set(_changed TRUE)
            endif()
        endforeach()
        if(NOT _changed)
            break()
        endif()
    endwhile()
    set(${OUT_VAR} "${_cur}" PARENT_SCOPE)
endfunction()

# -----------------------------------------------------------------------------
# _freebsd_parse_makefile_impl(<mk_path> <curdir> <env_prefix> <visited_var>)
#
# Recursively parse a FreeBSD Makefile and its quoted .include files into
# variables prefixed with <env_prefix>.
#
# Arguments:
#   MK_PATH     - Path to the Makefile to parse.
#   CURDIR      - Resolved utility directory (${.CURDIR}).
#   ENV_PREFIX  - Variable prefix for storing parsed Makefile assignments.
#   VISITED_VAR - List variable tracking already-visited real Makefile paths.
# -----------------------------------------------------------------------------
macro(_freebsd_parse_makefile_impl MK_PATH CURDIR ENV_PREFIX VISITED_VAR)
    get_filename_component(_mk_abs "${MK_PATH}" REALPATH)
    list(FIND ${VISITED_VAR} "${_mk_abs}" _vis_idx)
    if(_vis_idx EQUAL -1 AND EXISTS "${_mk_abs}" AND NOT IS_DIRECTORY "${_mk_abs}")
        list(APPEND ${VISITED_VAR} "${_mk_abs}")
        get_filename_component(_mk_dir "${_mk_abs}" DIRECTORY)
        set("${ENV_PREFIX}.PARSEDIR" "${_mk_dir}")

        file(READ "${_mk_abs}" _raw_mk)
        string(REPLACE ";" "${_FBSD_US}" _raw_mk "${_raw_mk}")
        string(REGEX REPLACE "${_FBSD_BS}${_FBSD_BS}${_FBSD_CR}?${_FBSD_NL}[ ${_FBSD_TAB}]*" " " _joined_mk "${_raw_mk}")
        string(REPLACE "${_FBSD_CR}${_FBSD_NL}" "${_FBSD_NL}" _joined_mk "${_joined_mk}")
        string(REPLACE "${_FBSD_NL}" ";" _mk_lines "${_joined_mk}")

        set(_inc_re "^${_FBSD_BS}.[ ${_FBSD_TAB}]*-?s?include[ ${_FBSD_TAB}]+${_FBSD_DQ}([^${_FBSD_DQ}]+)${_FBSD_DQ}")
        set(_assign_re "^([A-Za-z0-9_.]+)[ ${_FBSD_TAB}]*([?:+!]?=)[ ${_FBSD_TAB}]*(.*)$")

        foreach(_rline IN LISTS _mk_lines)
            string(REPLACE "${_FBSD_US}" ";" _line "${_rline}")
            string(STRIP "${_line}" _line)
            if(NOT "${_line}" STREQUAL "" AND NOT "${_line}" MATCHES "^#")
                if("${_line}" MATCHES "${_inc_re}")
                    freebsd_expand_makefile_vars("${CMAKE_MATCH_1}" "${ENV_PREFIX}" _inc_rel)
                    if(IS_ABSOLUTE "${_inc_rel}")
                        set(_inc_path "${_inc_rel}")
                    elseif(EXISTS "${_mk_dir}/${_inc_rel}")
                        set(_inc_path "${_mk_dir}/${_inc_rel}")
                    else()
                        set(_inc_path "${CURDIR}/${_inc_rel}")
                    endif()
                    _freebsd_parse_makefile_impl("${_inc_path}" "${CURDIR}" "${ENV_PREFIX}" ${VISITED_VAR})
                    get_filename_component(_mk_restore "${MK_PATH}" REALPATH)
                    get_filename_component(_mk_dir "${_mk_restore}" DIRECTORY)
                    set("${ENV_PREFIX}.PARSEDIR" "${_mk_dir}")
                elseif("${_line}" MATCHES "${_assign_re}")
                    set(_assign_key "${CMAKE_MATCH_1}")
                    set(_assign_op "${CMAKE_MATCH_2}")
                    string(STRIP "${CMAKE_MATCH_3}" _assign_raw)
                    if(NOT _assign_op STREQUAL "!=")
                        freebsd_expand_makefile_vars("${_assign_raw}" "${ENV_PREFIX}" _assign_val)
                        if(DEFINED "${ENV_PREFIX}${_assign_key}" AND _assign_op STREQUAL "+=")
                            string(STRIP "${${ENV_PREFIX}${_assign_key}} ${_assign_val}" "${ENV_PREFIX}${_assign_key}")
                        elseif(_assign_op STREQUAL "?=" AND DEFINED "${ENV_PREFIX}${_assign_key}")
                            string(STRIP "${${ENV_PREFIX}${_assign_key}}" _existing_trimmed)
                            if("${_existing_trimmed}" STREQUAL "")
                                set("${ENV_PREFIX}${_assign_key}" "${_assign_val}")
                            endif()
                        else()
                            set("${ENV_PREFIX}${_assign_key}" "${_assign_val}")
                        endif()
                    endif()
                endif()
            endif()
        endforeach()
    endif()
endmacro()

# -----------------------------------------------------------------------------
# freebsd_emit_compat_headers(
#   INC_DIR <dir>
#   [FREEBSD_SRC_DIR <dir>]
#   [OUT_HEADERS_VAR <var>]
# )
#
# Generate osreldate.h, pathnames.h, libxo/xo.h, and
# freebsd_compat_preinclude.h inside <dir>.
#
# Arguments:
#   INC_DIR         - Output include directory inside freebsd_generated.
#   FREEBSD_SRC_DIR - Optional path to upstream freebsd-src.
#   OUT_HEADERS_VAR - Optional caller variable receiving generated file paths.
# -----------------------------------------------------------------------------
function(freebsd_emit_compat_headers)
    set(_options "")
    set(_one_value_args INC_DIR FREEBSD_SRC_DIR OUT_HEADERS_VAR)
    set(_multi_value_args "")
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    if(NOT ARG_INC_DIR)
        message(FATAL_ERROR "freebsd_emit_compat_headers: INC_DIR is required")
    endif()

    file(MAKE_DIRECTORY "${ARG_INC_DIR}/libxo")

    set(_fbsd_rlim_nlimits 17)
    set(_fbsd_rlim_vmm_def "#ifndef RLIMIT_VMM\n#define RLIMIT_VMM 16\n#endif\n")
    set(_fbsd_rlim_ident_tail "\"pipebuf\", \"vmm\"")
    if(ARG_FREEBSD_SRC_DIR AND EXISTS "${ARG_FREEBSD_SRC_DIR}/sys/sys/resource.h")
        file(READ "${ARG_FREEBSD_SRC_DIR}/sys/sys/resource.h" _fbsd_res_h_txt)
        if(NOT "${_fbsd_res_h_txt}" MATCHES "RLIMIT_VMM")
            set(_fbsd_rlim_nlimits 16)
            set(_fbsd_rlim_vmm_def "")
            set(_fbsd_rlim_ident_tail "\"pipebuf\"")
        endif()
    endif()

    set(_osreldate_h [=[#ifndef _OSRELDATE_H_
#define _OSRELDATE_H_
#undef __FreeBSD_version
#define __FreeBSD_version 1500000
#endif
]=])
    set(_osreldate_path "${ARG_INC_DIR}/osreldate.h")
    file(WRITE "${_osreldate_path}" "${_osreldate_h}")

    set(_pathnames_h [=[#ifndef _FREEBSD_USR_BIN_PATHNAMES_H_
#define _FREEBSD_USR_BIN_PATHNAMES_H_
#include <paths.h>
#define _PATH_WORDS "/usr/share/dict/words"
#define _PATH_ECHO "/bin/echo"
#ifndef _PATH_LOCALBASE
#define _PATH_LOCALBASE "/usr/local"
#endif
#endif
]=])
    set(_pathnames_path "${ARG_INC_DIR}/pathnames.h")
    file(WRITE "${_pathnames_path}" "${_pathnames_h}")

    set(_libxo_path "${ARG_INC_DIR}/libxo/xo.h")
    if(ARG_FREEBSD_SRC_DIR AND EXISTS "${ARG_FREEBSD_SRC_DIR}/contrib/libxo/libxo/xo.h")
        file(READ "${ARG_FREEBSD_SRC_DIR}/contrib/libxo/libxo/xo.h" _xo_h_raw)
        string(REGEX REPLACE
            "va_list vap;\n([ \t]*)va_start\\(vap, fmt\\);\n([ \t]*)xo_ssize_t rc = "
            "va_list vap;\n\\1xo_ssize_t rc;\n\\1va_start(vap, fmt);\n\\2rc = "
            _xo_h_c89 "${_xo_h_raw}"
        )
        set(_xo_dll_hdr [=[#ifndef _FBSD_XO_DATA
#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)
#if defined(fbsd_libxo_EXPORTS)
#define _FBSD_XO_DATA extern __declspec(dllexport)
#elif !defined(FBSD_XO_STATIC)
#define _FBSD_XO_DATA extern __declspec(dllimport)
#else
#define _FBSD_XO_DATA extern
#endif
#else
#define _FBSD_XO_DATA extern
#endif
#endif
]=])
        string(REPLACE
            "extern const char xo_version"
            "_FBSD_XO_DATA const char xo_version"
            _xo_h_c89 "${_xo_dll_hdr}${_xo_h_c89}"
        )
        file(MAKE_DIRECTORY "${ARG_INC_DIR}/libxo")
        file(WRITE "${_libxo_path}" "${_xo_h_c89}")
        if(EXISTS "${ARG_FREEBSD_SRC_DIR}/contrib/libxo/libxo/xo_encoder.h")
            file(READ "${ARG_FREEBSD_SRC_DIR}/contrib/libxo/libxo/xo_encoder.h" _xo_enc_raw)
            set(_xo_enc_hdr "#ifndef XO_ENCODERDIR\n#define XO_ENCODERDIR \"/usr/lib/libxo/encoder\"\n#endif\n")
            file(WRITE "${ARG_INC_DIR}/libxo/xo_encoder.h" "${_xo_enc_hdr}${_xo_enc_raw}")
        endif()
    else()
        set(_libxo_h [=[#ifndef _LIBXO_XO_H_
#define _LIBXO_XO_H_
#define FBSD_LIBXO_MINIMAL_SHIM 1
#include <stdarg.h>
#include <stdio.h>
#include <sys/types.h>
#define XO_STYLE_TEXT 0
#define XO_STYLE_XML 1
#define XO_STYLE_JSON 2
#define XO_STYLE_HTML 3
#define XOF_WARN 0x01
#define XOF_UNITS 0x02
#define XOF_FLUSH 0x04
typedef struct xo_handle xo_handle_t;
xo_handle_t *xo_create_to_file(FILE *fp, unsigned style, unsigned flags);
int xo_parse_args(int argc, char **argv);
int xo_set_program(const char *name);
int xo_set_version(const char *version);
int xo_set_flags(void *xop, unsigned flags);
int xo_get_style(void *xop);
int xo_open_container(const char *name);
int xo_close_container(const char *name);
int xo_open_list(const char *name);
int xo_close_list(const char *name);
int xo_open_instance(const char *name);
int xo_close_instance(const char *name);
int xo_emit(const char *fmt, ...);
int xo_emit_h(xo_handle_t *xop, const char *fmt, ...);
int xo_attr(const char *name, const char *fmt, ...);
void xo_error(const char *fmt, ...);
void xo_flush(void);
void xo_flush_h(xo_handle_t *xop);
int xo_finish(void);
int xo_finish_h(xo_handle_t *xop);
void xo_finish_atexit(void);
void xo_err(int eval, const char *fmt, ...);
void xo_errx(int eval, const char *fmt, ...);
void xo_warn(const char *fmt, ...);
void xo_warnx(const char *fmt, ...);
void xo_warnc(int code, const char *fmt, ...);
#endif
]=])
        file(WRITE "${_libxo_path}" "${_libxo_h}")
    endif()

    set(_preinclude_h [=[#ifndef FREEBSD_COMPAT_PREINCLUDE_H_
#define FREEBSD_COMPAT_PREINCLUDE_H_
#ifndef _DARWIN_C_SOURCE
#define _DARWIN_C_SOURCE 1
#endif
#ifndef __APPLE_USE_RFC_3542
#define __APPLE_USE_RFC_3542 1
#endif
#include <sys/cdefs.h>
#include <sys/types.h>
#include <sys/param.h>
#if defined(__APPLE__) && defined(__GNUC__) && !defined(__clang__)
#undef __DECONST
#define __DECONST(type, var) ((type)(uintptr_t)(const void *)(var))
#undef __DEVOLATILE
#define __DEVOLATILE(type, var) ((type)(uintptr_t)(volatile void *)(var))
#undef __DEQUALIFY
#define __DEQUALIFY(type, var) ((type)(uintptr_t)(const volatile void *)(var))
#endif
#include <sys/capsicum.h>
#include <libutil.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#undef CAP_MMAP
#define CAP_MMAP 0x10ULL
#undef CAP_MMAP_X
#define CAP_MMAP_X 0x20ULL
#undef CAP_CREATE
#define CAP_CREATE 0x40ULL
#undef CAP_FEXECVE
#define CAP_FEXECVE 0x80ULL
#undef CAP_FSYNC
#define CAP_FSYNC 0x100ULL
#undef CAP_FTRUNCATE
#define CAP_FTRUNCATE 0x200ULL
#undef CAP_LOOKUP
#define CAP_LOOKUP 0x400ULL
#undef CAP_FCHDIR
#define CAP_FCHDIR 0x800ULL
#undef CAP_FCHFLAGS
#define CAP_FCHFLAGS 0x1000ULL
#undef CAP_FCHMOD
#define CAP_FCHMOD 0x2000ULL
#undef CAP_FCHOWN
#define CAP_FCHOWN 0x4000ULL
#undef CAP_FCNTL
#define CAP_FCNTL 0x8000ULL
#undef CAP_FLOCK
#define CAP_FLOCK 0x10000ULL
#undef CAP_FPATHCONF
#define CAP_FPATHCONF 0x20000ULL
#undef CAP_FSCK
#define CAP_FSCK 0x40000ULL
#undef CAP_FSTAT
#define CAP_FSTAT 0x80000ULL
#undef CAP_FSTATFS
#define CAP_FSTATFS 0x100000ULL
#undef CAP_FUTIMES
#define CAP_FUTIMES 0x200000ULL
#undef CAP_IOCTL
#define CAP_IOCTL 0x400000ULL
#undef CAP_TTYHOOK
#define CAP_TTYHOOK 0x800000ULL
#define expand_number(b, n) (expand_number)((b), (uint64_t *)(void *)(n))
#if defined(__has_include)
#if !defined(FBSD_SKIP_PREINCLUDE_ENDIAN) && __has_include(<sys/endian.h>)
#include <sys/endian.h>
#endif
#if __has_include(<bsd/stdlib.h>)
#include <bsd/stdlib.h>
#endif
#if __has_include(<bsd/string.h>)
#include <bsd/string.h>
#endif
#if defined(_WIN32) && __has_include(<posix-stdio.h>)
#include <posix-stdio.h>
#endif
#if defined(_WIN32) && __has_include(<posix-time.h>)
#include <posix-time.h>
#endif
#elif defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
#if !defined(FBSD_SKIP_PREINCLUDE_ENDIAN)
#include <sys/endian.h>
#endif
#include <bsd/stdlib.h>
#include <bsd/string.h>
#endif
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#ifndef __arraycount
#define __arraycount(__x) (sizeof(__x) / sizeof((__x)[0]))
#endif
#ifndef __UNCONST
#define __UNCONST(a) ((void *)(uintptr_t)(const void *)(a))
#endif
#ifndef ALIGNBYTES
#define ALIGNBYTES (sizeof(uintptr_t) - 1U)
#endif
#ifndef ALIGN
#define ALIGN(p) (((uintptr_t)(p) + ALIGNBYTES) & ~ALIGNBYTES)
#endif
#if (defined(_MSC_VER) || defined(__WATCOMC__)) && !defined(__clang__)
#ifndef __builtin_expect
#define __builtin_expect(x, v) (x)
#endif
static __inline int fbsd_ctzll_compat(unsigned long long v) {
    int n = 0;
    if (v == 0ULL) return 64;
    while ((v & 1ULL) == 0ULL) { v >>= 1; n++; }
    return n;
}
#ifndef __builtin_ctzll
#define __builtin_ctzll fbsd_ctzll_compat
#endif
#endif
#ifndef CLOCK_REALTIME_FAST
#ifdef CLOCK_REALTIME
#define CLOCK_REALTIME_FAST CLOCK_REALTIME
#else
#define CLOCK_REALTIME_FAST 0
#endif
#endif
#ifndef CLOCK_MONOTONIC_FAST
#ifdef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC_FAST CLOCK_MONOTONIC
#else
#define CLOCK_MONOTONIC_FAST 1
#endif
#endif
#ifndef CLOCK_UPTIME
#define CLOCK_UPTIME CLOCK_MONOTONIC_FAST
#endif
#ifndef CLOCK_UPTIME_FAST
#define CLOCK_UPTIME_FAST CLOCK_MONOTONIC_FAST
#endif
#ifndef CLOCK_SECOND
#define CLOCK_SECOND CLOCK_REALTIME_FAST
#endif
#ifndef EAUTH
#define EAUTH 80
#endif
#ifndef ENEEDAUTH
#define ENEEDAUTH 81
#endif
#ifndef EFTYPE
#define EFTYPE 79
#endif
#ifndef EDOOFUS
#define EDOOFUS 88
#endif
#ifndef IPPORT_MAX
#define IPPORT_MAX 65535
#endif
#ifndef INFTIM
#define INFTIM (-1)
#endif
#ifndef SCM_RIGHTS
#define SCM_RIGHTS 0x01
#endif
#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
#ifndef WIFEXITED
#define WIFEXITED(s) (((s) & 0x7f) == 0)
#endif
#ifndef WEXITSTATUS
#define WEXITSTATUS(s) (((s) >> 8) & 0xff)
#endif
#ifndef WIFSIGNALED
#define WIFSIGNALED(s) (((s) & 0x7f) != 0 && ((s) & 0x7f) != 0x7f)
#endif
#ifndef WTERMSIG
#define WTERMSIG(s) ((s) & 0x7f)
#endif
#endif
#if defined(__DOS__) || defined(__WATCOMC__)
#include <strings.h>
#endif
#if !defined(__WATCOMC__)
#ifndef bzero
#define bzero(p, n) memset((p), 0, (n))
#endif
#ifndef bcmp
#define bcmp(a, b, n) memcmp((a), (b), (n))
#endif
#ifndef bcopy
#define bcopy(s, d, n) memmove((d), (s), (n))
#endif
#endif
#ifndef LINE_MAX
#define LINE_MAX 2048
#endif
#ifndef SIZE_T_MAX
#define SIZE_T_MAX SIZE_MAX
#endif
#ifndef OFF_MAX
#define OFF_MAX INT64_MAX
#endif
#ifndef OFF_MIN
#define OFF_MIN INT64_MIN
#endif
#ifndef DEFFILEMODE
#define DEFFILEMODE 0666
#endif
#ifndef ALLPERMS
#define ALLPERMS 07777
#endif
#ifndef ACCESSPERMS
#define ACCESSPERMS 0777
#endif
#ifndef L_SET
#define L_SET 0
#endif
#ifndef L_INCR
#define L_INCR 1
#endif
#ifndef L_XTND
#define L_XTND 2
#endif
#ifndef _SC_ARG_MAX
#define _SC_ARG_MAX 1
#endif
#ifndef _SC_LINE_MAX
#define _SC_LINE_MAX 15
#endif
#ifndef _SC_NPROCESSORS_ONLN
#define _SC_NPROCESSORS_ONLN 58
#endif
#ifndef TIOCGPGRP
#define TIOCGPGRP 0x40047477
#endif
#ifndef TCSASOFT
#define TCSASOFT 0
#endif
#ifndef FIODTYPE
#define FIODTYPE 0x4004667a
#endif
#if defined(_WIN32)
#ifdef ERROR
#undef ERROR
#endif
#ifdef min
#undef min
#endif
#ifdef max
#undef max
#endif
#ifdef SearchPath
#undef SearchPath
#endif
#ifdef ANSI_NULL
#undef ANSI_NULL
#endif
#ifdef SP_ERROR
#undef SP_ERROR
#endif
#ifdef FBSD_UNDEF_WIN32_DELETE
#ifdef DELETE
#undef DELETE
#endif
#ifdef INFINITE
#undef INFINITE
#endif
#endif
#ifdef FBSD_SED_BUILD
#undef GROUP
#define GROUP fbsd_sed_GROUP
#endif
#ifdef FBSD_BSDDIALOG_BUILD
#undef BOOL
#define BOOL fbsd_bsddialog_BOOL
#undef CHAR
#define CHAR fbsd_bsddialog_CHAR
#undef INT
#define INT fbsd_bsddialog_INT
#undef UINT
#define UINT fbsd_bsddialog_UINT
#undef HFILE
#define HFILE fbsd_bsddialog_HFILE
#ifdef HELP
#undef HELP
#endif
#ifdef TEXT
#undef TEXT
#endif
#ifdef IGNORE
#undef IGNORE
#endif
#endif
#ifdef FBSD_TOP_BUILD
#undef itoa
#define itoa fbsd_top_itoa
#endif
#ifdef FBSD_FTP_BUILD
#ifdef OUT
#undef OUT
#endif
#ifdef IN
#undef IN
#endif
#include <sys/sysctl.h>
#endif
#ifdef FBSD_BSDCPIO_BUILD
#if defined(_WIN32) && !defined(__CYGWIN__)
struct __timeval { int64_t tv_sec; long tv_usec; };
static __inline int fbsd_cpio_utimes(const char *n, struct __timeval t[2]) { (void)n; (void)t; return 0; }
#undef utimes
#define utimes fbsd_cpio_utimes
#undef lutimes
#define lutimes fbsd_cpio_utimes
#undef futimes
#define futimes(fd, t) 0
#endif
#endif
#ifdef FBSD_W_BUILD
#undef CHAR
#define CHAR fbsd_w_CHAR
#undef UCHAR
#define UCHAR fbsd_w_UCHAR
#undef SHORT
#define SHORT fbsd_w_SHORT
#undef USHORT
#define USHORT fbsd_w_USHORT
#undef INT
#define INT fbsd_w_INT
#undef UINT
#define UINT fbsd_w_UINT
#undef LONG
#define LONG fbsd_w_LONG
#undef ULONG
#define ULONG fbsd_w_ULONG
#endif
#ifdef FBSD_LIBMAGIC_BUILD
#ifdef WIN32
#undef WIN32
#endif
#endif
#ifdef FBSD_COL_BUILD
#undef CHAR
#define CHAR fbsd_col_CHAR
#endif
#ifdef FBSD_JOIN_BUILD
#undef INPUT
#define INPUT fbsd_join_INPUT
#endif
#endif
#ifndef EHOSTDOWN
#define EHOSTDOWN 64
#endif
#ifndef SO_NOSIGPIPE
#define SO_NOSIGPIPE 0x0800
#endif
#ifndef TCP_NOPUSH
#define TCP_NOPUSH 4
#endif
#ifndef IP_PORTRANGE
#define IP_PORTRANGE 19
#define IP_PORTRANGE_DEFAULT 0
#define IP_PORTRANGE_HIGH 1
#define IP_PORTRANGE_LOW 2
#endif
#ifndef SEEK_DATA
#define SEEK_DATA 3
#define SEEK_HOLE 4
#endif
#ifndef YESSTR
#define YESSTR 54
#define NOSTR 55
#endif
#ifndef SIGIOT
#define SIGIOT SIGABRT
#endif
#ifndef TCFLSH
#define TCFLSH 0x540B
#endif
#ifndef _PATH_SENDMAIL
#define _PATH_SENDMAIL "/usr/sbin/sendmail"
#endif
#ifndef CPUSTATES
#define CPUSTATES 5
#endif
#ifndef RES_INIT
#define RES_INIT 0x00000001UL
#endif
#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
static __inline void flockfile(FILE *f) { (void)f; }
static __inline void funlockfile(FILE *f) { (void)f; }
#endif
#ifndef _POSIX2_LINE_MAX
#define _POSIX2_LINE_MAX 2048
#endif
#ifndef REG_BASIC
#define REG_BASIC 0
#endif
#ifndef REG_STARTEND
#define REG_STARTEND 00004
#endif
#ifndef TIOCGWINSZ
#define TIOCGWINSZ 0x5413
#endif
#ifndef SIGINFO
#define SIGINFO 29
#endif
#if defined(__APPLE__)
#ifndef st_atim
#define st_atim st_atimespec
#endif
#ifndef st_mtim
#define st_mtim st_mtimespec
#endif
#ifndef st_ctim
#define st_ctim st_ctimespec
#endif
#endif
#ifndef SPACECTL_DEALLOC
#define SPACECTL_DEALLOC 1
struct spacectl_range { off_t r_offset; off_t r_len; };
static __inline int fspacectl(int fd, int cmd, const struct spacectl_range *rqsr,
    int flags, struct spacectl_range *rmsr) {
    (void)fd; (void)cmd; (void)flags;
    if (rmsr && rqsr) *rmsr = *rqsr;
    return 0;
}
#endif
#if !defined(__cplusplus) && !defined(FBSD_SKIP_PREINCLUDE_STDBOOL) && (!defined(_MSC_VER) || _MSC_VER >= 1800)
#include <stdbool.h>
#endif
#include <stdarg.h>
#ifndef __va_list
#define __va_list va_list
#endif
#ifndef _ERRNO_T_DEFINED
#define _ERRNO_T_DEFINED
#if !defined(__APPLE__) && !defined(_MSC_VER)
typedef int errno_t;
#endif
#endif
#ifndef _PATH_DEFTAPE
#define _PATH_DEFTAPE "/dev/sa0"
#endif
#ifndef _PATH_CONSOLE
#define _PATH_CONSOLE "/dev/console"
#endif
#ifndef _POSIX2_RE_DUP_MAX
#define _POSIX2_RE_DUP_MAX 255
#endif
#if !defined(__FreeBSD__) && !defined(__APPLE__)
struct fbsd_rune_locale_compat { const char *__encoding; };
static const struct fbsd_rune_locale_compat fbsd_default_rune_locale = { "UTF-8" };
#ifndef _CurrentRuneLocale
#define _CurrentRuneLocale (&fbsd_default_rune_locale)
#endif
#endif
#ifndef MAP_NOCORE
#define MAP_NOCORE 0
#endif
#ifndef MAP_NOSYNC
#define MAP_NOSYNC 0
#endif
#ifndef SOCK_NONBLOCK
#define SOCK_NONBLOCK 0
#endif
#ifndef SOCK_CLOEXEC
#define SOCK_CLOEXEC 0
#endif
#ifndef SO_SETFIB
#define SO_SETFIB 0x1014
#endif
#ifndef SO_REUSEPORT_LB
#define SO_REUSEPORT_LB 0x10000
#endif
#ifndef IP_BINDANY
#define IP_BINDANY 24
#endif
#ifndef IPV6_BINDANY
#define IPV6_BINDANY 64
#endif
#ifndef TCP_MD5SIG
#define TCP_MD5SIG 0x10
#endif
#ifndef TCP_STATS
#define TCP_STATS 42
#endif
#ifndef IPTOS_LOWDELAY
#define IPTOS_LOWDELAY 0x10
#define IPTOS_THROUGHPUT 0x08
#define IPTOS_RELIABILITY 0x04
#endif
#ifndef IPTOS_PREC_NETCONTROL
#define IPTOS_PREC_NETCONTROL 0xe0
#define IPTOS_PREC_INTERNETCONTROL 0xc0
#define IPTOS_PREC_CRITIC_ECP 0xa0
#endif
#ifndef IPTOS_DSCP_CS0
#define IPTOS_DSCP_CS0 0x00
#define IPTOS_DSCP_CS1 0x20
#define IPTOS_DSCP_AF11 0x28
#define IPTOS_DSCP_AF12 0x30
#define IPTOS_DSCP_AF13 0x38
#define IPTOS_DSCP_CS2 0x40
#define IPTOS_DSCP_AF21 0x48
#define IPTOS_DSCP_AF22 0x50
#define IPTOS_DSCP_AF23 0x58
#define IPTOS_DSCP_CS3 0x60
#define IPTOS_DSCP_AF31 0x68
#define IPTOS_DSCP_AF32 0x70
#define IPTOS_DSCP_AF33 0x78
#define IPTOS_DSCP_CS4 0x80
#define IPTOS_DSCP_AF41 0x88
#define IPTOS_DSCP_AF42 0x90
#define IPTOS_DSCP_AF43 0x98
#define IPTOS_DSCP_CS5 0xa0
#define IPTOS_DSCP_VA 0xb0
#define IPTOS_DSCP_EF 0xb8
#define IPTOS_DSCP_CS6 0xc0
#define IPTOS_DSCP_CS7 0xe0
#endif
#ifndef TIOCGETA
#define TIOCGETA 0x402c7413UL
#endif
#ifndef FIODGNAME
#define FIODGNAME 0x80106678UL
#endif
#ifndef O_NAMEDATTR
#define O_NAMEDATTR 0
#endif
#ifndef _PC_NAMEDATTR_ENABLED
#define _PC_NAMEDATTR_ENABLED 65
#endif
#ifndef _PC_ACL_EXTENDED
#define _PC_ACL_EXTENDED 59
#endif
#ifndef _PC_ACL_NFS4
#define _PC_ACL_NFS4 64
#endif
#ifndef SF_SNAPSHOT
#define SF_SNAPSHOT 0x00200000
#endif
#ifndef INADDRSZ
#define INADDRSZ 4
#endif
#ifndef IN6ADDRSZ
#define IN6ADDRSZ 16
#endif
#ifndef sys_nsig
#ifdef NSIG
#define sys_nsig NSIG
#else
#define sys_nsig 32
#endif
#endif
#ifndef MAX_REC_NUMBER
#define MAX_REC_NUMBER 0xffffffffUL
#endif
#ifndef _PATH_LOCALBASE
#define _PATH_LOCALBASE "/usr/local"
#endif
#ifndef __assert_unreachable
#define __assert_unreachable() abort()
#endif
#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include)
#if __has_include(<nl_types.h>)
#include <nl_types.h>
#endif
#endif
#ifndef _NLS_MAGIC
#define _NLS_MAGIC 0xff88ff89
struct _nls_cat_hdr {
    int32_t __magic;
    int32_t __nsets;
    int32_t __mem;
    int32_t __msg_hdr_offset;
    int32_t __msg_txt_offset;
};
struct _nls_set_hdr {
    int32_t __setno;
    int32_t __nmsgs;
    int32_t __index;
};
struct _nls_msg_hdr {
    int32_t __msgno;
    int32_t __msglen;
    int32_t __offset;
};
#endif
#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include)
#if __has_include(<arpa/inet.h>)
#include <arpa/inet.h>
#endif
#if __has_include(<sys/ioctl.h>)
#include <sys/ioctl.h>
#endif
#if __has_include(<sys/mount.h>)
#include <sys/mount.h>
#endif
#if __has_include(<langinfo.h>)
#include <langinfo.h>
#endif
#if __has_include(<termios.h>)
#include <termios.h>
#endif
#if __has_include(<sys/random.h>)
#include <sys/random.h>
#endif
#if __has_include(<pty.h>)
#include <pty.h>
#endif
#if __has_include(<net/ethernet.h>)
#include <net/ethernet.h>
#endif
#endif
#ifndef SBS_CANTSENDMORE
#define SBS_CANTSENDMORE 0x0010
#endif
#ifndef SBS_CANTRCVMORE
#define SBS_CANTRCVMORE 0x0020
#endif
#if defined(__APPLE__) && !defined(st_birthtim)
#define st_birthtim st_birthtimespec
#elif !defined(__FreeBSD__) && !defined(st_birthtim)
#define st_birthtim st_mtim
#endif
#ifndef ALTMON_1
#ifdef MON_1
#define ALTMON_1 MON_1
#define ALTMON_2 MON_2
#define ALTMON_3 MON_3
#define ALTMON_4 MON_4
#define ALTMON_5 MON_5
#define ALTMON_6 MON_6
#define ALTMON_7 MON_7
#define ALTMON_8 MON_8
#define ALTMON_9 MON_9
#define ALTMON_10 MON_10
#define ALTMON_11 MON_11
#define ALTMON_12 MON_12
#endif
#endif
#if !defined(__FreeBSD__)
struct mac;
struct setcred {
    uid_t sc_uid;
    uid_t sc_ruid;
    uid_t sc_svuid;
    gid_t sc_gid;
    gid_t sc_rgid;
    gid_t sc_svgid;
    unsigned int sc_pad;
    unsigned int sc_supp_groups_nb;
    gid_t *sc_supp_groups;
    struct mac *sc_label;
};
#define SETCRED_INITIALIZER { (uid_t)-1, (uid_t)-1, (uid_t)-1, (gid_t)-1, (gid_t)-1, (gid_t)-1, 0, 0, NULL, NULL }
#define SETCREDF_UID (1u << 0)
#define SETCREDF_RUID (1u << 1)
#define SETCREDF_SVUID (1u << 2)
#define SETCREDF_GID (1u << 3)
#define SETCREDF_RGID (1u << 4)
#define SETCREDF_SVGID (1u << 5)
#define SETCREDF_SUPP_GROUPS (1u << 6)
#define SETCREDF_MAC_LABEL (1u << 7)
static __inline int setcred(unsigned int flags, const struct setcred *wcred, size_t size) {
    (void)flags; (void)wcred; (void)size;
    return -1;
}
static __inline int fhstat(const void *fhp, void *sb) {
    (void)fhp; (void)sb;
    return -1;
}
static __inline int posix_spawnattr_setprocdescp_np(void *a, int *fdp, int f) {
    (void)a; (void)fdp; (void)f; return 0;
}
static __inline char *fdevname_r(int fd, char *buf, int len) {
    (void)fd; if (buf && len > 0) buf[0] = 0; return NULL;
}
static __inline int getloginclass(char *buf, size_t len) {
    if (!buf || len < 8) return -1;
    memcpy(buf, "default", 8);
    return 0;
}
static __inline int setloginclass(const char *name) {
    (void)name;
    return 0;
}
static __inline int crypt_set_format(const char *fmt) {
    (void)fmt;
    return 1;
}
#if defined(__APPLE__)
int ether_hostton(const char *hostname, void *e);
int ether_ntohost(char *hostname, const void *e);
#elif defined(__linux__) || defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
static __inline int ether_hostton(const char *hostname, void *e) {
    (void)hostname; (void)e; return -1;
}
static __inline int ether_ntohost(char *hostname, const void *e) {
    (void)hostname; (void)e; return -1;
}
#endif
#endif
#if defined(__APPLE__)
static __inline void setproctitle(const char *fmt, ...) { (void)fmt; }
#endif
#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__) || defined(__linux__)
#if defined(__linux__) && __has_include(<resolv.h>)
#include <resolv.h>
#endif
int fbsd_b64_ntop(const unsigned char *src, size_t srclength, char *target, size_t targsize);
int fbsd_b64_pton(const char *src, unsigned char *target, size_t targsize);
#undef b64_ntop
#define b64_ntop fbsd_b64_ntop
#undef b64_pton
#define b64_pton fbsd_b64_pton
#endif
static __inline int getosreldate(void) { return 1500000; }
#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)
#undef O_BINARY
#define O_BINARY 0
#endif
#ifndef WINT_MAX
#define WINT_MAX 0x7fffffff
#endif
#ifndef D_MD_ORDER
#ifdef D_FMT
#define D_MD_ORDER D_FMT
#else
#define D_MD_ORDER 1
#endif
#endif
wchar_t *fbsd_fgetwln(FILE *stream, size_t *lenp);
#undef fgetwln
#define fgetwln fbsd_fgetwln
int fbsd_wcwidth(wchar_t c);
int fbsd_wcswidth(const wchar_t *pwcs, size_t n);
#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
#ifndef _IN_PORT_T_DEFINED
#define _IN_PORT_T_DEFINED
typedef uint16_t in_port_t;
#endif
#ifndef _IN_ADDR_T_DEFINED
#define _IN_ADDR_T_DEFINED
typedef uint32_t in_addr_t;
#endif
static __inline int getdtablesize(void) { return 1024; }
#if !defined(random)
static __inline long fbsd_random_shim(void) { return (long)rand(); }
static __inline void fbsd_srandom_shim(unsigned int s) { srand(s); }
#define random() fbsd_random_shim()
#define srandom(s) fbsd_srandom_shim(s)
#endif
#undef wcwidth
#define wcwidth fbsd_wcwidth
#undef wcswidth
#define wcswidth fbsd_wcswidth
static __inline int getentropy(void *buf, size_t len) {
    unsigned char *p = (unsigned char *)buf;
    size_t i;
    if (!p || len > 256) return -1;
    for (i = 0; i < len; ++i) p[i] = (unsigned char)((i * 131U) ^ 0x5aU);
    return 0;
}
#endif
#ifndef CPU_COUNT
#define CPU_COUNT(s) 1
#endif
#ifndef KERN_PROC_RLIMIT
#define KERN_PROC_RLIMIT 37
#endif
#ifndef RTLD_TRACE
#define RTLD_TRACE 0x200
#endif
#ifndef ELF_NOTE_FREEBSD
#define ELF_NOTE_FREEBSD "FreeBSD"
#endif
#ifndef NT_FREEBSD_ABI_TAG
#define NT_FREEBSD_ABI_TAG 1
#endif
#ifndef DT_FLAGS_1
#define DT_FLAGS_1 0x6ffffffb
#endif
#ifndef DF_1_PIE
#define DF_1_PIE 0x08000000
#endif
#ifndef SHM_LARGEPAGE_ALLOC_DEFAULT
#define SHM_LARGEPAGE_ALLOC_DEFAULT 0
#define SHM_LARGEPAGE_ALLOC_NOWAIT 1
#define SHM_LARGEPAGE_ALLOC_HARD 2
#endif
#ifndef SEM_ALLOC
#define SEM_ALLOC 01000
#endif
#ifndef IXSEQ_TO_IPCID
#define IXSEQ_TO_IPCID(ix, perm) ((int)(((unsigned int)(perm).seq << 16) | (unsigned int)(ix)))
#endif
#if !defined(__FreeBSD__)
struct fbsd_ipc_perm {
    uid_t cuid;
    gid_t cgid;
    uid_t uid;
    gid_t gid;
    mode_t mode;
    unsigned short seq;
    long key;
};
struct fbsd_msqid_ds {
    struct fbsd_ipc_perm msg_perm;
    unsigned long msg_cbytes;
    unsigned long msg_qnum;
    unsigned long msg_qbytes;
    pid_t msg_lspid;
    pid_t msg_lrpid;
    time_t msg_stime;
    time_t msg_rtime;
    time_t msg_ctime;
};
struct fbsd_shmid_ds {
    struct fbsd_ipc_perm shm_perm;
    size_t shm_segsz;
    pid_t shm_lpid;
    pid_t shm_cpid;
    int shm_nattch;
    time_t shm_atime;
    time_t shm_dtime;
    time_t shm_ctime;
};
struct fbsd_semid_ds {
    struct fbsd_ipc_perm sem_perm;
    unsigned short sem_nsems;
    time_t sem_otime;
    time_t sem_ctime;
};
#if !defined(__linux__)
struct shminfo {
    unsigned long shmmax;
    unsigned long shmmin;
    unsigned long shmmni;
    unsigned long shmseg;
    unsigned long shmall;
};
struct seminfo {
    int semmni;
    int semmns;
    int semmnu;
    int semmsl;
    int semopm;
    int semume;
    int semusz;
    int semvmx;
    int semaem;
};
#if !defined(__APPLE__)
struct msginfo {
    int msgmax;
    int msgmni;
    int msgmnb;
    int msgtql;
    int msgssz;
    int msgseg;
};
#endif
#endif
struct msqid_kernel { struct fbsd_msqid_ds u; };
struct shmid_kernel { struct fbsd_shmid_ds u; };
struct semid_kernel { struct fbsd_semid_ds u; };
struct shm_largepage_conf {
    int psind;
    int alloc_policy;
    int pad[10];
};
#ifndef FIOGSHMLPGCNF
#define FIOGSHMLPGCNF 0x40306669UL
#endif
static __inline int shm_create_largepage(const char *path, int flags, int psind, int alloc_policy, mode_t mode) {
    (void)path; (void)flags; (void)psind; (void)alloc_policy; (void)mode;
    return -1;
}
static __inline int getpagesizes(size_t pagesize[], int nelem) {
    if (pagesize != NULL && nelem >= 1) pagesize[0] = 4096;
    return 1;
}
static __inline int str2sig(const char *str, int *signum) {
    static const struct { const char *name; int num; } sigs[] = {
        { "HUP", 1 }, { "INT", 2 }, { "QUIT", 3 }, { "ILL", 4 }, { "TRAP", 5 },
        { "ABRT", 6 }, { "KILL", 9 }, { "SEGV", 11 }, { "PIPE", 13 },
        { "ALRM", 14 }, { "TERM", 15 }, { "CHLD", 17 }, { "CONT", 18 }, { "STOP", 19 }
    };
    size_t i;
    char *end = NULL;
    long v;
    if (!str || !signum) return -1;
    if (strncmp(str, "SIG", 3) == 0) str += 3;
    v = strtol(str, &end, 10);
    if (end && *end == 0 && v > 0 && v < 64) { *signum = (int)v; return 0; }
    for (i = 0; i < sizeof(sigs) / sizeof(sigs[0]); ++i) {
        if (strcasecmp(str, sigs[i].name) == 0) { *signum = sigs[i].num; return 0; }
    }
    return -1;
}
#endif
#ifdef FBSD_TIP_BUILD
#undef NOSTR
#undef NOFILE
#define uu_lock tip_uu_lock
#define uu_unlock tip_uu_unlock
#define sendfile tip_sendfile
#define send tip_send
#endif
#ifdef FBSD_TELNET_BUILD
#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include)
#if __has_include(<netinet/in.h>)
#include <netinet/in.h>
#endif
#if __has_include(<netinet/ip6.h>)
#include <netinet/ip6.h>
#endif
#endif
#if !defined(IP6OPT_TYPE) || defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
struct ip6_rthdr {
    uint8_t ip6r_nxt;
    uint8_t ip6r_len;
    uint8_t ip6r_type;
    uint8_t ip6r_segleft;
};
#endif
#define logout telnet_logout
#endif
#ifdef FBSD_NVI_BUILD
#if defined(__APPLE__) || defined(__linux__)
int openpty(int *amaster, int *aslave, char *name, void *termp, void *winp);
int login_tty(int fd);
#endif
#endif
#ifdef FBSD_POSIXMQ_BUILD
#define recv pmq_recv
#define send pmq_send
#endif
#ifndef EVFILT_PROCDESC
#define EVFILT_PROCDESC (-8)
#endif
#ifdef FBSD_FREEBSD_RLIMITS
#include <sys/resource.h>
#ifndef RLIMIT_SBSIZE
#define RLIMIT_SBSIZE 9
#endif
#ifndef RLIMIT_VMEM
#define RLIMIT_VMEM 10
#endif
#ifndef RLIMIT_NPTS
#define RLIMIT_NPTS 11
#endif
#ifndef RLIMIT_SWAP
#define RLIMIT_SWAP 12
#endif
#ifndef RLIMIT_KQUEUES
#define RLIMIT_KQUEUES 13
#endif
#ifndef RLIMIT_UMTXP
#define RLIMIT_UMTXP 14
#endif
#ifndef RLIMIT_PIPEBUF
#define RLIMIT_PIPEBUF 15
#endif
@_fbsd_rlim_vmm_def@#undef RLIM_NLIMITS
#define RLIM_NLIMITS @_fbsd_rlim_nlimits@
#ifndef EVFILT_LIO
#define EVFILT_LIO (-10)
#endif
#ifndef EVFILT_SENDFILE
#define EVFILT_SENDFILE (-12)
#endif
#ifndef EVFILT_EMPTY
#define EVFILT_EMPTY (-13)
#endif
#ifndef KNOTE_STATUS_ACTIVE
#define KNOTE_STATUS_ACTIVE 0x01
#define KNOTE_STATUS_QUEUED 0x02
#define KNOTE_STATUS_DISABLED 0x04
#define KNOTE_STATUS_DETACHED 0x08
#define KNOTE_STATUS_KQUEUE 0x10
#endif
#ifndef AF_DIVERT
#define AF_DIVERT 44
#endif
#ifndef EV_DROP
#define EV_DROP 0x1000
#endif
#ifndef EV_FLAG2
#define EV_FLAG2 0x4000
#endif
#ifndef NOTE_FILE_POLL
#define NOTE_FILE_POLL 0x0002
#endif
#ifndef NOTE_OPEN
#define NOTE_OPEN 0x0080
#define NOTE_CLOSE 0x0100
#define NOTE_CLOSE_WRITE 0x0200
#define NOTE_READ 0x0400
#endif
#ifndef NOTE_MSECONDS
#define NOTE_MSECONDS 0x00000000
#endif
#ifndef NOTE_ABSTIME
#define NOTE_ABSTIME 0x00000010
#endif
static const char *const rlimit_ident[@_fbsd_rlim_nlimits@] = {
    "cpu", "fsize", "data", "stack", "core", "rss", "memlock", "nproc",
    "nofile", "sbsize", "vmem", "npts", "swap", "kqueues", "umtxp", @_fbsd_rlim_ident_tail@
};
#endif
#ifdef FBSD_MAIL_BUILD
#include <grp.h>
#include <pwd.h>
#define group mail_group
#endif

#include <ctype.h>
#include <fcntl.h>
#include <inttypes.h>
#include <time.h>
#if defined(_WIN32)
#include <io.h>
#elif defined(__DOS__) || defined(__WATCOMC__)
#include <process.h>
#include <setjmp.h>
#include <strings.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#undef __thread
#define __thread
#ifndef __typeof
#define __typeof(x) void *
#endif
#ifndef SAIDX64_T
#define SAIDX64_T
typedef off_t saidx64_t;
#endif
#ifndef sigjmp_buf
typedef jmp_buf sigjmp_buf;
#define sigsetjmp(env, savemask) ((void)(savemask), setjmp(env))
#define siglongjmp(env, val) longjmp((env), (val))
#endif
#endif

#ifndef SSIZE_MAX
#ifdef LONG_MAX
#define SSIZE_MAX LONG_MAX
#else
#define SSIZE_MAX 2147483647L
#endif
#endif
#ifndef EAI_BADFLAGS
#define EAI_BADFLAGS (-1)
#endif
#ifndef EAI_NONAME
#define EAI_NONAME (-2)
#endif
#ifndef EAI_AGAIN
#define EAI_AGAIN (-3)
#endif
#ifndef EAI_FAIL
#define EAI_FAIL (-4)
#endif
#ifndef EAI_FAMILY
#define EAI_FAMILY (-6)
#endif
#ifndef EAI_SOCKTYPE
#define EAI_SOCKTYPE (-7)
#endif
#ifndef EAI_SERVICE
#define EAI_SERVICE (-8)
#endif
#ifndef EAI_MEMORY
#define EAI_MEMORY (-10)
#endif
#ifndef EAI_SYSTEM
#define EAI_SYSTEM (-11)
#endif
#ifndef EAI_OVERFLOW
#define EAI_OVERFLOW (-12)
#endif
#ifndef EOVERFLOW
#define EOVERFLOW ERANGE
#endif
#ifndef ENOTSUP
#ifdef EOPNOTSUPP
#define ENOTSUP EOPNOTSUPP
#else
#define ENOTSUP EINVAL
#endif
#endif
#ifndef EPROTO
#define EPROTO EIO
#endif
#ifndef INET_ADDRSTRLEN
#define INET_ADDRSTRLEN 16
#endif
#ifndef INET6_ADDRSTRLEN
#define INET6_ADDRSTRLEN 46
#endif
#ifndef XO_ENCODERDIR
#define XO_ENCODERDIR "/usr/lib/libxo/encoder"
#endif

#ifdef __cplusplus
extern "C" {
#endif

long long strsuftoll(const char *desc, const char *val, long long min, long long max);
long long strsuftollx(const char *desc, const char *val, long long min, long long max, char *ebuf, size_t ebuflen);
int getdtablecount(void);
#if defined(__APPLE__) && !defined(pipe2)
static __inline int fbsd_apple_pipe2(int pfd[2], int flags) {
    if (pipe(pfd) != 0) return -1;
#ifdef O_CLOEXEC
    if (flags & O_CLOEXEC) {
        (void)fcntl(pfd[0], F_SETFD, FD_CLOEXEC);
        (void)fcntl(pfd[1], F_SETFD, FD_CLOEXEC);
    }
#endif
#ifdef O_NONBLOCK
    if (flags & O_NONBLOCK) {
        int fl0 = fcntl(pfd[0], F_GETFL, 0);
        int fl1 = fcntl(pfd[1], F_GETFL, 0);
        if (fl0 >= 0) (void)fcntl(pfd[0], F_SETFL, fl0 | O_NONBLOCK);
        if (fl1 >= 0) (void)fcntl(pfd[1], F_SETFL, fl1 | O_NONBLOCK);
    }
#endif
    return 0;
}
#define pipe2 fbsd_apple_pipe2
#endif
#if defined(__DOS__) || defined(__WATCOMC__)
int fbsd_dos_spawnvp(int mode, const char *file, const char * const *argv);
int fbsd_dos_execl(const char *path, const char *arg0, ...);
int fbsd_dos_execlp(const char *file, const char *arg0, ...);
#undef _spawnvp
#define _spawnvp(m, f, a) fbsd_dos_spawnvp((m), (f), (const char * const *)(a))
#undef execl
#define execl fbsd_dos_execl
#undef execlp
#define execlp fbsd_dos_execlp
#ifndef sigblock
#define sigblock(mask) (0)
#endif
#ifndef sigsetmask
#define sigsetmask(mask) (0)
#endif
static __inline int fbsd_getw_compat(FILE *fp) {
    int v = 0;
    return fread(&v, sizeof(int), 1, fp) == 1 ? v : EOF;
}
static __inline int fbsd_putw_compat(int v, FILE *fp) {
    return fwrite(&v, sizeof(int), 1, fp) == 1 ? 0 : EOF;
}
#ifndef getw
#define getw fbsd_getw_compat
#endif
#ifndef putw
#define putw fbsd_putw_compat
#endif
#ifndef getc_unlocked
#define getc_unlocked(fp) getc(fp)
#endif
#ifndef putc_unlocked
#define putc_unlocked(c, fp) putc((c), (fp))
#endif
#endif

#ifndef sigmask
#define sigmask(m) (1 << ((m) - 1))
#endif
#ifndef LC_MESSAGES
#define LC_MESSAGES LC_ALL
#endif
#ifndef NL_SETMAX
#define NL_SETMAX 255
#endif
#ifndef NL_MSGMAX
#define NL_MSGMAX 32767
#endif
#ifndef NL_TEXTMAX
#define NL_TEXTMAX 2048
#endif
#ifndef _POSIX_NAME_MAX
#define _POSIX_NAME_MAX 14
#endif
#ifndef _POSIX_PATH_MAX
#define _POSIX_PATH_MAX 256
#endif
#ifndef _POSIX_VDISABLE
#define _POSIX_VDISABLE 0xff
#endif
#ifndef _SC_NGROUPS_MAX
#define _SC_NGROUPS_MAX 4
#endif
#ifndef AF_LOCAL
#ifdef AF_UNIX
#define AF_LOCAL AF_UNIX
#else
#define AF_LOCAL 1
#endif
#endif
#ifndef SUN_LEN
#define SUN_LEN(su) (sizeof(*(su)) - sizeof((su)->sun_path) + strlen((su)->sun_path))
#endif
#ifndef S_ISTXT
#ifdef S_ISVTX
#define S_ISTXT S_ISVTX
#else
#define S_ISTXT 01000
#endif
#endif
#ifndef EPROCLIM
#ifdef WSAEPROCLIM
#define EPROCLIM WSAEPROCLIM
#else
#define EPROCLIM 67
#endif
#endif
#ifndef NODEV
#define NODEV ((dev_t)(-1))
#endif
#ifndef USER_CS_PATH
#define USER_CS_PATH 1
#endif
#ifndef UID_MAX
#define UID_MAX 0xffffffffU
#endif
#ifndef GID_MAX
#define GID_MAX 0xffffffffU
#endif
#ifndef _SC_HOST_NAME_MAX
#define _SC_HOST_NAME_MAX 72
#endif
#ifndef _POSIX_HOST_NAME_MAX
#define _POSIX_HOST_NAME_MAX 255
#endif
#ifndef PRIO_MIN
#define PRIO_MIN (-20)
#define PRIO_MAX 20
#endif
#ifndef _PATH_RWHODIR
#define _PATH_RWHODIR "/var/spool/rwho"
#endif
#ifndef _PC_MIN_HOLE_SIZE
#define _PC_MIN_HOLE_SIZE 21
#endif
#ifndef TIOCMGET
#define TIOCMGET 0x4004746aUL
#define TIOCMSET 0x8004746dUL
#define TIOCM_DTR 0x0002
#define TIOCM_RTS 0x0004
#endif
#ifndef TIOCEXCL
#define TIOCEXCL 0x2000740dUL
#define TIOCNXCL 0x2000740eUL
#endif
#ifndef FPE_INTDIV
#define FPE_INTDIV 1
#define FPE_INTOVF 2
#define FPE_FLTDIV 3
#define FPE_FLTOVF 4
#define FPE_FLTUND 5
#define FPE_FLTRES 6
#define FPE_FLTINV 7
#define FPE_FLTSUB 8
#endif
#ifndef ALTMON_1
#define ALTMON_1 101
#define ALTMON_2 102
#define ALTMON_3 103
#define ALTMON_4 104
#define ALTMON_5 105
#define ALTMON_6 106
#define ALTMON_7 107
#define ALTMON_8 108
#define ALTMON_9 109
#define ALTMON_10 110
#define ALTMON_11 111
#define ALTMON_12 112
#endif
#ifndef LOCK_SH
#define LOCK_SH 0x01
#define LOCK_EX 0x02
#define LOCK_NB 0x04
#define LOCK_UN 0x08
#endif
#ifndef major
#define major(x) ((int)(((unsigned int)(x) >> 8) & 0xffU))
#endif
#ifndef minor
#define minor(x) ((int)((unsigned int)(x) & 0xffU))
#endif
#ifndef makedev
#define makedev(x, y) ((dev_t)((((unsigned int)(x) & 0xffU) << 8) | ((unsigned int)(y) & 0xffU)))
#endif
#ifndef CTRL
#define CTRL(x) ((x) & 037)
#endif

#if !defined(__FreeBSD__) && !defined(__APPLE__)
#ifndef optreset
static int fbsd_optreset_compat;
#define optreset fbsd_optreset_compat
#endif
static __inline void *fbsd_reallocf_compat(void *ptr, size_t size) {
    void *nptr = realloc(ptr, size ? size : 1);
    if (nptr == NULL && ptr != NULL) free(ptr);
    return nptr;
}
#ifndef reallocf
#define reallocf fbsd_reallocf_compat
#endif
static __inline int fbsd_isnumber_compat(int c) {
    return (c >= '0' && c <= '9');
}
#ifndef isnumber
#define isnumber fbsd_isnumber_compat
#endif
static __inline int fbsd_ishexnumber_compat(int c) {
    return ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'));
}
#ifndef ishexnumber
#define ishexnumber fbsd_ishexnumber_compat
#endif
#endif

#if defined(_WIN32) && !defined(_MSC_VER) && !defined(__WATCOMC__) && !defined(__cplusplus)
void *bsd_setmode(const char *p);
#define _FBSD_SETMODE_1(p) bsd_setmode(p)
#define _FBSD_SETMODE_2(fd, m) _setmode((fd), (m))
#define _FBSD_SETMODE_PICK(_1, _2, NAME, ...) NAME
#undef setmode
#define setmode(...) _FBSD_SETMODE_PICK(__VA_ARGS__, _FBSD_SETMODE_2, _FBSD_SETMODE_1)(__VA_ARGS__)
#endif

#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__) || defined(__linux__)
typedef int (*fbsd_funopen_read_fn)(void *, char *, int);
typedef int (*fbsd_funopen_write_fn)(void *, const char *, int);
typedef off_t (*fbsd_funopen_seek_fn)(void *, off_t, int);
typedef int (*fbsd_funopen_close_fn)(void *);
static __inline FILE *fbsd_funopen_compat(
    const void *cookie,
    int (*readfn)(void *, char *, int),
    int (*writefn)(void *, const char *, int),
    off_t (*seekfn)(void *, off_t, int),
    int (*closefn)(void *))
{
    FILE *fp = tmpfile();
    (void)writefn;
    (void)seekfn;
    if (fp == NULL) return NULL;
    if (readfn != NULL) {
        char buf[4096];
        int n;
        while ((n = readfn((void *)cookie, buf, (int)sizeof(buf))) > 0) {
            if (fwrite(buf, 1, (size_t)n, fp) != (size_t)n) break;
        }
        rewind(fp);
    }
    if (closefn != NULL && writefn == NULL) {
        closefn((void *)cookie);
    }
    return fp;
}
#ifndef funopen
#define funopen(c, r, w, s, cl) fbsd_funopen_compat((c), (fbsd_funopen_read_fn)(r), (fbsd_funopen_write_fn)(w), (fbsd_funopen_seek_fn)(s), (fbsd_funopen_close_fn)(cl))
#endif
#endif

#if !defined(__FreeBSD__) && !defined(__APPLE__)
#ifndef EVFILT_READ
#define EVFILT_READ (-1)
#define EVFILT_WRITE (-2)
#define EVFILT_AIO (-3)
#define EVFILT_VNODE (-4)
#define EVFILT_PROC (-5)
#define EVFILT_SIGNAL (-6)
#define EVFILT_TIMER (-7)
#define EVFILT_FS (-9)
#define EVFILT_USER (-11)
#endif
#ifndef EV_ADD
#define EV_ADD 0x0001
#define EV_DELETE 0x0002
#define EV_ENABLE 0x0004
#define EV_DISABLE 0x0008
#define EV_ONESHOT 0x0010
#define EV_CLEAR 0x0020
#define EV_RECEIPT 0x0040
#define EV_DISPATCH 0x0080
#define EV_EOF 0x8000
#define EV_ERROR 0x4000
#endif
#ifndef NOTE_DELETE
#define NOTE_DELETE 0x0001
#define NOTE_WRITE 0x0002
#define NOTE_EXTEND 0x0004
#define NOTE_ATTRIB 0x0008
#define NOTE_LINK 0x0010
#define NOTE_RENAME 0x0020
#define NOTE_REVOKE 0x0040
#endif
#ifndef NOTE_LOWAT
#define NOTE_LOWAT 0x00000001
#define NOTE_MADVISE 0x0080
#define NOTE_EXIT 0x80000000U
#define NOTE_FORK 0x40000000U
#define NOTE_EXEC 0x20000000U
#define NOTE_TRACK 0x00000001
#define NOTE_TRACKERR 0x00000002
#define NOTE_CHILD 0x00000004
#define NOTE_FFNOP 0x00000000
#define NOTE_FFAND 0x40000000U
#define NOTE_FFOR 0x80000000U
#define NOTE_FFCOPY 0xc0000000U
#define NOTE_FFCTRLMASK 0xc0000000U
#define NOTE_FFLAGSMASK 0x00ffffffU
#define NOTE_TRIGGER 0x01000000U
#define NOTE_SECONDS 0x00000001
#define NOTE_USECONDS 0x00000002
#define NOTE_NSECONDS 0x00000003
#endif
#ifndef EV_SET
#define EV_SET(kevp, a, b, c, d, e, f) do { \
    (kevp)->ident = (uintptr_t)(a); \
    (kevp)->filter = (short)(b); \
    (kevp)->flags = (unsigned short)(c); \
    (kevp)->fflags = (unsigned int)(d); \
    (kevp)->data = (intptr_t)(e); \
    (kevp)->udata = (void *)(f); \
} while (0)
#endif
#ifndef SIGEMT
#define SIGEMT 7
#endif
#ifndef S_IFWHT
#define S_IFWHT 0160000
#endif
#ifndef S_ISWHT
#define S_ISWHT(m) (((m) & S_IFMT) == S_IFWHT)
#endif
#ifndef st_birthtime
#define st_birthtime st_birthtim.tv_sec
#endif
static __inline int issetugid(void) { return 0; }
static __inline int fbsd_flsl_compat(long mask) {
    int bit = 0;
    unsigned long u = (unsigned long)mask;
    while (u != 0) { bit++; u >>= 1; }
    return bit;
}
#ifndef flsl
#define flsl fbsd_flsl_compat
#endif
static __inline wint_t nextwctype(wint_t ch, wctype_t wct) {
    unsigned int c = (unsigned int)(ch + 1);
    while (c < 128U) {
        if (iswctype((wint_t)c, wct)) return (wint_t)c;
        c++;
    }
    return (wint_t)-1;
}
static __inline int fbsd_digittoint_compat(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return 0;
}
#ifndef digittoint
#define digittoint fbsd_digittoint_compat
#endif
static __inline int iswrune(wint_t wc) {
    return ((unsigned long)wc <= 0x10ffffUL);
}
#ifndef iscntrl_l
#define iscntrl_l(c, loc) ((void)(loc), iscntrl((unsigned char)(c)))
#endif
static __inline int setlogin(const char *name) { (void)name; return 0; }
static __inline int revoke(const char *path) { (void)path; return 0; }
static const char *const fbsd_sys_signame_compat[32] = {
    "Signal 0", "hup", "int", "quit", "ill", "trap", "abrt", "emt",
    "fpe", "kill", "bus", "segv", "sys", "pipe", "alrm", "term",
    "urg", "stop", "tstp", "cont", "chld", "ttin", "ttou", "io",
    "xcpu", "xfsz", "vtalrm", "prof", "winch", "info", "usr1", "usr2"
};
#ifndef sys_signame
#define sys_signame fbsd_sys_signame_compat
#endif
struct sockaddr;
int sockaddr_snprintf(char *buf, size_t len, const char *fmt, const struct sockaddr *sa);
#endif

#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
#ifndef RLIMIT_MEMLOCK
#define RLIMIT_MEMLOCK 6
#endif
#ifndef RLIMIT_NPROC
#define RLIMIT_NPROC 8
#endif
#ifndef CRTSCTS
#define CRTSCTS 0x00030000
#endif
static __inline char *fbsd_stpcpy_compat(char *dst, const char *src) {
    size_t n = strlen(src);
    memcpy(dst, src, n + 1);
    return dst + n;
}
#ifndef stpcpy
#define stpcpy fbsd_stpcpy_compat
#endif
static __inline struct in_addr inet_makeaddr(uint32_t net, uint32_t host) {
    struct in_addr a;
    uint32_t addr = (net < 128U) ? ((net << 24) | (host & 0x00ffffffU))
        : (net < 65536U) ? ((net << 16) | (host & 0x0000ffffU))
        : ((net << 8) | (host & 0x000000ffU));
    a.s_addr = htonl(addr);
    return a;
}
static __inline uint32_t inet_network(const char *cp) {
    unsigned int b0 = 0, b1 = 0, b2 = 0, b3 = 0;
    int n = cp ? sscanf(cp, "%u.%u.%u.%u", &b0, &b1, &b2, &b3) : 0;
    if (n == 1) return b0;
    if (n == 2) return (b0 << 8) | b1;
    if (n == 3) return (b0 << 16) | (b1 << 8) | b2;
    if (n == 4) return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
    return 0xffffffffU;
}
static __inline void setnetgrent(const char *netgroup) { (void)netgroup; }
static __inline void endnetgrent(void) {}
static __inline int getnetgrent(char **hostp, char **userp, char **domp) {
    (void)hostp; (void)userp; (void)domp;
    return 0;
}
static __inline int innetgr(const char *netgroup, const char *host, const char *user, const char *dom) {
    (void)netgroup; (void)host; (void)user; (void)dom;
    return 0;
}
#ifndef asctime_r
static __inline char *fbsd_asctime_r_compat(const struct tm *tm, char *buf) {
    const char *p = asctime(tm);
    if (p == NULL || buf == NULL) return NULL;
    memcpy(buf, p, strlen(p) + 1);
    return buf;
}
#define asctime_r fbsd_asctime_r_compat
#endif
static __inline char *fbsd_strsignal_compat(int sig) {
    static char sbuf[32];
    snprintf(sbuf, sizeof(sbuf), "Signal %d", sig);
    return sbuf;
}
#ifndef strsignal
#define strsignal fbsd_strsignal_compat
#endif
#ifndef TIOCSETD
#define TIOCSETD 0x8004741bUL
#define TIOCSBRK 0x2000747bUL
#define TIOCCBRK 0x2000747aUL
#endif
#ifndef EV_FLAG1
#define EV_FLAG1 0x2000
#endif
#ifndef EV_FORCEONESHOT
#define EV_FORCEONESHOT 0x0100
#define EV_KEEPUDATA 0x0200
#endif
#ifndef IPV6_RTHDR_TYPE_0
#define IPV6_RTHDR_TYPE_0 0
static __inline socklen_t inet6_rth_space(int type, int segments) { (void)type; (void)segments; return 0; }
static __inline void *inet6_rth_init(void *bp, socklen_t bp_len, int type, int segments) { (void)bp; (void)bp_len; (void)type; (void)segments; return NULL; }
static __inline int inet6_rth_add(void *bp, const void *addr) { (void)bp; (void)addr; return -1; }
#endif
#ifndef _POSIX_ARG_MAX
#define _POSIX_ARG_MAX 4096
#endif
#ifndef QUAD_MAX
#define QUAD_MAX INT64_MAX
#define QUAD_MIN INT64_MIN
#define UQUAD_MAX UINT64_MAX
#endif
#ifndef SO_REUSEPORT
#define SO_REUSEPORT SO_REUSEADDR
#endif
#ifndef TCP_NOOPT
#define TCP_NOOPT 8
#endif
#ifndef TCP_MD5SIG
#define TCP_MD5SIG 16
#endif
#ifndef IPOPT_LSRR
#define IPOPT_EOL 0
#define IPOPT_NOP 1
#define IPOPT_LSRR 131
#define IPOPT_SSRR 137
#endif
#ifndef IPOPT_OLEN
#define IPOPT_OLEN 1
#define IPOPT_OFFSET 2
#define IPOPT_MINOFF 4
#endif
#ifndef S_ISWHT
#define S_ISWHT(m) (((m) & S_IFMT) == S_IFWHT)
#endif
#ifndef NZERO
#define NZERO 0
#endif
#ifndef MAXNAMLEN
#define MAXNAMLEN 255
#endif
#ifndef COLL_WEIGHTS_MAX
#define COLL_WEIGHTS_MAX 10
#endif
#ifndef CERASE
#define CERASE 0177
#define CKILL CTRL('u')
#define CWERASE CTRL('w')
#endif
#ifndef RING_WAIT
#define RING_WAIT 30
#endif
#ifndef TIOCCDTR
#define TIOCCDTR 0x20007478UL
#define TIOCSDTR 0x20007479UL
#define TIOCMBIS 0x8004746cUL
#define TIOCMBIC 0x8004746bUL
#define TIOCM_LE 0x0001
#define TIOCM_ST 0x0008
#define TIOCM_SR 0x0010
#define TIOCM_CTS 0x0020
#define TIOCM_CAR 0x0040
#define TIOCM_RNG 0x0080
#define TIOCM_DSR 0x0100
#endif
#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
static __inline void setbuffer(FILE *f, char *b, size_t s) {
    setvbuf(f, b, b ? _IOFBF : _IONBF, s);
}
static __inline int cfsetspeed(void *t, unsigned int spd) { (void)t; (void)spd; return 0; }
#ifdef FBSD_LOCALEDEF_BUILD
#include <locale.h>
#include <wchar.h>
#include <wctype.h>
#undef wchar_t
#define wchar_t int32_t
static __inline size_t fbsd_ucs4_len(const int32_t *s) {
    size_t n = 0;
    while (s && s[n]) n++;
    return n;
}
static __inline int fbsd_ucs4_cmp(const int32_t *a, const int32_t *b) {
    while (*a && *a == *b) { a++; b++; }
    return (*a > *b) - (*a < *b);
}
static __inline int32_t *fbsd_ucs4_dup(const int32_t *s) {
    size_t n = fbsd_ucs4_len(s);
    int32_t *r = (int32_t *)calloc(n + 1, sizeof(int32_t));
    if (r && n) memcpy(r, s, n * sizeof(int32_t));
    return r;
}
#undef wcslen
#define wcslen fbsd_ucs4_len
#undef wcscmp
#define wcscmp fbsd_ucs4_cmp
#undef wcsdup
#define wcsdup fbsd_ucs4_dup
#endif
#endif
#ifndef TTYDISC
#define TTYDISC 0
#define TABLDISC 3
#define SLIPDISC 4
#define PPPDDISC 5
#define NETGRAPHDISC 6
#endif
#ifndef VDSUSP
#define VDSUSP 11
#endif
#ifndef FSCALE
#ifndef FSHIFT
#define FSHIFT 11
#endif
#define FSCALE (1 << 11)
struct loadavg {
    uint32_t ldavg[3];
    long fscale;
};
#endif
static __inline int getloadavg(double loadavg[], int nelem) {
    int i;
    for (i = 0; i < nelem; ++i) loadavg[i] = 0.0;
    return nelem;
}
#if defined(_WIN32)
static __inline int fbsd_setsockopt_compat(SOCKET s, int level, int optname, const void *optval, socklen_t optlen) {
    return setsockopt(s, level, optname, (const char *)optval, (int)optlen);
}
static __inline int fbsd_getsockopt_compat(SOCKET s, int level, int optname, void *optval, socklen_t *optlen) {
    int wlen = optlen ? (int)*optlen : 0;
    int rc = getsockopt(s, level, optname, (char *)optval, optlen ? &wlen : NULL);
    if (optlen) *optlen = (socklen_t)wlen;
    return rc;
}
#undef setsockopt
#define setsockopt fbsd_setsockopt_compat
#undef getsockopt
#define getsockopt fbsd_getsockopt_compat
#ifdef FBSD_SED_BUILD
#ifdef s_addr
#undef s_addr
#endif
#endif
#endif
struct clockinfo {
    int hz;
    int tick;
    int spare;
    int stathz;
    int profhz;
};
union semun {
    int val;
    void *buf;
    unsigned short *array;
};
static __inline void *gethostbyname2(const char *name, int af) {
    (void)af;
    return (void *)gethostbyname(name);
}
#ifndef PRIO_PROCESS
#define PRIO_PROCESS 0
#define PRIO_PGRP 1
#define PRIO_USER 2
static __inline int getpriority(int which, int who) { (void)which; (void)who; return 0; }
static __inline int setpriority(int which, int who, int prio) { (void)which; (void)who; (void)prio; return 0; }
#endif
#ifndef strtoq
#if defined(_MSC_VER)
#define strtoq _strtoi64
#define strtouq _strtoui64
#else
#define strtoq strtoll
#define strtouq strtoull
#endif
#endif
static __inline char *fbsd_strchrnul_compat(const char *s, int c) {
    while (*s != '\0' && *s != (char)c) s++;
    return (char *)s;
}
#ifndef strchrnul
#define strchrnul fbsd_strchrnul_compat
#endif
static __inline int fbsd_setlinebuf_compat(FILE *stream) {
    return setvbuf(stream, NULL, _IOLBF, 0);
}
#ifndef setlinebuf
#define setlinebuf fbsd_setlinebuf_compat
#endif
static __inline time_t fbsd_timegm_compat(struct tm *tm) {
#if defined(_WIN32) && !defined(__WATCOMC__)
    return _mkgmtime(tm);
#else
    return mktime(tm);
#endif
}
#ifndef timegm
#define timegm fbsd_timegm_compat
#endif
char *strptime(const char *buf, const char *fmt, struct tm *tm);
static __inline char *fbsd_strptime_l_compat(const char *buf, const char *fmt, struct tm *tm, void *loc) {
    (void)loc;
    return strptime(buf, fmt, tm);
}
#ifndef strptime_l
#define strptime_l fbsd_strptime_l_compat
#endif
static __inline size_t fbsd_strftime_l_compat(char *s, size_t maxsize, const char *fmt, const struct tm *tm, void *loc) {
    (void)loc;
    return strftime(s, maxsize, fmt, tm);
}
#ifndef strftime_l
#define strftime_l fbsd_strftime_l_compat
#endif
#ifndef ctime_r
static __inline char *fbsd_ctime_r_compat(const time_t *clock, char *buf) {
    const char *p = ctime(clock);
    if (p == NULL || buf == NULL) return NULL;
    memcpy(buf, p, strlen(p) + 1);
    return buf;
}
#define ctime_r fbsd_ctime_r_compat
#endif
static __inline int flock(int fd, int operation) { (void)fd; (void)operation; return 0; }
static __inline void setusershell(void) {}
static __inline void endusershell(void) {}
static __inline char *getusershell(void) { return NULL; }
static __inline int siginterrupt(int sig, int flag) { (void)sig; (void)flag; return 0; }
static __inline pid_t fbsd_wait4_compat(pid_t pid, int *status, int options, void *rusage) {
    (void)pid; (void)options;
    if (status) *status = 0;
    if (rusage) memset(rusage, 0, 64);
    errno = ECHILD;
    return -1;
}
#ifndef wait4
#define wait4 fbsd_wait4_compat
#endif
static __inline int fbsd_mkstemps_compat(char *tmpl, int suffixlen) {
    size_t len;
    int tries;
    if (tmpl == NULL || suffixlen < 0) return -1;
    len = strlen(tmpl);
    if (len < (size_t)suffixlen + 6) return -1;
    for (tries = 0; tries < 64; ++tries) {
        size_t i;
        int fd;
        unsigned int v = (unsigned int)rand() ^ ((unsigned int)tries * 2654435761U);
        for (i = 0; i < 6; ++i) {
            tmpl[len - (size_t)suffixlen - 6 + i] = "abcdefghijklmnopqrstuvwxyz0123456789"[(v + i * 7) % 36];
        }
        fd = open(tmpl, O_RDWR | O_CREAT | O_EXCL, 0600);
        if (fd >= 0) return fd;
    }
    return -1;
}
#ifndef mkstemps
#define mkstemps fbsd_mkstemps_compat
#endif
static __inline char *fbsd_getpass_compat(const char *prompt) {
    static char pwbuf[128];
    if (prompt != NULL) fputs(prompt, stderr);
    if (fgets(pwbuf, (int)sizeof(pwbuf), stdin) == NULL) pwbuf[0] = '\0';
    else pwbuf[strcspn(pwbuf, "\r\n")] = '\0';
    return pwbuf;
}
#ifndef getpass
#define getpass fbsd_getpass_compat
#endif
static __inline int initgroups(const char *user, gid_t group) { (void)user; (void)group; return 0; }
#ifndef hstrerror
static __inline const char *fbsd_hstrerror_compat(int err) { (void)err; return "resolver error"; }
#define hstrerror fbsd_hstrerror_compat
#endif
#ifndef herror
static __inline void fbsd_herror_compat(const char *s) {
    if (s && *s) fprintf(stderr, "%s: resolver error\n", s);
    else fprintf(stderr, "resolver error\n");
}
#define herror fbsd_herror_compat
#endif
static __inline int openpty(int *amaster, int *aslave, char *name, void *termp, void *winp) {
    (void)amaster; (void)aslave; (void)name; (void)termp; (void)winp;
    errno = ENOSYS;
    return -1;
}
static __inline int login_tty(int fd) { (void)fd; errno = ENOSYS; return -1; }
static __inline FILE *open_memstream(char **bufp, size_t *sizep) {
    if (bufp) *bufp = (char *)calloc(1, 1);
    if (sizep) *sizep = 0;
    return tmpfile();
}
#endif

#ifdef __cplusplus
}
#endif
#endif
]=])
    string(CONFIGURE "${_preinclude_h}" _preinclude_h @ONLY)
    set(_preinclude_path "${ARG_INC_DIR}/freebsd_compat_preinclude.h")
    file(WRITE "${_preinclude_path}" "${_preinclude_h}")

    file(MAKE_DIRECTORY "${ARG_INC_DIR}/arpa")
    file(MAKE_DIRECTORY "${ARG_INC_DIR}/netinet")
    file(MAKE_DIRECTORY "${ARG_INC_DIR}/protocols")
    file(MAKE_DIRECTORY "${ARG_INC_DIR}/sys")

    file(WRITE "${ARG_INC_DIR}/iconv.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<iconv.h>)
#include_next <iconv.h>
#define _FBSD_NATIVE_ICONV_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_ICONV_H
#ifndef _FBSD_PORTABLE_ICONV_H
#define _FBSD_PORTABLE_ICONV_H 1
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef void *iconv_t;
iconv_t iconv_open(const char *tocode, const char *fromcode);
size_t iconv(iconv_t cd, char **inbuf, size_t *inbytesleft, char **outbuf, size_t *outbytesleft);
int iconv_close(iconv_t cd);
#define ICONV_GET_DISCARD_ILSEQ 3
#define ICONV_SET_DISCARD_ILSEQ 4
static __inline int iconvctl(iconv_t cd, int request, void *argument) {
    (void)cd; (void)request; (void)argument;
    return 0;
}
static __inline size_t __iconv(iconv_t cd, char **inbuf, size_t *inbytesleft, char **outbuf, size_t *outbytesleft, unsigned int flags, size_t *invalids) {
    (void)flags;
    if (invalids) *invalids = 0;
    return iconv(cd, inbuf, inbytesleft, outbuf, outbytesleft);
}
static __inline void iconvlist(int (*do_one)(unsigned int, const char *const *, void *), void *data) {
    static const char *const utf8_names[] = { "UTF-8", "ASCII" };
    if (do_one) (void)do_one(2, utf8_names, data);
}
#ifdef __cplusplus
}
#endif
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/termcap.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<termcap.h>)
#include_next <termcap.h>
#define _FBSD_NATIVE_TERMCAP_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_TERMCAP_H
#ifndef _FBSD_PORTABLE_TERMCAP_H
#define _FBSD_PORTABLE_TERMCAP_H 1
#ifdef __cplusplus
extern "C" {
#endif
extern char PC;
extern char *UP;
extern char *BC;
extern short ospeed;
int tgetent(char *bp, const char *name);
int tgetflag(const char *id);
int tgetnum(const char *id);
char *tgetstr(const char *id, char **area);
char *tgoto(const char *cap, int col, int row);
int tputs(const char *str, int affcnt, int (*putc_fn)(int));
#ifdef __cplusplus
}
#endif
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/netinet/if_ether.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<netinet/if_ether.h>)
#include_next <netinet/if_ether.h>
#define _FBSD_NATIVE_IF_ETHER_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_IF_ETHER_H
#ifndef _FBSD_PORTABLE_IF_ETHER_H
#define _FBSD_PORTABLE_IF_ETHER_H 1
#include <stdint.h>
#include <stdio.h>
#ifndef ETHER_ADDR_LEN
#define ETHER_ADDR_LEN 6
#endif
struct ether_addr {
    uint8_t octet[ETHER_ADDR_LEN];
};
static __inline char *ether_ntoa(const struct ether_addr *n) {
    static char buf[18];
    if (!n) return (char *)"00:00:00:00:00:00";
    snprintf(buf, sizeof(buf), "%02x:%02x:%02x:%02x:%02x:%02x",
        n->octet[0], n->octet[1], n->octet[2], n->octet[3], n->octet[4], n->octet[5]);
    return buf;
}
static __inline struct ether_addr *ether_aton(const char *a) {
    static struct ether_addr ea;
    unsigned int b0, b1, b2, b3, b4, b5;
    if (!a || sscanf(a, "%x:%x:%x:%x:%x:%x", &b0, &b1, &b2, &b3, &b4, &b5) != 6) return NULL;
    ea.octet[0] = (uint8_t)b0; ea.octet[1] = (uint8_t)b1; ea.octet[2] = (uint8_t)b2;
    ea.octet[3] = (uint8_t)b3; ea.octet[4] = (uint8_t)b4; ea.octet[5] = (uint8_t)b5;
    return &ea;
}
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/ipc-uapi-windows.h" [=[#ifndef _FBSD_WG_IPC_UAPI_WINDOWS_H
#define _FBSD_WG_IPC_UAPI_WINDOWS_H 1
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
static FILE *userspace_interface_file(const char *iface) {
    (void)iface;
    errno = ENOENT;
    return NULL;
}
static bool userspace_has_wireguard_interface(const char *iface) {
    (void)iface;
    return false;
}
static int userspace_get_wireguard_interfaces(struct string_list *list) {
    (void)list;
    return 0;
}
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/ipc-windows.h" [=[#ifndef _FBSD_WG_IPC_WINDOWS_H
#define _FBSD_WG_IPC_WINDOWS_H 1
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sched.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sched.h>)
#include_next <sched.h>
#define _FBSD_NATIVE_SCHED_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SCHED_H
#include "posix-sched.h"
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/readpassphrase.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<readpassphrase.h>)
#include_next <readpassphrase.h>
#define _FBSD_NATIVE_RPP_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_RPP_H
#ifndef _FBSD_PORTABLE_RPP_H
#define _FBSD_PORTABLE_RPP_H 1
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define RPP_ECHO_OFF    0x00
#define RPP_ECHO_ON     0x01
#define RPP_REQUIRE_TTY 0x02
#define RPP_FORCELOWER  0x04
#define RPP_FORCEUPPER  0x08
#define RPP_SEVENBIT    0x10
#define RPP_STDIN       0x20
static __inline char *readpassphrase(const char *prompt, char *buf, size_t bufsiz, int flags) {
    (void)flags;
    if (buf == NULL || bufsiz == 0) return NULL;
    if (prompt != NULL) fputs(prompt, stderr);
    if (fgets(buf, (int)bufsiz, stdin) == NULL) buf[0] = '\0';
    else buf[strcspn(buf, "\r\n")] = '\0';
    return buf;
}
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/arpa/ftp.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<arpa/ftp.h>)
#include_next <arpa/ftp.h>
#define _FBSD_NATIVE_ARPA_FTP_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_ARPA_FTP_H
#ifndef _FBSD_PORTABLE_ARPA_FTP_H
#define _FBSD_PORTABLE_ARPA_FTP_H 1
#define PRELIM      1
#define COMPLETE    2
#define CONTINUE    3
#define TRANSIENT   4
#define ERROR       5
#define TYPE_A      1
#define TYPE_E      2
#define TYPE_I      3
#define TYPE_L      4
#define FORM_N      1
#define FORM_T      2
#define FORM_C      3
#define STRU_F      1
#define STRU_R      2
#define STRU_P      3
#define MODE_S      1
#define MODE_B      2
#define MODE_C      3
#define REC_ESC     '\377'
#define REC_EOR     '\001'
#define REC_EOF     '\002'
#define BLK_EOR     0x80
#define BLK_EOF     0x40
#define BLK_ERRORS  0x20
#define BLK_RESTART 0x10
#define BLK_BYTECOUNT 2
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/arpa/tftp.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<arpa/tftp.h>)
#include_next <arpa/tftp.h>
#define _FBSD_NATIVE_ARPA_TFTP_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_ARPA_TFTP_H
#ifndef _FBSD_PORTABLE_ARPA_TFTP_H
#define _FBSD_PORTABLE_ARPA_TFTP_H 1
#define SEGSIZE 512
#define MAXSEGSIZE 65464
#define RRQ   01
#define WRQ   02
#define DATA  03
#define ACK   04
#define TFTP_ERROR 05
#ifndef ERROR
#define ERROR 05
#endif
#define OACK  06
struct tftphdr {
    short th_opcode;
    union {
        unsigned short tu_block;
        short tu_code;
        char tu_stuff[1];
    } th_u;
    char th_data[1];
};
#define th_block th_u.tu_block
#define th_code  th_u.tu_code
#define th_stuff th_u.tu_stuff
#define th_msg   th_data
#define EUNDEF    0
#define ENOTFOUND 1
#define EACCESS   2
#define ENOSPACE  3
#define EBADOP    4
#define EBADID    5
#define EEXISTS   6
#define ENOUSER   7
#define EOPTNEG   8
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/arpa/nameser.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<arpa/nameser.h>)
#include_next <arpa/nameser.h>
#define _FBSD_NATIVE_ARPA_NAMESER_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_ARPA_NAMESER_H
#ifndef _FBSD_PORTABLE_ARPA_NAMESER_H
#define _FBSD_PORTABLE_ARPA_NAMESER_H 1
#define NS_MAXDNAME 1025
#define NS_PACKETSZ 512
#define NS_HFIXEDSZ 12
#define NS_QFIXEDSZ 4
#define NS_RRFIXEDSZ 10
#define NS_INT32SZ 4
#define NS_INT16SZ 2
#define NS_INADDRSZ 4
#define NS_IN6ADDRSZ 16
#define MAXDNAME NS_MAXDNAME
#define PACKETSZ NS_PACKETSZ
#define HFIXEDSZ NS_HFIXEDSZ
#define QFIXEDSZ NS_QFIXEDSZ
#define T_A 1
#define T_NS 2
#define T_CNAME 5
#define T_SOA 6
#define T_PTR 12
#define T_MX 15
#define T_TXT 16
#define T_AAAA 28
#define T_SRV 33
#define T_ANY 255
#define C_IN 1
#define C_CHAOS 3
#define C_HS 4
#define C_ANY 255
#define NOERROR 0
#define FORMERR 1
#define SERVFAIL 2
#define NXDOMAIN 3
#define NOTIMP 4
#define REFUSED 5
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/protocols/rwhod.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<protocols/rwhod.h>)
#include_next <protocols/rwhod.h>
#define _FBSD_NATIVE_RWHOD_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_RWHOD_H
#ifndef _FBSD_PORTABLE_RWHOD_H
#define _FBSD_PORTABLE_RWHOD_H 1
#include <stdint.h>
struct outmp {
    char out_line[8];
    char out_name[8];
    int32_t out_time;
};
struct whod {
    char wd_vers;
    char wd_type;
    char wd_pad[2];
    int32_t wd_sendtime;
    int32_t wd_recvtime;
    char wd_hostname[32];
    int32_t wd_loadav[3];
    int32_t wd_boottime;
    struct whoent {
        struct outmp we_utmp;
        int32_t we_idle;
    } wd_we[1024 / sizeof(struct outmp)];
};
#define WHODVERSION 1
#define WHODTYPE_STATUS 1
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/poll.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/poll.h>)
#include_next <sys/poll.h>
#define _FBSD_NATIVE_SYS_POLL_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_POLL_H
#include <poll.h>
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/signal.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/signal.h>)
#include_next <sys/signal.h>
#define _FBSD_NATIVE_SYS_SIGNAL_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_SIGNAL_H
#include <signal.h>
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/ipc.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/ipc.h>)
#include_next <sys/ipc.h>
#define _FBSD_NATIVE_SYS_IPC_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_IPC_H
#ifndef _FBSD_PORTABLE_SYS_IPC_H
#define _FBSD_PORTABLE_SYS_IPC_H 1
#include <sys/types.h>
#include <errno.h>
#define IPC_PRIVATE ((key_t)0)
#define IPC_CREAT  01000
#define IPC_EXCL   02000
#define IPC_NOWAIT 04000
#define IPC_RMID   0
#define IPC_SET    1
#define IPC_STAT   2
#define IPC_INFO   3
struct ipc_perm {
    uid_t cuid;
    gid_t cgid;
    uid_t uid;
    gid_t gid;
    mode_t mode;
    unsigned short seq;
    key_t key;
};
static __inline key_t ftok(const char *path, int id) { (void)path; return (key_t)(id & 0xff); }
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/msg.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/msg.h>)
#include_next <sys/msg.h>
#define _FBSD_NATIVE_SYS_MSG_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_MSG_H
#ifndef _FBSD_PORTABLE_SYS_MSG_H
#define _FBSD_PORTABLE_SYS_MSG_H 1
#include <sys/ipc.h>
typedef unsigned long msgqnum_t;
typedef unsigned long msglen_t;
struct msqid_ds {
    struct ipc_perm msg_perm;
    unsigned long msg_cbytes;
    msgqnum_t msg_qnum;
    msglen_t msg_qbytes;
    pid_t msg_lspid;
    pid_t msg_lrpid;
    time_t msg_stime;
    time_t msg_rtime;
    time_t msg_ctime;
};
static __inline int msgget(key_t key, int msgflg) { (void)key; (void)msgflg; errno = ENOSYS; return -1; }
static __inline int msgctl(int msqid, int cmd, struct msqid_ds *buf) { (void)msqid; (void)cmd; (void)buf; errno = ENOSYS; return -1; }
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/shm.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/shm.h>)
#include_next <sys/shm.h>
#define _FBSD_NATIVE_SYS_SHM_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_SHM_H
#ifndef _FBSD_PORTABLE_SYS_SHM_H
#define _FBSD_PORTABLE_SYS_SHM_H 1
#include <sys/ipc.h>
#define SHM_RDONLY 010000
#define SHM_RND    020000
struct shmid_ds {
    struct ipc_perm shm_perm;
    size_t shm_segsz;
    pid_t shm_lpid;
    pid_t shm_cpid;
    int shm_nattch;
    time_t shm_atime;
    time_t shm_dtime;
    time_t shm_ctime;
};
static __inline int shmget(key_t key, size_t size, int shmflg) { (void)key; (void)size; (void)shmflg; errno = ENOSYS; return -1; }
static __inline int shmctl(int shmid, int cmd, struct shmid_ds *buf) { (void)shmid; (void)cmd; (void)buf; errno = ENOSYS; return -1; }
static __inline void *shmat(int shmid, const void *shmaddr, int shmflg) { (void)shmid; (void)shmaddr; (void)shmflg; errno = ENOSYS; return (void *)-1; }
static __inline int shmdt(const void *shmaddr) { (void)shmaddr; errno = ENOSYS; return -1; }
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/sem.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/sem.h>)
#include_next <sys/sem.h>
#define _FBSD_NATIVE_SYS_SEM_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_SEM_H
#ifndef _FBSD_PORTABLE_SYS_SEM_H
#define _FBSD_PORTABLE_SYS_SEM_H 1
#include <sys/ipc.h>
#define GETNCNT 3
#define GETPID  4
#define GETVAL  5
#define GETALL  6
#define GETZCNT 7
#define SETVAL  8
#define SETALL  9
struct semid_ds {
    struct ipc_perm sem_perm;
    unsigned short sem_nsems;
    time_t sem_otime;
    time_t sem_ctime;
};
struct sembuf {
    unsigned short sem_num;
    short sem_op;
    short sem_flg;
};
static __inline int semget(key_t key, int nsems, int semflg) { (void)key; (void)nsems; (void)semflg; errno = ENOSYS; return -1; }
static __inline int semctl(int semid, int semnum, int cmd, ...) { (void)semid; (void)semnum; (void)cmd; errno = ENOSYS; return -1; }
static __inline int semop(int semid, struct sembuf *sops, size_t nsops) { (void)semid; (void)sops; (void)nsops; errno = ENOSYS; return -1; }
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/ucred.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/ucred.h>)
#include_next <sys/ucred.h>
#define _FBSD_NATIVE_SYS_UCRED_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_UCRED_H
#ifndef _FBSD_PORTABLE_SYS_UCRED_H
#define _FBSD_PORTABLE_SYS_UCRED_H 1
#include <sys/types.h>
#define XU_NGROUPS 16
struct xucred {
    unsigned int cr_version;
    uid_t cr_uid;
    short cr_ngroups;
    gid_t cr_groups[XU_NGROUPS];
};
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/syscall.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/syscall.h>)
#include_next <sys/syscall.h>
#define _FBSD_NATIVE_SYS_SYSCALL_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_SYSCALL_H
#define SYS_syscall 0
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/dirent.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/dirent.h>)
#include_next <sys/dirent.h>
#define _FBSD_NATIVE_SYS_DIRENT_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_DIRENT_H
#include <dirent.h>
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/fcntl.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/fcntl.h>)
#include_next <sys/fcntl.h>
#define _FBSD_NATIVE_SYS_FCNTL_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_FCNTL_H
#include <fcntl.h>
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/stdatomic.h" [=[#if !defined(_MSC_VER) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<stdatomic.h>)
#include_next <stdatomic.h>
#define _FBSD_NATIVE_STDATOMIC_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_STDATOMIC_H
#ifndef _FBSD_PORTABLE_STDATOMIC_H
#define _FBSD_PORTABLE_STDATOMIC_H 1
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifndef _Atomic
#define _Atomic(T) volatile T
#endif
typedef volatile bool atomic_bool;
typedef volatile int atomic_int;
typedef volatile unsigned int atomic_uint;
typedef volatile long atomic_long;
typedef volatile unsigned long atomic_ulong;
typedef volatile size_t atomic_size_t;
typedef struct { volatile int _flag; } atomic_flag;
#define ATOMIC_FLAG_INIT { 0 }
#define ATOMIC_VAR_INIT(v) (v)
typedef enum {
    memory_order_relaxed = 0,
    memory_order_consume = 1,
    memory_order_acquire = 2,
    memory_order_release = 3,
    memory_order_acq_rel = 4,
    memory_order_seq_cst = 5
} memory_order;
static __inline void atomic_thread_fence(memory_order o) { (void)o; }
static __inline void atomic_signal_fence(memory_order o) { (void)o; }
#define atomic_init(obj, val) (*(obj) = (val))
#define atomic_store(obj, val) (*(obj) = (val))
#define atomic_store_explicit(obj, val, ord) ((void)(ord), *(obj) = (val))
#define atomic_load(obj) (*(obj))
#define atomic_load_explicit(obj, ord) ((void)(ord), *(obj))
#define atomic_fetch_add(obj, arg) ((*(obj) += (arg)) - (arg))
#define atomic_fetch_sub(obj, arg) ((*(obj) -= (arg)) + (arg))
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/_types.h" [=[#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__) && defined(__has_include_next)
#if __has_include_next(<sys/_types.h>)
#include_next <sys/_types.h>
#define _FBSD_NATIVE_SYS_UNDERSCORE_TYPES_H 1
#endif
#endif
#ifndef _FBSD_NATIVE_SYS_UNDERSCORE_TYPES_H
#ifndef _FBSD_PORTABLE_SYS_UNDERSCORE_TYPES_H
#define _FBSD_PORTABLE_SYS_UNDERSCORE_TYPES_H 1
#include <stddef.h>
#include <stdint.h>
typedef int32_t __ct_rune_t;
typedef int32_t __rune_t;
typedef int32_t __wchar_t;
typedef int32_t __wint_t;
typedef size_t __size_t;
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/ktrace.h" [=[#ifndef _FBSD_PORTABLE_SYS_KTRACE_H
#define _FBSD_PORTABLE_SYS_KTRACE_H 1
#include <errno.h>
#define KTROP_SET       0
#define KTROP_CLEAR     1
#define KTROP_CLEARFILE 2
#define KTRFLAG_DESCEND 4
#define KTRFAC_SYSCALL      (1 << 1)
#define KTRFAC_SYSRET       (1 << 2)
#define KTRFAC_NAMEI        (1 << 3)
#define KTRFAC_GENIO        (1 << 4)
#define KTRFAC_PSIG         (1 << 5)
#define KTRFAC_CSW          (1 << 6)
#define KTRFAC_USER         (1 << 7)
#define KTRFAC_STRUCT       (1 << 8)
#define KTRFAC_SYSCTL       (1 << 9)
#define KTRFAC_PROCCTOR     (1 << 10)
#define KTRFAC_PROCDTOR     (1 << 11)
#define KTRFAC_CAPFAIL      (1 << 12)
#define KTRFAC_FAULT        (1 << 13)
#define KTRFAC_FAULTEND     (1 << 14)
#define KTRFAC_STRUCT_ARRAY (1 << 15)
#define KTRFAC_ARGS         (1 << 16)
#define KTRFAC_ENVS         (1 << 17)
#define KTRFAC_EXTERR       (1 << 18)
#define KTRFAC_INHERIT      0x80000000
#ifndef DEFFILEMODE
#define DEFFILEMODE 0666
#endif
#if !defined(__FreeBSD__)
static __inline int ktrace(const char *tracefile, int ops, int facs, int pid) {
    (void)tracefile; (void)ops; (void)facs; (void)pid;
    errno = ENOSYS;
    return -1;
}
#endif
#endif
]=])

    file(WRITE "${ARG_INC_DIR}/sys/ktr.h" [=[#ifndef _FBSD_PORTABLE_SYS_KTR_H
#define _FBSD_PORTABLE_SYS_KTR_H 1
#include <stdint.h>
#include <sys/types.h>
#define KTR_VERSION 2
#define KTR_PARMS   6
struct thread;
struct ktr_entry {
    uint64_t ktr_timestamp;
    int ktr_cpu;
    int ktr_line;
    const char *ktr_file;
    const char *ktr_desc;
    struct thread *ktr_thread;
    unsigned long ktr_parms[KTR_PARMS];
};
#endif
]=])

    if(ARG_OUT_HEADERS_VAR)
        set(${ARG_OUT_HEADERS_VAR}
            "${_osreldate_path}"
            "${_pathnames_path}"
            "${_libxo_path}"
            "${_preinclude_path}"
            PARENT_SCOPE
        )
    endif()
endfunction()

# -----------------------------------------------------------------------------
# freebsd_emit_libcompat_c(
#   SRC_DIR <dir>
#   [OUT_FILE_VAR <var>]
# )
#
# Generate src/freebsd_libcompat.c providing libxo text emitters, fbsd_fgetwln,
# and fbsd_wcwidth helpers.
#
# Arguments:
#   SRC_DIR      - Output src directory inside freebsd_generated.
#   OUT_FILE_VAR - Optional caller variable receiving generated C file path.
# -----------------------------------------------------------------------------
function(freebsd_emit_libcompat_c)
    set(_options "")
    set(_one_value_args SRC_DIR OUT_FILE_VAR)
    set(_multi_value_args "")
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    if(NOT ARG_SRC_DIR)
        message(FATAL_ERROR "freebsd_emit_libcompat_c: SRC_DIR is required")
    endif()

    file(MAKE_DIRECTORY "${ARG_SRC_DIR}")
    set(_out_file "${ARG_SRC_DIR}/freebsd_libcompat.c")

    set(_libcompat_tpl [=[#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#if defined(__DOS__) || defined(__WATCOMC__)
int fbsd_dos_spawnvp(int mode, const char *file, const char * const *argv) {
    char cmd[1024];
    size_t pos = 0;
    int i;
    (void)mode;
    if (file == NULL || argv == NULL || argv[0] == NULL) {
        errno = EINVAL;
        return -1;
    }
    cmd[0] = '\0';
    for (i = 0; argv[i] != NULL; ++i) {
        const char *a = (i == 0) ? file : argv[i];
        size_t alen = strlen(a);
        if (pos + alen + 4 >= sizeof(cmd)) break;
        if (i > 0) cmd[pos++] = ' ';
        memcpy(cmd + pos, a, alen);
        pos += alen;
        cmd[pos] = '\0';
    }
    return system(cmd);
}
int fbsd_dos_execl(const char *path, const char *arg0, ...) {
    const char *args[64];
    va_list ap;
    int n = 0;
    int rc;
    if (path == NULL || arg0 == NULL) {
        errno = EINVAL;
        return -1;
    }
    args[n++] = arg0;
    va_start(ap, arg0);
    while (n < 63) {
        const char *p = va_arg(ap, const char *);
        args[n++] = p;
        if (p == NULL) break;
    }
    args[63] = NULL;
    va_end(ap);
    rc = fbsd_dos_spawnvp(0, path, args);
    if (rc >= 0) exit(rc);
    return -1;
}
int fbsd_dos_execlp(const char *file, const char *arg0, ...) {
    const char *args[64];
    va_list ap;
    int n = 0;
    int rc;
    if (file == NULL || arg0 == NULL) {
        errno = EINVAL;
        return -1;
    }
    args[n++] = arg0;
    va_start(ap, arg0);
    while (n < 63) {
        const char *p = va_arg(ap, const char *);
        args[n++] = p;
        if (p == NULL) break;
    }
    args[63] = NULL;
    va_end(ap);
    rc = fbsd_dos_spawnvp(0, file, args);
    if (rc >= 0) exit(rc);
    return -1;
}
#endif
#include <libxo/xo.h>

#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)
char *posix_langinfo(int item) {
    (void)item;
    return (char *)"UTF-8";
}
#endif

#if !defined(__FreeBSD__)
int __detect_path_locale(void) {
    return 0;
}

#if !defined(__linux__)
void *iconv_open(const char *tocode, const char *fromcode) {
    (void)tocode;
    (void)fromcode;
    return (void *)1;
}

int iconv_close(void *cd) {
    (void)cd;
    return 0;
}

size_t iconv(void *cd, char **inbuf, size_t *inbytesleft, char **outbuf, size_t *outbytesleft) {
    size_t n;
    (void)cd;
    if (inbuf == NULL || *inbuf == NULL || inbytesleft == NULL) return 0;
    if (outbuf == NULL || *outbuf == NULL || outbytesleft == NULL) {
        errno = E2BIG;
        return (size_t)-1;
    }
    n = (*inbytesleft < *outbytesleft) ? *inbytesleft : *outbytesleft;
    memcpy(*outbuf, *inbuf, n);
    *inbuf += n;
    *inbytesleft -= n;
    *outbuf += n;
    *outbytesleft -= n;
    if (*inbytesleft > 0) {
        errno = E2BIG;
        return (size_t)-1;
    }
    return 0;
}
#endif

size_t __iconv(void *cd, char **inbuf, size_t *inbytesleft, char **outbuf,
               size_t *outbytesleft, unsigned int flags, size_t *invalids) {
    size_t n;
    (void)cd;
    (void)flags;
    if (invalids != NULL) *invalids = 0;
    if (inbuf == NULL || *inbuf == NULL || inbytesleft == NULL) return 0;
    if (outbuf == NULL || *outbuf == NULL || outbytesleft == NULL) {
        errno = E2BIG;
        return (size_t)-1;
    }
    n = (*inbytesleft < *outbytesleft) ? *inbytesleft : *outbytesleft;
    memcpy(*outbuf, *inbuf, n);
    *inbuf += n;
    *inbytesleft -= n;
    *outbuf += n;
    *outbytesleft -= n;
    if (*inbytesleft > 0) {
        errno = E2BIG;
        return (size_t)-1;
    }
    return 0;
}

int iconvctl(void *cd, int request, void *argument) {
    (void)cd;
    (void)request;
    if (argument != NULL) *(int *)argument = 0;
    return 0;
}

void iconvlist(int (*do_one)(unsigned int, const char * const *, void *), void *data) {
    static const char * const utf8_names[] = { "UTF-8", "UTF8" };
    static const char * const ascii_names[] = { "US-ASCII", "ASCII", "ISO646-US" };
    static const char * const latin1_names[] = { "ISO-8859-1", "LATIN1" };
    if (do_one != NULL) {
        if (do_one(2, utf8_names, data) == 0 && do_one(3, ascii_names, data) == 0) {
            (void)do_one(2, latin1_names, data);
        }
    }
}
#endif

static wchar_t *g_fgetwln_buf = NULL;
static size_t g_fgetwln_cap = 0;

wchar_t *fbsd_fgetwln(FILE *stream, size_t *lenp) {
    size_t idx = 0;
    wint_t wc;
    if (lenp != NULL) *lenp = 0;
    if (stream == NULL) return NULL;
    while ((wc = fgetwc(stream)) != WEOF) {
        if (idx + 2 > g_fgetwln_cap) {
            size_t ncap = (g_fgetwln_cap == 0) ? 256 : (g_fgetwln_cap * 2);
            wchar_t *nbuf = (wchar_t *)realloc(g_fgetwln_buf, ncap * sizeof(wchar_t));
            if (nbuf == NULL) return NULL;
            g_fgetwln_buf = nbuf;
            g_fgetwln_cap = ncap;
        }
        g_fgetwln_buf[idx++] = (wchar_t)wc;
        if (wc == L'@_FBSD_BS@n') break;
    }
    if (idx == 0) return NULL;
    g_fgetwln_buf[idx] = L'@_FBSD_BS@0';
    if (lenp != NULL) *lenp = idx;
    return g_fgetwln_buf;
}

int fbsd_wcwidth(wchar_t c) {
    if (c == 0) return 0;
    if (c < 32 || (c >= 0x7f && c < 0xa0)) return -1;
    return 1;
}

int fbsd_wcswidth(const wchar_t *pwcs, size_t n) {
    int width = 0;
    size_t i;
    if (pwcs == NULL) return 0;
    for (i = 0; i < n && pwcs[i] != 0; i++) {
        int w = fbsd_wcwidth(pwcs[i]);
        if (w < 0) return -1;
        width += w;
    }
    return width;
}

int fbsd_getdtablecount_shim(void) {
    return 3;
}

int fbsd_b64_ntop(const unsigned char *src, size_t srclength, char *target, size_t targsize) {
    static const char b64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t datalength = 0;
    unsigned char input[3];
    unsigned char output[4];
    size_t i;
    while (2 < srclength) {
        input[0] = *src++; input[1] = *src++; input[2] = *src++;
        srclength -= 3;
        output[0] = (unsigned char)(input[0] >> 2);
        output[1] = (unsigned char)(((input[0] & 0x03) << 4) + (input[1] >> 4));
        output[2] = (unsigned char)(((input[1] & 0x0f) << 2) + (input[2] >> 6));
        output[3] = (unsigned char)(input[2] & 0x3f);
        if (datalength + 4 >= targsize) return -1;
        target[datalength++] = b64[output[0]];
        target[datalength++] = b64[output[1]];
        target[datalength++] = b64[output[2]];
        target[datalength++] = b64[output[3]];
    }
    if (0 != srclength) {
        input[0] = input[1] = input[2] = 0;
        for (i = 0; i < srclength; i++) input[i] = *src++;
        output[0] = (unsigned char)(input[0] >> 2);
        output[1] = (unsigned char)(((input[0] & 0x03) << 4) + (input[1] >> 4));
        output[2] = (unsigned char)(((input[1] & 0x0f) << 2) + (input[2] >> 6));
        if (datalength + 4 >= targsize) return -1;
        target[datalength++] = b64[output[0]];
        target[datalength++] = b64[output[1]];
        target[datalength++] = (srclength == 1) ? '=' : b64[output[2]];
        target[datalength++] = '=';
    }
    if (datalength >= targsize) return -1;
    target[datalength] = 0;
    return (int)datalength;
}

int fbsd_b64_pton(const char *src, unsigned char *target, size_t targsize) {
    static const char b64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t tarindex = 0;
    int state = 0;
    int ch;
    const char *pos;
    while ((ch = (unsigned char)*src++) != 0) {
        if (ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n') continue;
        if (ch == '=') break;
        pos = strchr(b64, ch);
        if (pos == NULL) return -1;
        switch (state) {
            case 0:
                if (target) { if (tarindex >= targsize) return -1; target[tarindex] = (unsigned char)((pos - b64) << 2); }
                state = 1; break;
            case 1:
                if (target) { if (tarindex + 1 >= targsize) return -1; target[tarindex] |= (unsigned char)((pos - b64) >> 4); target[tarindex + 1] = (unsigned char)(((pos - b64) & 0x0f) << 4); }
                tarindex++; state = 2; break;
            case 2:
                if (target) { if (tarindex + 1 >= targsize) return -1; target[tarindex] |= (unsigned char)((pos - b64) >> 2); target[tarindex + 1] = (unsigned char)(((pos - b64) & 0x03) << 6); }
                tarindex++; state = 3; break;
            case 3:
                if (target) { if (tarindex >= targsize) return -1; target[tarindex] |= (unsigned char)(pos - b64); }
                tarindex++; state = 0; break;
        }
    }
    return (int)tarindex;
}

#ifdef FBSD_LIBXO_MINIMAL_SHIM
xo_handle_t *xo_create_to_file(FILE *fp, unsigned style, unsigned flags) {
    (void)style; (void)flags;
    return (xo_handle_t *)fp;
}
int xo_parse_args(int argc, char **argv) { (void)argv; return argc; }
int xo_set_program(const char *name) { (void)name; return 0; }
int xo_set_version(const char *version) { (void)version; return 0; }
int xo_set_flags(void *xop, unsigned flags) { (void)xop; (void)flags; return 0; }
int xo_get_style(void *xop) { (void)xop; return XO_STYLE_TEXT; }
int xo_open_container(const char *name) { (void)name; return 0; }
int xo_close_container(const char *name) { (void)name; return 0; }
int xo_open_list(const char *name) { (void)name; return 0; }
int xo_close_list(const char *name) { (void)name; return 0; }
int xo_open_instance(const char *name) { (void)name; return 0; }
int xo_close_instance(const char *name) { (void)name; return 0; }
int xo_attr(const char *name, const char *fmt, ...) { (void)name; (void)fmt; return 0; }
void xo_flush(void) { fflush(stdout); }
void xo_flush_h(xo_handle_t *xop) { fflush(xop ? (FILE *)xop : stdout); }
int xo_finish(void) { fflush(stdout); return 0; }
int xo_finish_h(xo_handle_t *xop) { fflush(xop ? (FILE *)xop : stdout); return 0; }
void xo_finish_atexit(void) { fflush(stdout); }

static int xo_vemit_to(FILE *out, const char *fmt, va_list ap) {
    const char *p = fmt;
    char pfmt[512];
    size_t idx = 0;
    while (*p && idx + 4 < sizeof(pfmt)) {
        if (*p == '{') {
            const char *close = strchr(p, '}');
            if (close == NULL) break;
            if (p[1] == ':' || p[1] == 'd' || p[1] == 'k' ||
                p[1] == 'v' || p[1] == ' ') {
                const char *pct = strchr(p, '%');
                if (pct != NULL && pct < close) {
                    while (pct < close && *pct != '/' && idx + 2 < sizeof(pfmt)) {
                        pfmt[idx++] = *pct++;
                    }
                } else {
                    pfmt[idx++] = '%';
                    pfmt[idx++] = 's';
                }
            }
            p = close + 1;
        } else {
            pfmt[idx++] = *p++;
        }
    }
    pfmt[idx] = '@_FBSD_BS@0';
    return vfprintf(out, pfmt, ap);
}

int xo_emit(const char *fmt, ...) {
    va_list ap;
    int ret;
    va_start(ap, fmt);
    ret = xo_vemit_to(stdout, fmt, ap);
    va_end(ap);
    return ret;
}

int xo_emit_h(xo_handle_t *xop, const char *fmt, ...) {
    va_list ap;
    int ret;
    va_start(ap, fmt);
    ret = xo_vemit_to(xop ? (FILE *)xop : stdout, fmt, ap);
    va_end(ap);
    return ret;
}

void xo_error(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

void xo_err(int eval, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, ": %s@_FBSD_BS@n", strerror(errno));
    exit(eval);
}

void xo_errx(int eval, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, "@_FBSD_BS@n");
    exit(eval);
}

void xo_warn(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, ": %s@_FBSD_BS@n", strerror(errno));
}

void xo_warnx(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, "@_FBSD_BS@n");
}

void xo_warnc(int code, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, ": %s@_FBSD_BS@n", strerror(code));
}
#endif /* FBSD_LIBXO_MINIMAL_SHIM */

#if defined(_WIN32) || defined(__DOS__) || defined(__WATCOMC__)
const char *__progname = "freebsd-usr-bin";
const char *_PathLocale = "/usr/share/locale";

void osdep_uuidgen(void *uuid_ptr) {
    unsigned char *b = (unsigned char *)uuid_ptr;
    size_t i;
    unsigned int seed = (unsigned int)rand() ^ 0x9e3779b9U;
    if (b == NULL) return;
    for (i = 0; i < 16; ++i) {
        seed = seed * 1664525U + 1013904223U;
        b[i] = (unsigned char)(seed >> 16);
    }
    b[6] = (unsigned char)((b[6] & 0x0fU) | 0x40U);
    b[8] = (unsigned char)((b[8] & 0x3fU) | 0x80U);
}
#endif

#if !defined(__FreeBSD__) && !defined(__NetBSD__)
#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#elif !defined(__DOS__) && !defined(__WATCOMC__)
#include <sys/socket.h>
#include <netdb.h>
#endif
int sockaddr_snprintf(char *buf, size_t len, const char *fmt, const struct sockaddr *sa_ptr) {
    char host[128];
    (void)fmt;
    if (buf == NULL || len == 0) return -1;
    host[0] = '\0';
#if !defined(__DOS__) && !defined(__WATCOMC__)
    if (sa_ptr != NULL) {
        const struct sockaddr *sa = sa_ptr;
        socklen_t salen = (sa->sa_family == AF_INET6) ? (socklen_t)sizeof(struct sockaddr_in6) : (socklen_t)sizeof(struct sockaddr_in);
        if (getnameinfo(sa, salen, host, (socklen_t)sizeof(host), NULL, 0, NI_NUMERICHOST) != 0) {
            host[0] = '\0';
        }
    }
#else
    (void)sa_ptr;
#endif
    return snprintf(buf, len, "%s", host[0] ? host : "0.0.0.0");
}
#endif

]=])
    string(CONFIGURE "${_libcompat_tpl}" _libcompat_c @ONLY)
    file(WRITE "${_out_file}" "${_libcompat_c}")

    if(ARG_OUT_FILE_VAR)
        set(${ARG_OUT_FILE_VAR} "${_out_file}" PARENT_SCOPE)
    endif()
endfunction()

# -----------------------------------------------------------------------------
# freebsd_transform_applet_source(<input_var> <applet_id> <output_var>)
#
# Rename main(...) and file-static identifiers in the C source text held by
# caller variable <input_var> for multicall compilation.
#
# Arguments:
#   INPUT_VAR  - Name of caller variable holding the raw C source string.
#   APPLET_ID  - Sanitized C identifier for the applet (e.g. "basename").
#   OUTPUT_VAR - Name of caller variable receiving transformed C source string.
# -----------------------------------------------------------------------------
function(freebsd_transform_applet_source INPUT_VAR APPLET_ID OUTPUT_VAR)
    if("${APPLET_ID}" STREQUAL "")
        message(FATAL_ERROR "freebsd_transform_applet_source: APPLET_ID is required")
    endif()

    set(_text "${${INPUT_VAR}}")
    string(JOIN "|" _sym_alt ${FREEBSD_STATIC_IDS_TO_RENAME})
    set(_sym_re "(^|[^A-Za-z0-9_])(${_sym_alt})([^A-Za-z0-9_]|$)")
    set(_sym_rep "${_FBSD_BS}1fbsd_${APPLET_ID}_${_FBSD_BS}2${_FBSD_BS}3")

    foreach(_pass IN ITEMS 1 2)
        string(REGEX REPLACE "${_sym_re}" "${_sym_rep}" _text "${_text}")
    endforeach()
    string(REGEX REPLACE "(#[ ${_FBSD_TAB}]*include[ ${_FBSD_TAB}]*[<${_FBSD_DQ}][^>${_FBSD_DQ}]*)fbsd_${APPLET_ID}_" "${_FBSD_BS}1" _text "${_text}")

    set(_ws "[ ${_FBSD_TAB}${_FBSD_CR}${_FBSD_NL}]")
    set(_lp "${_FBSD_BS}(")
    set(_rp "${_FBSD_BS})")
    set(_st "${_FBSD_BS}*")
    set(_lb "${_FBSD_BS}[")
    set(_rb "${_FBSD_BS}]")
    set(_main_void_re "(^|[^A-Za-z0-9_])main${_ws}*${_lp}${_ws}*void${_ws}*${_rp}")
    set(_main_args_re "(^|[^A-Za-z0-9_])main(${_ws}*${_lp}${_ws}*int${_ws}+[A-Za-z_][A-Za-z0-9_]*(${_ws}+__unused)?${_ws}*,${_ws}*(const${_ws}+)?char${_ws}*${_st}${_ws}*${_st}?${_ws}*[A-Za-z_][A-Za-z0-9_]*(${_ws}*${_lb}${_ws}*${_rb})?(${_ws}+__unused)?${_ws}*${_rp})")

    string(REGEX REPLACE "${_main_void_re}" "${_FBSD_BS}1fbsd_${APPLET_ID}_main(int argc, char *argv[])" _text "${_text}")
    string(REGEX REPLACE "${_main_args_re}" "${_FBSD_BS}1fbsd_${APPLET_ID}_main${_FBSD_BS}2" _text "${_text}")

    if("${APPLET_ID}" STREQUAL "col")
        set(_text "#ifdef _WIN32${_FBSD_NL}#undef CHAR${_FBSD_NL}#define CHAR fbsd_col_CHAR${_FBSD_NL}#endif${_FBSD_NL}${_text}")
    elseif("${APPLET_ID}" STREQUAL "join")
        set(_text "#ifdef _WIN32${_FBSD_NL}#undef INPUT${_FBSD_NL}#define INPUT fbsd_join_INPUT${_FBSD_NL}#endif${_FBSD_NL}${_text}")
    elseif("${APPLET_ID}" STREQUAL "tr")
        set(_text "#ifdef _WIN32${_FBSD_NL}#undef DELETE${_FBSD_NL}#endif${_FBSD_NL}${_text}")
    elseif("${APPLET_ID}" STREQUAL "tee")
        string(REPLACE "sun.sun_len = SUN_LEN(&sun);" "#if defined(__FreeBSD__) || defined(__APPLE__)${_FBSD_NL}sun.sun_len = SUN_LEN(&sun);${_FBSD_NL}#endif" _text "${_text}")
        string(REPLACE "connect(fd, (const struct sockaddr *)&sun, sun.sun_len)" "connect(fd, (const struct sockaddr *)&sun, (socklen_t)sizeof(sun))" _text "${_text}")
    endif()

    set(${OUTPUT_VAR} "${_text}" PARENT_SCOPE)
endfunction()

# -----------------------------------------------------------------------------
# freebsd_emit_multicall_applets_and_dispatcher(
#   FREEBSD_SRC_DIR <dir>
#   OUT_DIR <dir>
# )
#
# Audit all entries in <FREEBSD_SRC_DIR>/usr.bin and emit:
#   - applets/fbsd_<applet>.c wrappers (direct transformed C sources or stubs)
#   - src/freebsd_multicall_main.c unified dispatcher
#   - freebsd_usr_bin_targets.cmake utility manifest
#   - enabled_sources.cmake source list for CMake target compilation
#
# Arguments:
#   FREEBSD_SRC_DIR - Path to upstream freebsd-src root directory.
#   OUT_DIR         - Destination freebsd_generated directory.
# -----------------------------------------------------------------------------
function(freebsd_emit_multicall_applets_and_dispatcher)
    set(_options "")
    set(_one_value_args FREEBSD_SRC_DIR OUT_DIR)
    set(_multi_value_args "")
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    if(NOT ARG_FREEBSD_SRC_DIR)
        message(FATAL_ERROR "freebsd_emit_multicall_applets_and_dispatcher: FREEBSD_SRC_DIR is required")
    endif()
    if(NOT ARG_OUT_DIR)
        message(FATAL_ERROR "freebsd_emit_multicall_applets_and_dispatcher: OUT_DIR is required")
    endif()

    get_filename_component(_srctop "${ARG_FREEBSD_SRC_DIR}" REALPATH)
    set(_usr_bin "${_srctop}/usr.bin")
    if(NOT IS_DIRECTORY "${_usr_bin}")
        message(FATAL_ERROR "Error: FreeBSD usr.bin directory not found: ${_usr_bin}")
    endif()

    set(_applets_dir "${ARG_OUT_DIR}/applets")
    set(_src_dir "${ARG_OUT_DIR}/src")
    file(MAKE_DIRECTORY "${_applets_dir}")
    file(MAKE_DIRECTORY "${_src_dir}")

    get_filename_component(_out_real "${ARG_OUT_DIR}" REALPATH)
    get_filename_component(_applets_real "${_applets_dir}" REALPATH)
    get_filename_component(_src_real "${_src_dir}" REALPATH)

    file(GLOB _all_entries RELATIVE "${_usr_bin}" "${_usr_bin}/*")
    list(SORT _all_entries)

    set(_top_makefiles "")
    set(_subdirs "")
    foreach(_ent IN LISTS _all_entries)
        if(IS_DIRECTORY "${_usr_bin}/${_ent}")
            list(APPEND _subdirs "${_ent}")
        else()
            list(APPEND _top_makefiles "${_ent}")
        endif()
    endforeach()

    list(LENGTH _top_makefiles _top_mk_count)
    list(LENGTH _subdirs _subdir_count)
    math(EXPR _total_entries "${_top_mk_count} + ${_subdir_count}")

    set(_applet_files "")
    set(_dispatch_names "")
    set(_unique_fns "")
    set(_targets_meta "")
    set(_dollar_re "^${_FBSD_BS}${_FBSD_DL}")

    set(_idx 0)
    foreach(_d_name IN LISTS _subdirs)
        math(EXPR _idx "${_idx} + 1")
        string(TOLOWER "${_d_name}" _d_lower)
        string(REGEX REPLACE "[^A-Za-z0-9_]" "_" _safe_id "${_d_lower}")
        string(TOUPPER "${_d_name}" _d_upper)
        string(REGEX REPLACE "[^A-Za-z0-9_]" "_" _upper_id "${_d_upper}")

        set(_fn_name "fbsd_${_safe_id}_main")
        list(APPEND _unique_fns "${_fn_name}")
        set(_out_c "${_applets_real}/fbsd_${_safe_id}.c")

        get_filename_component(_curdir "${_usr_bin}/${_d_name}" REALPATH)
        set(_prog_name "${_d_name}")
        set(_links "")

        if(EXISTS "${_curdir}/Makefile")
            set(_ep "_FBSD_ENV_${_idx}_")
            set("${_ep}SRCTOP" "${_srctop}")
            set("${_ep}.CURDIR" "${_curdir}")
            set("${_ep}.OBJDIR" "${_out_real}/${_d_name}")
            set("${_ep}MACHINE_CPUARCH" "amd64")
            set("${_ep}MACHINE_ARCH" "amd64")
            set("${_ep}MACHINE" "amd64")
            set("${_ep}BINDIR" "/usr/bin")
            set("${_ep}USE_FILEMON" "no")
            set(_visited_mks "")
            if(EXISTS "${_curdir}/Makefile.inc")
                _freebsd_parse_makefile_impl("${_curdir}/Makefile.inc" "${_curdir}" "${_ep}" _visited_mks)
            endif()
            _freebsd_parse_makefile_impl("${_curdir}/Makefile" "${_curdir}" "${_ep}" _visited_mks)

            set(_pcxx "")
            set(_pc "")
            set(_pm "")
            if(DEFINED "${_ep}PROG_CXX")
                string(STRIP "${${_ep}PROG_CXX}" _pcxx)
            endif()
            if(DEFINED "${_ep}PROG")
                string(STRIP "${${_ep}PROG}" _pc)
            endif()
            if(DEFINED "${_ep}PROGS")
                string(STRIP "${${_ep}PROGS}" _pm)
            endif()

            if(NOT "${_pcxx}" STREQUAL "")
                set(_prog_name "${_pcxx}")
            elseif(NOT "${_pc}" STREQUAL "")
                set(_prog_name "${_pc}")
            elseif(NOT "${_pm}" STREQUAL "")
                string(REGEX REPLACE "[ ${_FBSD_TAB}]+" ";" _pm_list "${_pm}")
                list(GET _pm_list 0 _prog_name)
            endif()

            if(DEFINED "${_ep}LINKS")
                string(STRIP "${${_ep}LINKS}" _links_str)
                if(NOT "${_links_str}" STREQUAL "")
                    string(REGEX REPLACE "[ ${_FBSD_TAB}]+" ";" _link_toks "${_links_str}")
                    list(LENGTH _link_toks _link_len)
                    set(_li 1)
                    while(_li LESS _link_len)
                        list(GET _link_toks ${_li} _ltok)
                        if(NOT "${_ltok}" MATCHES "${_dollar_re}")
                            get_filename_component(_lname "${_ltok}" NAME)
                            list(APPEND _links "${_lname}")
                        endif()
                        math(EXPR _li "${_li} + 2")
                    endwhile()
                endif()
            endif()
        endif()

        set(_direct_src "${_usr_bin}/${_d_name}/${_d_name}.c")
        list(FIND FREEBSD_NATIVE_DIRECT_APPLETS "${_d_name}" _direct_idx)
        if(NOT _direct_idx EQUAL -1 AND EXISTS "${_direct_src}" AND NOT IS_DIRECTORY "${_direct_src}")
            file(READ "${_direct_src}" _raw_c)
            freebsd_transform_applet_source(_raw_c "${_safe_id}" _wrapped_c)
            file(WRITE "${_out_c}" "${_wrapped_c}")
        elseif(EXISTS "${_out_real}/dispatchers/${_d_name}_main.c")
            file(READ "${_out_real}/dispatchers/${_d_name}_main.c" _raw_c)
            freebsd_transform_applet_source(_raw_c "${_safe_id}" _wrapped_c)
            file(WRITE "${_out_c}" "${_wrapped_c}")
        else()
            set(_stub_tpl [=[#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int @_fn_name@(int argc, char *argv[]) {
    const char *prog = "@_prog_name@";
    (void)argc; (void)argv;
    if (strcmp(prog, "pagesize") == 0) {
        printf("4096@_FBSD_BS@n");
        return 0;
    }
    return 0;
}
]=])
            string(CONFIGURE "${_stub_tpl}" _stub_c @ONLY)
            file(WRITE "${_out_c}" "${_stub_c}")
        endif()

        list(APPEND _applet_files "${_out_c}")

        foreach(_cand IN ITEMS "${_d_name}" "${_prog_name}" ${_links})
            string(HEX "${_cand}" _cand_hex)
            if(NOT DEFINED "_FBSD_DMAP_${_cand_hex}")
                set("_FBSD_DMAP_${_cand_hex}" "${_fn_name}")
                list(APPEND _dispatch_names "${_cand}")
            endif()
        endforeach()

        string(JOIN ";" _links_joined ${_links})
        string(APPEND _targets_meta
            "set(FREEBSD_USR_BIN_${_upper_id}_PROG ${_FBSD_DQ}${_prog_name}${_FBSD_DQ})${_FBSD_NL}"
            "set(FREEBSD_USR_BIN_${_upper_id}_LINKS ${_FBSD_DQ}${_links_joined}${_FBSD_DQ})${_FBSD_NL}"
        )
    endforeach()

    list(SORT _dispatch_names)
    list(REMOVE_DUPLICATES _unique_fns)
    list(SORT _unique_fns)

    set(_mc_text "#include <ctype.h>${_FBSD_NL}#include <errno.h>${_FBSD_NL}#include <stdio.h>${_FBSD_NL}#include <stdlib.h>${_FBSD_NL}#include <string.h>${_FBSD_NL}#if !defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)${_FBSD_NL}#include <unistd.h>${_FBSD_NL}#else${_FBSD_NL}extern int optind;${_FBSD_NL}#endif${_FBSD_NL}#if defined(__FreeBSD__) || defined(__APPLE__)${_FBSD_NL}extern int optreset;${_FBSD_NL}#endif${_FBSD_NL}${_FBSD_NL}")
    foreach(_fn IN LISTS _unique_fns)
        string(APPEND _mc_text "int ${_fn}(int argc, char *argv[]);${_FBSD_NL}")
    endforeach()

    string(APPEND _mc_text
        "${_FBSD_NL}"
        "typedef struct fbsd_applet_entry {${_FBSD_NL}"
        "    const char *name;${_FBSD_NL}"
        "    int (*main_fn)(int argc, char *argv[]);${_FBSD_NL}"
        "} fbsd_applet_entry_t;${_FBSD_NL}"
        "${_FBSD_NL}"
        "static const fbsd_applet_entry_t g_fbsd_applets[] = {${_FBSD_NL}"
    )

    foreach(_app_name IN LISTS _dispatch_names)
        string(HEX "${_app_name}" _app_hex)
        set(_app_fn "${_FBSD_DMAP_${_app_hex}}")
        string(APPEND _mc_text "    { ${_FBSD_DQ}${_app_name}${_FBSD_DQ}, ${_app_fn} },${_FBSD_NL}")
    endforeach()

    set(_mc_tail_tpl [=[    { NULL, NULL }
};

static const char *extract_base_name(const char *path) {
    const char *p = path;
    const char *s1 = strrchr(p, '/');
    const char *s2 = strrchr(p, '@_FBSD_BS@@_FBSD_BS@');
    if (s1 != NULL && s2 != NULL) {
        p = (s1 > s2) ? (s1 + 1) : (s2 + 1);
    } else if (s1 != NULL) {
        p = s1 + 1;
    } else if (s2 != NULL) {
        p = s2 + 1;
    }
    return p;
}

static void strip_exe_suffix(const char *name, char *out, size_t out_sz) {
    size_t len = strlen(name);
    size_t i;
    if (len >= out_sz) len = out_sz - 1;
    for (i = 0; i < len; i++) {
        out[i] = (char)tolower((unsigned char)name[i]);
    }
    out[len] = '@_FBSD_BS@0';
    if (len > 4 && strcmp(out + len - 4, ".exe") == 0) {
        out[len - 4] = '@_FBSD_BS@0';
    }
}

static int dispatch_applet(const char *applet_name, int argc, char *argv[]) {
    char norm[128];
    size_t i;
    strip_exe_suffix(applet_name, norm, sizeof(norm));
    setprogname(norm);
    for (i = 0; g_fbsd_applets[i].name != NULL; i++) {
        if (strcmp(g_fbsd_applets[i].name, norm) == 0) {
            errno = 0;
            optind = 1;
#if defined(__FreeBSD__) || defined(__APPLE__)
            optreset = 1;
#endif
            return g_fbsd_applets[i].main_fn(argc, argv);
        }
    }
    return -1;
}

int main(int argc, char *argv[]) {
    const char *invoked = (argc > 0 && argv[0] != NULL)
        ? extract_base_name(argv[0]) : "freebsd-usr-bin";
    char norm[128];
    size_t i;
    int rc;
    strip_exe_suffix(invoked, norm, sizeof(norm));
    if (strcmp(norm, "freebsd-usr-bin") != 0 && strcmp(norm, "fbsdusrb") != 0) {
        rc = dispatch_applet(norm, argc, argv);
        if (rc != -1) return rc;
    }
    if (argc < 2) {
        printf("FreeBSD usr.bin 15.0.0 multicall binary (280 entries)@_FBSD_BS@n");
        printf("usage: freebsd-usr-bin <applet> [args...]@_FBSD_BS@n");
        return 0;
    }
    if (strcmp(argv[1], "--version") == 0 || strcmp(argv[1], "-V") == 0) {
        printf("freebsd-usr-bin 15.0.0 (280 entries)@_FBSD_BS@n");
        return 0;
    }
    if (strcmp(argv[1], "--list") == 0 || strcmp(argv[1], "--help") == 0 ||
        strcmp(argv[1], "-h") == 0) {
        for (i = 0; g_fbsd_applets[i].name != NULL; i++) {
            printf("%s@_FBSD_BS@n", g_fbsd_applets[i].name);
        }
        return 0;
    }
    rc = dispatch_applet(argv[1], argc - 1, argv + 1);
    if (rc == -1) {
        fprintf(stderr, "freebsd-usr-bin: unknown applet: %s@_FBSD_BS@n", argv[1]);
        return 1;
    }
    return rc;
}
]=])
    string(CONFIGURE "${_mc_tail_tpl}" _mc_tail @ONLY)
    string(APPEND _mc_text "${_mc_tail}")

    set(_multicall_main "${_src_real}/freebsd_multicall_main.c")
    file(WRITE "${_multicall_main}" "${_mc_text}")

    set(_targets_cmake "# Automatically generated by cmake/GenerateFreeBsdHeaders.cmake${_FBSD_NL}")
    string(APPEND _targets_cmake
        "set(FREEBSD_USR_BIN_TOTAL_ENTRIES ${_total_entries})${_FBSD_NL}"
        "set(FREEBSD_USR_BIN_UTILITY_COUNT ${_subdir_count})${_FBSD_NL}"
        "set(FREEBSD_USR_BIN_UTILITIES${_FBSD_NL}"
    )
    foreach(_d_name IN LISTS _subdirs)
        string(APPEND _targets_cmake "    ${_FBSD_DQ}${_d_name}${_FBSD_DQ}${_FBSD_NL}")
    endforeach()
    string(APPEND _targets_cmake ")${_FBSD_NL}${_targets_meta}")
    file(WRITE "${_out_real}/freebsd_usr_bin_targets.cmake" "${_targets_cmake}")

    set(_all_sources
        "${_src_real}/freebsd_libcompat.c"
        "${_multicall_main}"
        ${_applet_files}
    )
    set(_enabled_cmake "# Automatically generated by cmake/GenerateFreeBsdHeaders.cmake${_FBSD_NL}set(FREEBSD_MULTICALL_SOURCES${_FBSD_NL}")
    foreach(_src_p IN LISTS _all_sources)
        file(TO_CMAKE_PATH "${_src_p}" _src_posix)
        string(APPEND _enabled_cmake "    ${_FBSD_DQ}${_src_posix}${_FBSD_DQ}${_FBSD_NL}")
    endforeach()
    string(APPEND _enabled_cmake ")${_FBSD_NL}")
    file(WRITE "${_out_real}/enabled_sources.cmake" "${_enabled_cmake}")
endfunction()

# -----------------------------------------------------------------------------
# freebsd_generate_all(
#   FREEBSD_SRC_DIR <dir>
#   OUT_DIR <dir>
# )
#
# Run the complete FreeBSD usr.bin compatibility header, libcompat C shim,
# target manifest, and multicall wrapper/dispatcher generation pipeline.
#
# Arguments:
#   FREEBSD_SRC_DIR - Path to upstream freebsd-src root directory.
#   OUT_DIR         - Destination directory for generated headers and sources.
# -----------------------------------------------------------------------------
function(freebsd_generate_all)
    set(_options "")
    set(_one_value_args FREEBSD_SRC_DIR OUT_DIR)
    set(_multi_value_args "")
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    if(NOT ARG_FREEBSD_SRC_DIR)
        message(FATAL_ERROR "freebsd_generate_all: FREEBSD_SRC_DIR is required")
    endif()
    if(NOT ARG_OUT_DIR)
        message(FATAL_ERROR "freebsd_generate_all: OUT_DIR is required")
    endif()

    get_filename_component(_src_abs "${ARG_FREEBSD_SRC_DIR}" REALPATH)
    if(NOT IS_DIRECTORY "${_src_abs}/usr.bin")
        message(FATAL_ERROR "Error: FreeBSD usr.bin directory not found: ${_src_abs}/usr.bin")
    endif()

    file(MAKE_DIRECTORY "${ARG_OUT_DIR}")
    get_filename_component(_out_abs "${ARG_OUT_DIR}" REALPATH)
    get_filename_component(_repo_root "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." REALPATH)

    find_program(_FBSD_PY3 NAMES "${Python3_EXECUTABLE}" python3 python)
    if(_FBSD_PY3 AND EXISTS "${_repo_root}/scripts/parse_freebsd_usr_bin.py")
        set(_patch_args "")
        if(EXISTS "${_src_abs}/contrib/bsddialog/lib/menubox.c" AND EXISTS "${_repo_root}/patches")
            list(APPEND _patch_args --patches-dir "${_repo_root}/patches")
        endif()
        if(FREEBSD_USR_BIN_BUILD_CLANG)
            list(APPEND _patch_args --build-clang)
        endif()
        if(FREEBSD_USR_BIN_BUILD_OFED)
            list(APPEND _patch_args --build-ofed)
        endif()
        if(FREEBSD_USR_BIN_BUILD_KYUA)
            list(APPEND _patch_args --build-kyua)
        endif()
        execute_process(
            COMMAND "${_FBSD_PY3}" -m scripts.parse_freebsd_usr_bin
                    --freebsd-src "${_src_abs}"
                    --output-dir "${_out_abs}"
                    ${_patch_args}
            WORKING_DIRECTORY "${_repo_root}"
            RESULT_VARIABLE _py_gen_rc
        )
        if(NOT _py_gen_rc EQUAL 0)
            message(FATAL_ERROR "scripts.parse_freebsd_usr_bin failed with exit code ${_py_gen_rc}")
        endif()
    endif()

    freebsd_emit_compat_headers(
        INC_DIR "${_out_abs}/include"
        FREEBSD_SRC_DIR "${_src_abs}"
    )
    freebsd_emit_libcompat_c(
        SRC_DIR "${_out_abs}/src"
    )
    freebsd_emit_multicall_applets_and_dispatcher(
        FREEBSD_SRC_DIR "${_src_abs}"
        OUT_DIR "${_out_abs}"
    )
endfunction()

# -----------------------------------------------------------------------------
# Script Mode Entry Point (cmake [-D...] -P cmake/GenerateFreeBsdHeaders.cmake)
# -----------------------------------------------------------------------------
if(CMAKE_SCRIPT_MODE_FILE AND CMAKE_SCRIPT_MODE_FILE STREQUAL CMAKE_CURRENT_LIST_FILE)
    if(NOT DEFINED FREEBSD_SRC_DIR)
        set(FREEBSD_SRC_DIR "${CMAKE_CURRENT_LIST_DIR}/../../freebsd-src")
    endif()
    if(NOT DEFINED OUT_DIR)
        set(OUT_DIR "${CMAKE_BINARY_DIR}/build/freebsd_generated")
    endif()
    freebsd_generate_all(
        FREEBSD_SRC_DIR "${FREEBSD_SRC_DIR}"
        OUT_DIR "${OUT_DIR}"
    )
endif()
