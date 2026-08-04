"""
Credentials must not survive a trip through an error message.

These are written against the shapes that actually occur: a service account
key serialised into an exception, a bare PEM block in a traceback, and an
Authorization header echoed back by an API. The repository is public and the
API puts error text in the browser, so a miss here is a live key in a public
place.
"""

import json

import pytest

from redaction import REDACTED, redact, safe_message, safe_str

FAKE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDfake\n"
    "-----END PRIVATE KEY-----\n"
)

KEY_FILE = {
    "type": "service_account",
    "project_id": "sitescanner-verify",
    "private_key_id": "0123456789abcdef0123456789abcdef01234567",
    "private_key": FAKE_KEY,
    "client_email": "verify@sitescanner-verify.iam.gserviceaccount.com",
    "client_id": "112233445566778899000",
}


def test_a_serialised_key_file_loses_its_private_key():
    out = redact(json.dumps(KEY_FILE))
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj" not in out
    assert "BEGIN PRIVATE KEY" not in out
    assert REDACTED in out


def test_the_key_id_goes_too():
    out = redact(json.dumps(KEY_FILE))
    assert "0123456789abcdef0123456789abcdef01234567" not in out


def test_harmless_fields_are_kept_so_the_error_stays_useful():
    """Redaction that removes everything is the same as no error message.
    The project and the account are what tell you which key is misconfigured."""
    out = redact(json.dumps(KEY_FILE))
    assert "sitescanner-verify" in out
    assert "verify@sitescanner-verify.iam.gserviceaccount.com" in out
    assert "service_account" in out


def test_a_bare_pem_block_in_a_traceback():
    out = redact(f"Traceback:\n  credentials={FAKE_KEY}\nRuntimeError")
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj" not in out
    assert "RuntimeError" in out


def test_an_escaped_key_inside_a_json_string():
    """A key read from an env var arrives with literal backslash-n rather
    than real newlines, which a naive multiline pattern misses."""
    escaped = json.dumps(KEY_FILE)          # \n inside the private_key value
    assert "\\n" in escaped
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj" not in redact(escaped)


def test_python_repr_form_with_single_quotes():
    out = redact(str(KEY_FILE))
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj" not in out


def test_bearer_tokens():
    out = redact("401 Unauthorized: Authorization: Bearer ya29.a0AfB_byXlongtokenvalue123456")
    assert "ya29.a0AfB_byXlongtokenvalue123456" not in out
    assert "Bearer" in out


@pytest.mark.parametrize("field", ["client_secret", "refresh_token", "access_token"])
def test_other_credential_fields(field):
    assert "s3cr3tvalue" not in redact(f'{{"{field}": "s3cr3tvalue"}}')


def test_safe_message_names_the_exception_type():
    exc = RuntimeError(f"could not authenticate with {json.dumps(KEY_FILE)}")
    out = safe_message(exc)
    assert out.startswith("RuntimeError:")
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj" not in out


def test_safe_message_truncates_a_huge_earth_engine_error():
    """Earth Engine serialises the whole request into some errors — thousands
    of characters, useless to a user, and the part most likely to be carrying
    something sensitive."""
    exc = RuntimeError("x" * 5000)
    out = safe_message(exc, limit=200)
    assert len(out) <= 200
    assert out.endswith("…")


def test_safe_message_collapses_newlines_so_it_stays_one_line():
    out = safe_message(RuntimeError("line one\nline two\n\nline three"))
    assert "\n" not in out
    assert "line one line two line three" in out


def test_redacting_ordinary_text_changes_nothing():
    text = "Earth Engine failed: image collection is empty for 2013-04"
    assert redact(text) == text


def test_safe_str_handles_non_exceptions():
    assert "s3cr3t" not in safe_str({"private_key": "s3cr3t"})
