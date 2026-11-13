freebsd-usr-bin-windows
=======================

[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT%20OR%20CC0--1.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
![Doc Coverage](https://img.shields.io/badge/doc%20coverage-100%25-brightgreen)
![Test Coverage](https://img.shields.io/badge/test%20coverage-100%25-brightgreen)

Native Windows (MSVC `X64`, `X86`, `ARM64`) and 32-bit Protected-Mode DOS (`OpenWatcom v2` / `DOS32A`) per-binary CMake build system, true Section 3 `SHARED`/`STATIC` backing library suite, and automated GitHub Releases packager for all 280 entries in FreeBSD `usr.bin` (`../freebsd-src/usr.bin`), powered by [`auto-win-msvc`](https://github.com/SamuelMarks/auto-win-msvc).

## Highlights

- **Zero Upstream Modifications**: Compiles directly from `../freebsd-src` without editing a single `.c` or `.h` file (`git -C ../freebsd-src diff --exit-code` verified in CI and `pytest`).
- **Zero In-Repo C/H Files**: Enforced by the `forbid-c-headers-and-sources` pre-commit hook. Reusable POSIX/BSD/FreeBSD polyfills live in `../auto-win-msvc`, utility-specific adjustments use declarative `patches/*.patch` staged into `${CMAKE_BINARY_DIR}/freebsd_generated/staged_src`, and generated headers/dispatchers live exclusively under `${CMAKE_BINARY_DIR}/freebsd_generated`.
- **Out-of-Tree Per-Binary `CMakeLists.txt`**:
  - Configure-time generation emits `${CMAKE_BINARY_DIR}/freebsd_generated/per_binary/<prog>/CMakeLists.txt` for every concrete `usr.bin` executable (`286` subprojects).
  - Each generated `CMakeLists.txt` works **both** via `add_subdirectory()` from the root `CMakeLists.txt` and as an isolated standalone CMake project (`cmake -S build/freebsd_generated/per_binary/printf -B build_printf`) that builds only `<prog>`'s required Section 3 backing libraries.
- **Section 3 Libraries vs. Section 1 Executables (`printf(3)` vs. `printf(1)`)**:
  - Standard C Section 3 calls such as `printf(3)` are provided by MSVC UCRT / OpenWatcom CRT + `auto-win-msvc`, whereas `usr.bin/printf` builds the Section 1 `printf(1)` executable (`printf.exe` + `freebsd-usr-bin printf`).
  - True FreeBSD Section 3 backing libraries (`libutil`, `libxo`, `libmd`, `libsbuf`, `libz`, `libbz2`, `libbsdxml`, `liblzma`, `libzstd`, `libarchive`, `libmagic`, `libelftc`, `libfetch`, `libcurses`, `libedit`, `libbsddialog`, `libsys`, etc.) are built by `cmake/FreeBsdInternalLibs.cmake` as `SHARED` libraries (`.dll` + `.lib` + SDK headers) on Windows/Unix (`FREEBSD_SECTION3_SHARED=ON`) and `STATIC` libraries (`.lib`) on 32-bit DOS.
- **Automated GitHub Releases (`v*` Tags)**:
  - Publishes multi-architecture Windows (`X64`, `X86`, `ARM64` `.zip`, `.msi`, `-setup.exe`, `.exe`) and 32-bit DOS (`dos32` `.zip`, `.exe`) suite bundles, `freebsd-usr-bin-<ver>-section3-sdk.zip`, per-binary `<prog>-<ver>-windows.zip` and `<prog>-<ver>-dos32.zip` archives, and `SHA256SUMS.txt` via `scripts.package_release_assets`.

## Quick Start

### Full Suite + Section 3 Libraries + Standalone Per-Binary Targets

```sh
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --parallel
ctest --test-dir build -C Release --output-on-failure
```

### Building a Single Utility Standalone (`per_binary/<prog>/CMakeLists.txt`)

```sh
python3 -m scripts.parse_freebsd_usr_bin --output-dir build/freebsd_generated
cmake -S build/freebsd_generated/per_binary/printf -B build_printf -DCMAKE_BUILD_TYPE=Release
cmake --build build_printf --config Release
```
