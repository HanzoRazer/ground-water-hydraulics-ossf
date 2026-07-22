"""
core/history/artifact_paths.py
==============================

Deterministic provenance-path representation for CaseHistory artifact
bindings (OSSF-GW-005-D1).

Records distinguishable location labels for ``ArtifactBinding.relative_path``.
Observational only — does not open, authorize, or dereference filesystem
locations. Traversal policy for externally authored history strings remains
GW-005-P1 (ADJUDICATE).
"""

from __future__ import annotations

from pathlib import Path, PurePath, PureWindowsPath
from typing import Tuple, Union

from .errors import ArtifactPathRepresentationError

PathLike = Union[str, Path, PurePath]


def _join_recorded_components(parts: Tuple[str, ...]) -> str:
    """Join provenance components with forward slashes (no leading slash)."""
    cleaned = [p for p in parts if p and p not in (".",)]
    if not cleaned:
        raise ArtifactPathRepresentationError(
            "recorded artifact path has no location components"
        )
    return "/".join(cleaned)


def _normalized_absolute_path(path: Path) -> Path:
    """Resolve for containment comparison (follow symlinks; no create)."""
    if not str(path).strip():
        raise ArtifactPathRepresentationError("artifact path must be non-empty")
    return path.expanduser().resolve(strict=False)


def _posix_external_components(abs_path: Path) -> Tuple[str, ...]:
    """Strip POSIX root markers; return remaining location components."""
    parts = abs_path.parts
    if not parts:
        raise ArtifactPathRepresentationError(
            f"cannot derive external components from {abs_path!r}"
        )
    # Drop leading '/' (or drive root on odd hosts).
    if parts[0] in ("/", "\\"):
        rest = parts[1:]
    else:
        rest = parts
    if not rest:
        raise ArtifactPathRepresentationError(
            f"external path has no components after root: {abs_path!r}"
        )
    return tuple(rest)


def _normalize_external_windows_path(path: PureWindowsPath) -> str:
    """Lexical Windows / UNC → ``external/...`` (no host Path.resolve).

    Examples
    --------
    ``C:\\runs\\a\\report.txt`` → ``external/C/runs/a/report.txt``
    ``\\\\server\\share\\runs\\a\\report.txt`` →
    ``external/UNC/server/share/runs/a/report.txt``
    """
    if not isinstance(path, PureWindowsPath):
        path = PureWindowsPath(path)

    drive = path.drive
    # Incomplete UNC like ``\\server`` (no share).
    if drive.startswith("\\\\") and path.root == "":
        raise ArtifactPathRepresentationError(
            f"incomplete UNC path (missing share): {path!r}"
        )

    # UNC with share: drive is ``\\server\share``.
    if drive.startswith("\\\\"):
        unc_body = drive.lstrip("\\").replace("\\", "/")
        server_share = [c for c in unc_body.split("/") if c]
        if len(server_share) < 2:
            raise ArtifactPathRepresentationError(
                f"incomplete UNC path (need server and share): {path!r}"
            )
        # PureWindowsPath parts: ('\\\\server\\share\\', 'folder', 'file')
        if len(path.parts) <= 1:
            raise ArtifactPathRepresentationError(
                f"UNC path has no artifact file component: {path!r}"
            )
        after = [p.rstrip("\\/") for p in path.parts[1:] if p and p not in (".",)]
        if not after:
            raise ArtifactPathRepresentationError(
                f"UNC path has no artifact file component: {path!r}"
            )
        return _join_recorded_components(
            ("external", "UNC", server_share[0], server_share[1], *after)
        )

    # Drive letter paths: ``C:\runs\a\report.txt``.
    if len(drive) >= 2 and drive[1] == ":":
        letter = drive[0].upper()
        after = [p for p in path.parts[1:] if p and p not in (".", "\\", "/")]
        if not after:
            raise ArtifactPathRepresentationError(
                f"Windows path has no artifact file component: {path!r}"
            )
        return _join_recorded_components(("external", letter, *after))

    raise ArtifactPathRepresentationError(
        f"unsupported Windows path form: {path!r}"
    )


def _recorded_external_label(artifact: Path | PureWindowsPath) -> str:
    """Label an artifact known to lie outside ``repository_root``.

    On Windows hosts, ``Path`` is a ``PureWindowsPath`` subclass. Routing those
    through POSIX component stripping leaks drive / ``\\`` markers into the
    recorded label (and can trip ``ArtifactBinding`` absolute-path guards).
    """
    if isinstance(artifact, PureWindowsPath):
        return _normalize_external_windows_path(PureWindowsPath(artifact))
    return _join_recorded_components(
        ("external", *_posix_external_components(Path(artifact)))
    )


def recorded_artifact_path(
    path: PathLike,
    *,
    repository_root: PathLike,
) -> str:
    """Return the canonical provenance representation for an artifact path.

    * Inside the repository → repository-relative path (``/`` separators).
    * Outside the repository → ``external/<normalized location components>``.

    Uses ``Path.resolve(strict=False)`` for containment (symlink targets
    followed). Does not open the artifact for reading.
    """
    if repository_root is None or not str(repository_root).strip():
        raise ArtifactPathRepresentationError(
            "repository_root must be a non-empty path"
        )
    if path is None or not str(path).strip():
        raise ArtifactPathRepresentationError("artifact path must be non-empty")

    # Lexical Windows / UNC inputs on non-Windows hosts: do not force through
    # POSIX Path.resolve (which would mis-parse drive / UNC strings).
    if isinstance(path, PureWindowsPath) and not isinstance(path, Path):
        return _normalize_external_windows_path(path)

    artifact = _normalized_absolute_path(Path(path))
    repo = _normalized_absolute_path(Path(repository_root))

    if artifact == repo:
        raise ArtifactPathRepresentationError(
            "repository root is not a valid artifact-file binding"
        )

    # Existence-aware directory rejection (when the path exists).
    try:
        if artifact.exists() and artifact.is_dir():
            raise ArtifactPathRepresentationError(
                f"directory is not a valid artifact-file binding: {artifact}"
            )
    except OSError:
        # Representation remains observational if metadata is unavailable.
        pass

    try:
        rel = artifact.relative_to(repo)
    except ValueError:
        return _recorded_external_label(artifact)

    recorded = rel.as_posix()
    # Strip redundant ./ and trailing separators already handled by as_posix
    # of a relative path; drop a lone "." if somehow produced.
    if recorded in ("", "."):
        raise ArtifactPathRepresentationError(
            "recorded artifact path collapsed to empty"
        )
    while recorded.startswith("./"):
        recorded = recorded[2:]
    if recorded.endswith("/"):
        recorded = recorded.rstrip("/")
    if not recorded or recorded == ".":
        raise ArtifactPathRepresentationError(
            "recorded artifact path collapsed to empty"
        )
    return recorded


__all__ = [
    "recorded_artifact_path",
]
