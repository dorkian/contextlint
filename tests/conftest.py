import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = ROOT / "benchmarks" / "fixtures" / "bloated"


@pytest.fixture(scope="session")
def bloated_report():
    from contextlint.audit import run_audit

    return run_audit(str(FIXTURE), include_global=False, use_usage=False)


@pytest.fixture
def fixture_path() -> Path:
    return FIXTURE
