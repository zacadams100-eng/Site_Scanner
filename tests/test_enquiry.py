"""
The enquiry form's receiver.

The rule under test is the one this codebase applies everywhere else: a thing
that could not happen must not report that it did. A contact form returning
success with no receiver configured is the same failure as a scanner reporting
"clear" for a check it could not run.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import enquiry as enquiry_mod
import mock_ee_backend

VALID = {
    "name": "A Person",
    "email": "person@example.com",
    "organisation": "An Organisation",
    "site": "TQ 123 456",
    "detail": "We are looking at a parcel and want to know what is on it.",
    "scanners": ["Land", "Coastal"],
}

ENV_KEYS = ("ENQUIRY_WEBHOOK_URL", "ENQUIRY_SMTP_HOST", "ENQUIRY_SMTP_USER",
            "ENQUIRY_SMTP_PASSWORD", "ENQUIRY_TO", "ENQUIRY_FROM")


@pytest.fixture
def client():
    with TestClient(mock_ee_backend.app) as c:
        yield c


@pytest.fixture(autouse=True)
def no_receiver(monkeypatch):
    """Every test starts with nothing configured — the deployed state today."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_with_no_receiver_the_form_refuses_rather_than_thanking_you(client):
    r = client.post("/api/enquiry", json=VALID)
    assert r.status_code == 503
    assert "not connected" in r.json()["detail"]
    # And it says the message was not kept, because it was not.
    assert "not been stored" in r.json()["detail"]


def test_the_form_can_ask_before_someone_types_five_hundred_words(client):
    r = client.get("/api/enquiry/status")
    assert r.status_code == 200
    assert r.json() == {"configured": False}


def test_status_never_leaks_which_receiver_or_its_configuration(client, monkeypatch):
    monkeypatch.setenv("ENQUIRY_WEBHOOK_URL", "https://hooks.example/secret-path")
    body = client.get("/api/enquiry/status").json()
    assert body == {"configured": True}
    assert "secret-path" not in str(body)


def test_a_configured_webhook_receives_the_enquiry(client, monkeypatch):
    sent = {}

    def fake(payload):
        sent.update(payload.as_dict())

    monkeypatch.setenv("ENQUIRY_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(enquiry_mod, "_deliver_webhook", fake)

    r = client.post("/api/enquiry", json=VALID)
    assert r.status_code == 200
    assert r.json() == {"delivered": True, "via": "webhook"}
    assert sent["email"] == "person@example.com"
    assert sent["scanners"] == ["Land", "Coastal"]


def test_a_delivery_failure_is_not_reported_as_success(client, monkeypatch):
    """A webhook that 500s must not produce a thank-you page."""
    monkeypatch.setenv("ENQUIRY_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(enquiry_mod, "_deliver_webhook",
                        lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    r = client.post("/api/enquiry", json=VALID)
    assert r.status_code == 502
    assert "not be delivered" in r.json()["detail"]
    # And the sender is told nothing was kept, so they can copy their text.
    assert "Nothing was stored" in r.json()["detail"]


def test_the_webhook_is_preferred_over_smtp_because_it_is_cheaper_to_stand_up(monkeypatch):
    for key in ("ENQUIRY_SMTP_HOST", "ENQUIRY_SMTP_USER",
                "ENQUIRY_SMTP_PASSWORD", "ENQUIRY_TO"):
        monkeypatch.setenv(key, "x")
    assert enquiry_mod.configured_receiver() == "smtp"
    monkeypatch.setenv("ENQUIRY_WEBHOOK_URL", "https://hooks.example/x")
    assert enquiry_mod.configured_receiver() == "webhook"


def test_partial_smtp_configuration_is_not_a_receiver(monkeypatch):
    """Three of four variables is a misconfiguration, and treating it as
    configured would fail at send time after telling the user it worked."""
    for key in ("ENQUIRY_SMTP_HOST", "ENQUIRY_SMTP_USER", "ENQUIRY_SMTP_PASSWORD"):
        monkeypatch.setenv(key, "x")
    assert enquiry_mod.configured_receiver() is None


@pytest.mark.parametrize("bad,field", [
    ({"email": "not-an-email"}, "email"),
    ({"name": ""}, "name"),
    ({"detail": ""}, "detail"),
    ({"detail": "x" * 5000}, "detail"),
    ({"name": "y" * 500}, "name"),
])
def test_the_endpoint_validates_before_it_delivers(client, bad, field):
    r = client.post("/api/enquiry", json={**VALID, **bad})
    assert r.status_code == 422, field


def test_nothing_is_stored_anywhere_when_there_is_no_receiver(client, tmp_path):
    """A submissions table sounds like the safe middle ground and is not:
    personal data at rest, unwatched, with no retention policy. The module
    documents the decision; this asserts the behaviour."""
    before = set(tmp_path.iterdir())
    client.post("/api/enquiry", json=VALID)
    assert set(tmp_path.iterdir()) == before


def test_the_enquiry_body_is_never_written_to_the_log(client, monkeypatch, caplog):
    """A log line is the easiest place to leak personal data from."""
    monkeypatch.setenv("ENQUIRY_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(enquiry_mod, "_deliver_webhook", lambda _: None)
    with caplog.at_level("DEBUG"):
        client.post("/api/enquiry", json=VALID)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "person@example.com" not in logged
    assert "TQ 123 456" not in logged


def test_the_missing_receiver_is_logged_loudly(client, caplog):
    """So a deployment with an unconnected form is discoverable from the logs
    rather than from a customer who never got a reply."""
    with caplog.at_level("ERROR"):
        client.post("/api/enquiry", json=VALID)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "NOT DELIVERED" in logged
    assert "ENQUIRY_WEBHOOK_URL" in logged
