from pathlib import Path


CONFIG = (
    Path(__file__).resolve().parents[1] / "frontend" / "playwright.config.ts"
).read_text()
PACKAGE = (
    Path(__file__).resolve().parents[1] / "frontend" / "package.json"
).read_text()
RUNNER = (
    Path(__file__).resolve().parents[1] / "frontend" / "scripts" / "run-e2e.sh"
).read_text()


def test_playwright_never_reuses_a_server_that_may_be_production():
    assert "reuseExistingServer: !process.env.CI" not in CONFIG
    assert CONFIG.count("reuseExistingServer: false") == 2


def test_playwright_defaults_to_per_run_ports_and_temporary_e2e_data():
    assert "anotasyon-e2e-${E2E_RUN_ID}" in CONFIG
    assert "E2E_BACKEND_PORT ?? '8002'" not in CONFIG
    assert "E2E_FRONTEND_PORT ?? '5175'" not in CONFIG
    assert '"e2e": "./scripts/run-e2e.sh"' in PACKAGE
    assert 'e2e_run_id="${E2E_RUN_ID:-$$}"' in RUNNER
    assert "E2E_DATA_DIR" in RUNNER
    assert "E2E_BACKEND_PORT" in RUNNER
    assert "E2E_FRONTEND_PORT" in RUNNER
