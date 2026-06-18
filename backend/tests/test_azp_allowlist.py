"""The azp (authorized-party) allow-list: additional first-party client ids
(e.g. the native desktop app) are accepted via KEYCLOAK_ALLOWED_AZP, without
weakening the single-client default."""
from orchestrator.auth import allowed_azp_values


def test_default_is_primary_only(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_ALLOWED_AZP", raising=False)
    assert allowed_azp_values("astral-frontend") == {"astral-frontend"}


def test_extras_are_added(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ALLOWED_AZP", "astral-desktop, astral-mobile ")
    assert allowed_azp_values("astral-frontend") == {
        "astral-frontend", "astral-desktop", "astral-mobile"}


def test_empty_primary(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ALLOWED_AZP", "astral-desktop")
    assert allowed_azp_values(None) == {"astral-desktop"}


def test_blank_entries_ignored(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ALLOWED_AZP", " , ,astral-desktop, ")
    assert allowed_azp_values("astral-frontend") == {"astral-frontend", "astral-desktop"}
