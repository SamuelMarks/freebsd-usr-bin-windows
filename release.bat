@echo off
REM ===========================================================================
REM release.bat - Native Windows MSVC Build, Test & Packaging Script
REM Usage: release.bat [version] [X64|X86|ARM64]
REM ===========================================================================

setlocal enabledelayedexpansion

set FREEBSD_REF=%~1
if "%FREEBSD_REF%"=="" set FREEBSD_REF=15.0.0

set TARGET_ARCH=%~2
if "%TARGET_ARCH%"=="" set TARGET_ARCH=X64

echo =======================================================
echo Building FreeBSD usr.bin Windows Release (%FREEBSD_REF% - %TARGET_ARCH%)
echo =======================================================

set CMAKE_EXTRA_ARGS=
if /i "%TARGET_ARCH%"=="X86" set CMAKE_EXTRA_ARGS=-A Win32
if /i "%TARGET_ARCH%"=="X64" set CMAKE_EXTRA_ARGS=-A x64
if /i "%TARGET_ARCH%"=="ARM64" set CMAKE_EXTRA_ARGS=-A ARM64

if exist ..\auto-win-msvc\CMakeLists.txt (
    echo Using local ..\auto-win-msvc repository...
    for %%I in ("..\auto-win-msvc") do set "AWM_ABS=%%~fI"
    set "AWM_FWD=!AWM_ABS:\=/!"
    set CMAKE_EXTRA_ARGS=!CMAKE_EXTRA_ARGS! "-DFETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC=!AWM_FWD!"
) else if exist auto-win-msvc\CMakeLists.txt (
    for %%I in ("auto-win-msvc") do set "AWM_ABS=%%~fI"
    set "AWM_FWD=!AWM_ABS:\=/!"
    set CMAKE_EXTRA_ARGS=!CMAKE_EXTRA_ARGS! "-DFETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC=!AWM_FWD!"
)

set BUILD_DIR=build_release_%TARGET_ARCH%
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%

echo Configuring with CMake...
cmake -B %BUILD_DIR% -S . -DCMAKE_BUILD_TYPE=Release !CMAKE_EXTRA_ARGS!
if errorlevel 1 exit /b 1

echo Compiling FreeBSD usr.bin Release (Section 3 DLLs + Per-Binary + Multicall)...
cmake --build %BUILD_DIR% --config Release --parallel
if errorlevel 1 exit /b 1

if /i not "%TARGET_ARCH%"=="ARM64" (
    echo Testing FreeBSD usr.bin...
    ctest --test-dir %BUILD_DIR% -C Release --output-on-failure
    if errorlevel 1 exit /b 1
)

echo Packaging suite installers with CPack...
cd %BUILD_DIR%
cpack -C Release -G ZIP -D CPACK_PACKAGE_FILE_NAME=freebsd-usr-bin-%FREEBSD_REF%-%TARGET_ARCH%
if /i not "%TARGET_ARCH%"=="ARM64" (
    cpack -C Release -G NSIS -D CPACK_PACKAGE_FILE_NAME=freebsd-usr-bin-%FREEBSD_REF%-%TARGET_ARCH%-setup
)
cpack -C Release -G WIX -D CPACK_PACKAGE_FILE_NAME=freebsd-usr-bin-%FREEBSD_REF%-%TARGET_ARCH%
if exist bin\Release\freebsd-usr-bin.exe copy /y bin\Release\freebsd-usr-bin.exe freebsd-usr-bin-%FREEBSD_REF%-%TARGET_ARCH%.exe >nul
if exist bin\freebsd-usr-bin.exe copy /y bin\freebsd-usr-bin.exe freebsd-usr-bin-%FREEBSD_REF%-%TARGET_ARCH%.exe >nul
cd ..

echo Packaging per-binary archives and Section 3 SDK...
set WIN_FLAG=--win-x64
if /i "%TARGET_ARCH%"=="X86" set WIN_FLAG=--win-x86
if /i "%TARGET_ARCH%"=="ARM64" set WIN_FLAG=--win-arm64
python -m scripts.package_release_assets --version %FREEBSD_REF% --output-dir release_assets %WIN_FLAG% %BUILD_DIR% --per-binary-cmake-dir %BUILD_DIR%\freebsd_generated\per_binary

echo Build and packaging complete!
