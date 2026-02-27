from __future__ import annotations

from pathlib import Path


def test_formula_does_not_reinstall_moved_project_files() -> None:
    formula_path = Path(__file__).resolve().parents[1] / "Formula" / "moonshine-flow.rb"
    content = formula_path.read_text(encoding="utf-8")

    assert 'libexec.install buildpath.children' in content

    # Homebrew Pathname#install moves files, so these must not be reinstalled.
    assert 'libexec.install buildpath/"README.md"' not in content
    assert 'libexec.install buildpath/"pyproject.toml"' not in content
    assert 'libexec.install buildpath/"uv.lock"' not in content


def test_formula_sets_setuptools_scm_version_for_stable_builds() -> None:
    formula_path = Path(__file__).resolve().parents[1] / "Formula" / "moonshine-flow.rb"
    content = formula_path.read_text(encoding="utf-8")

    assert "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MOONSHINE_FLOW" in content


def test_formula_installs_mflow_alias_wrapper() -> None:
    formula_path = Path(__file__).resolve().parents[1] / "Formula" / "moonshine-flow.rb"
    content = formula_path.read_text(encoding="utf-8")

    assert "%w[moonshine-flow mflow].each do |command_name|" in content
    assert 'shell_output("#{bin}/mflow --help")' in content
