# =============================================================================
# CPackSourceConfig.cmake - Source Archive Configuration for FreeBSD usr.bin Windows
# =============================================================================

set(CPACK_SOURCE_GENERATOR "ZIP;TGZ")
set(CPACK_SOURCE_PACKAGE_FILE_NAME "freebsd-usr-bin-15.0.0-src")
set(CPACK_SOURCE_IGNORE_FILES
    "/\.git/"
    "/build.*/"
    "/\.vscode/"
    "/\.idea/"
    "/__pycache__/"
    "/\.DS_Store"
)
