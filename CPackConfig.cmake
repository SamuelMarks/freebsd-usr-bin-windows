# =============================================================================
# CPackConfig.cmake - Binary Package Configuration for FreeBSD usr.bin Windows & DOS
#
# Configures CPack to produce standalone portable ZIP archives, NSIS (.exe),
# and WiX (.msi) Windows installers containing the compiled FreeBSD usr.bin
# executables and licenses.
# =============================================================================

set(CPACK_PACKAGE_NAME "freebsd-usr-bin")
set(CPACK_PACKAGE_VENDOR "The FreeBSD Project")
set(CPACK_PACKAGE_VERSION "15.0.0")
set(CPACK_PACKAGE_VERSION_MAJOR "15")
set(CPACK_PACKAGE_VERSION_MINOR "0")
set(CPACK_PACKAGE_VERSION_PATCH "0")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "FreeBSD usr.bin command-line utilities for native Windows (MSVC) and 32-bit DOS (OpenWatcom).")
set(CPACK_PACKAGE_HOMEPAGE_URL "https://www.freebsd.org/")
set(CPACK_PACKAGE_CONTACT "Samuel Marks")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "freebsd-usr-bin")
set(CPACK_GENERATOR "ZIP;NSIS;WIX")

set(_cpack_license_src "")
if(DEFINED FREEBSD_SRC_DIR AND EXISTS "${FREEBSD_SRC_DIR}/COPYRIGHT")
    set(_cpack_license_src "${FREEBSD_SRC_DIR}/COPYRIGHT")
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT")
    set(_cpack_license_src "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT")
endif()

if(_cpack_license_src)
    if(DEFINED CMAKE_CURRENT_BINARY_DIR AND NOT "${CMAKE_CURRENT_BINARY_DIR}" STREQUAL "${CMAKE_CURRENT_SOURCE_DIR}")
        configure_file("${_cpack_license_src}" "${CMAKE_CURRENT_BINARY_DIR}/LICENSE.txt" COPYONLY)
        set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_BINARY_DIR}/LICENSE.txt")
    else()
        set(CPACK_RESOURCE_FILE_LICENSE "${_cpack_license_src}")
    endif()
endif()

set(CPACK_NSIS_DISPLAY_NAME "FreeBSD usr.bin for Windows")
set(CPACK_NSIS_PACKAGE_NAME "FreeBSD usr.bin for Windows")
set(CPACK_NSIS_MODIFY_PATH ON)

set(CPACK_WIX_UPGRADE_GUID "8F3C9A21-6E4B-4D2C-9A75-1C8E5B3D4072")
