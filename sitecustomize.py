"""Project-local Python startup customizations.

Coverage 7.13 walks parent directories of every ``sys.path`` entry while
detecting third-party locations. In sandboxed Windows runs, that can raise
``PermissionError`` for user profile directories before pytest collection
starts. Treat those unreadable directories as non-importable so the normal
``--cov=src`` test command can proceed.
"""

from __future__ import annotations


def _patch_coverage_directory_probe() -> None:
    try:
        import coverage.inorout as coverage_inorout
    except Exception:
        return

    original = getattr(coverage_inorout, "_analyze_directory", None)
    detail_cls = getattr(coverage_inorout, "DirectoryDetail", None)
    if original is None or detail_cls is None:
        return
    if getattr(original, "_stock_auto_permission_patch", False):
        return

    def _safe_analyze_directory(directory: str):
        try:
            return original(directory)
        except PermissionError:
            return detail_cls(exists=False, venv=None)

    _safe_analyze_directory._stock_auto_permission_patch = True
    coverage_inorout._analyze_directory = _safe_analyze_directory


_patch_coverage_directory_probe()
