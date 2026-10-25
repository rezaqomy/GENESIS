import pytest


@pytest.fixture(autouse=True)
def offline_cognition(monkeypatch):
    # Simulation/API tests should never depend on a running model server.
    monkeypatch.setenv("GENESIS_COGNITION", "0")
