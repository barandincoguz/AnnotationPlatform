from pathlib import Path


SCRIPT = (Path(__file__).resolve().parents[1] / "deploy_hf.sh").read_text()


def test_deploy_uses_historyless_orphan_commit_and_safe_lease():
    assert "checkout --orphan" in SCRIPT
    assert "--force-with-lease" in SCRIPT
    assert "git push -f " not in SCRIPT


def test_deploy_stages_an_explicit_production_whitelist():
    assert "deploy_paths=(" in SCRIPT
    assert '"backend"' in SCRIPT
    assert '\n  "frontend"\n' not in SCRIPT
    assert '"frontend/src"' in SCRIPT
    assert '"frontend/package.json"' in SCRIPT
    assert '"Dockerfile"' in SCRIPT
    assert "add -- \"${deploy_paths[@]}\"" in SCRIPT
    assert "git rm -r --quiet audit/" not in SCRIPT


def test_deploy_excludes_test_fixture_and_debug_sources_from_space_tree():
    assert "deploy_excludes=(" in SCRIPT
    for forbidden in (
        "backend/tests",
        "frontend/e2e",
        "frontend/src/test",
        "frontend/src/**/*.test.ts",
        "frontend/src/**/*.test.tsx",
    ):
        assert forbidden in SCRIPT
    assert "ls-files -- \"${deploy_excludes[@]}\"" in SCRIPT
    assert "Refusing deployment: test or fixture files remain" in SCRIPT
