"""Metas da Missão 01 e caminhos compartilhados. Sem MySQL."""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_WALK_CSV = BACKEND_ROOT / "datasets" / "sample_walk.csv"
WALKS_DIR = BACKEND_ROOT / "tests" / "fixtures" / "walks"

# A1–A3. A meta agregada de 3% é desejável e não bloqueia.
TARGETS = {
    "A1_per_walk_error_pct": 5.0,
    "A2_phantoms_max": 2,
    "A3_sample_walk_steps": 20,
    "A3_sample_walk_tolerance": 1,
    "event_match_window_s": 0.250,
}


@pytest.fixture(autouse=True)
def _isolated_db_pool():
    """Nenhuma sessão do teste anterior volta para o seguinte."""
    from datasets.ManagerDatabase import drain_pool

    drain_pool()
    yield
    drain_pool()


@pytest.fixture(autouse=True)
def _reset_editor_attempts():
    from api.editor_auth import reset_attempts, set_attempt_limit

    reset_attempts()
    set_attempt_limit(8)
    yield
    reset_attempts()
    set_attempt_limit(8)


@pytest.fixture
def detector():
    from pdr.steps import PeakStepDetector

    return PeakStepDetector()


@pytest.fixture
def step_config():
    from pdr.steps import StepDetectorConfig

    return StepDetectorConfig()
