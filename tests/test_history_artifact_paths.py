"""
test_history_artifact_paths.py
==============================

Provenance-path representation for ArtifactBinding (OSSF-GW-005-D1).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path, PureWindowsPath

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.history.artifact_paths import (
    _normalize_external_windows_path,
    recorded_artifact_path,
)
from core.history.errors import ArtifactPathRepresentationError


def test_repository_relative_path_preserved(tmp_path):
    repo = tmp_path / "repo"
    artifact = repo / "output" / "site_report.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("x", encoding="utf-8")
    assert recorded_artifact_path(artifact, repository_root=repo) == (
        "output/site_report.txt"
    )


def test_nested_repository_path_preserved(tmp_path):
    repo = tmp_path / "repo"
    artifact = repo / "output" / "archive" / "run-1" / "site_report.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("x", encoding="utf-8")
    assert recorded_artifact_path(artifact, repository_root=repo) == (
        "output/archive/run-1/site_report.txt"
    )


def test_external_posix_path_tagged(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "run-1" / "site_report.txt"
    external.parent.mkdir(parents=True)
    external.write_text("x", encoding="utf-8")
    recorded = recorded_artifact_path(external, repository_root=repo)
    assert recorded.startswith("external/")
    assert recorded.endswith("run-1/site_report.txt")
    assert "\\" not in recorded
    assert not recorded.startswith("external//")


def test_same_basename_external_paths_distinguishable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    a = tmp_path / "run-a" / "results.json"
    b = tmp_path / "run-b" / "results.json"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    ra = recorded_artifact_path(a, repository_root=repo)
    rb = recorded_artifact_path(b, repository_root=repo)
    assert ra != rb
    assert ra.endswith("run-a/results.json")
    assert rb.endswith("run-b/results.json")


def test_repeated_normalization_deterministic(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "x" / "y.txt"
    external.parent.mkdir()
    external.write_text("z", encoding="utf-8")
    first = recorded_artifact_path(external, repository_root=repo)
    second = recorded_artifact_path(external, repository_root=repo)
    assert first == second


def test_separators_normalized_forward_slash(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "nested" / "path" / "file.txt"
    external.parent.mkdir(parents=True)
    external.write_text("z", encoding="utf-8")
    recorded = recorded_artifact_path(external, repository_root=repo)
    assert "\\" not in recorded
    assert "/" in recorded


def test_windows_drive_lexical_form():
    recorded = _normalize_external_windows_path(
        PureWindowsPath(r"C:\runs\a\report.txt")
    )
    assert recorded == "external/C/runs/a/report.txt"


def test_unc_lexical_form():
    recorded = _normalize_external_windows_path(
        PureWindowsPath(r"\\server\share\runs\a\report.txt")
    )
    assert recorded == "external/UNC/server/share/runs/a/report.txt"


def test_incomplete_unc_rejected():
    with pytest.raises(ArtifactPathRepresentationError, match="UNC"):
        _normalize_external_windows_path(PureWindowsPath(r"\\server"))
    with pytest.raises(ArtifactPathRepresentationError):
        _normalize_external_windows_path(PureWindowsPath(r"\\server\share"))


def test_repository_root_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ArtifactPathRepresentationError, match="repository root"):
        recorded_artifact_path(repo, repository_root=repo)


def test_common_prefix_sibling_not_inside_repo(tmp_path):
    repo = tmp_path / "repo"
    other = tmp_path / "repository-other"
    repo.mkdir()
    other.mkdir()
    inside = repo / "output" / "report.txt"
    outside = other / "output" / "report.txt"
    inside.parent.mkdir()
    outside.parent.mkdir()
    inside.write_text("a", encoding="utf-8")
    outside.write_text("b", encoding="utf-8")
    assert recorded_artifact_path(inside, repository_root=repo) == (
        "output/report.txt"
    )
    out_rec = recorded_artifact_path(outside, repository_root=repo)
    assert out_rec.startswith("external/")
    assert "repository-other" in out_rec


def test_dotdot_producer_path_resolves_before_representation(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = tmp_path / "real" / "file.txt"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    # Lexical path with .. that resolves outside the repo.
    lexical = repo / "output" / ".." / ".." / "real" / "file.txt"
    recorded = recorded_artifact_path(lexical, repository_root=repo)
    assert recorded.startswith("external/")
    assert recorded.endswith("real/file.txt")


def test_symlink_inside_repo_pointing_outside_is_external(tmp_path):
    repo = tmp_path / "repo"
    outside_dir = tmp_path / "outside"
    repo.mkdir()
    outside_dir.mkdir()
    target = outside_dir / "file.txt"
    target.write_text("x", encoding="utf-8")
    link = repo / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks not supported")
    recorded = recorded_artifact_path(link, repository_root=repo)
    assert recorded.startswith("external/")


def test_symlink_outside_repo_pointing_inside_is_internal(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    target = repo / "output" / "file.txt"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    link = outside / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks not supported")
    recorded = recorded_artifact_path(link, repository_root=repo)
    assert recorded == "output/file.txt"


def test_empty_path_rejected(tmp_path):
    with pytest.raises(ArtifactPathRepresentationError):
        recorded_artifact_path("", repository_root=tmp_path)
    with pytest.raises(ArtifactPathRepresentationError):
        recorded_artifact_path(tmp_path / "a.txt", repository_root="")


def test_redundant_dot_segments_collapsed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact = repo / "output" / "report.txt"
    artifact.parent.mkdir()
    artifact.write_text("x", encoding="utf-8")
    lexical = repo / "output" / "." / "report.txt"
    assert recorded_artifact_path(lexical, repository_root=repo) == (
        "output/report.txt"
    )


def test_external_passes_artifact_binding_guard():
    from core.history.models import ArtifactBinding

    for path in (
        "external/tmp/run/report.txt",
        "external/C/runs/report.txt",
        "external/UNC/server/share/report.txt",
    ):
        binding = ArtifactBinding(
            artifact_type="report_text",
            relative_path=path,
            sha256="a" * 16,
        )
        assert binding.relative_path == path
