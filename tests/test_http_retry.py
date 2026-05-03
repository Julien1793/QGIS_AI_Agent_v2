# Tests for utils/http.py — the centralised retry/backoff helper.
#
# Every LLM call in the plugin goes through post_with_retry. Bugs here cause
# either lost requests (the agent silently aborts on the first 503) or runaway
# retry storms (every 4xx triggers 3 attempts and burns API credits). We mock
# requests.post so the tests run fast and offline.

from unittest.mock import patch, MagicMock

import pytest
import requests

from qgis_ai_plugin.utils.http import post_with_retry


def _fake_response(status_code: int):
    r = MagicMock(spec=requests.Response)
    r.status_code = status_code
    r.text = f"status {status_code}"
    return r


# ─────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────

def test_success_returns_after_single_attempt():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post:
        mock_post.return_value = _fake_response(200)
        resp = post_with_retry("http://x", {}, {}, timeout=5)
    assert resp.status_code == 200
    assert mock_post.call_count == 1


# ─────────────────────────────────────────────────────────────────────────
# Retry on 429 / 503
# ─────────────────────────────────────────────────────────────────────────

def test_429_retries_then_succeeds():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post, \
         patch("qgis_ai_plugin.utils.http.time.sleep") as mock_sleep:
        mock_post.side_effect = [_fake_response(429), _fake_response(200)]
        resp = post_with_retry("http://x", {}, {}, timeout=5)
    assert resp.status_code == 200
    assert mock_post.call_count == 2
    # First retry waits 1s per the delays = [1, 2] table.
    mock_sleep.assert_called_once_with(1)


def test_503_retried_up_to_three_attempts():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post, \
         patch("qgis_ai_plugin.utils.http.time.sleep") as mock_sleep:
        mock_post.return_value = _fake_response(503)
        resp = post_with_retry("http://x", {}, {}, timeout=5)
    # On the 3rd attempt the helper returns the 503 instead of retrying.
    assert resp.status_code == 503
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2


# ─────────────────────────────────────────────────────────────────────────
# No retry on client errors
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 500, 502])
def test_other_status_codes_returned_immediately_without_retry(status):
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post:
        mock_post.return_value = _fake_response(status)
        resp = post_with_retry("http://x", {}, {}, timeout=5)
    assert resp.status_code == status
    assert mock_post.call_count == 1


# ─────────────────────────────────────────────────────────────────────────
# Network error retries
# ─────────────────────────────────────────────────────────────────────────

def test_connection_error_retried_then_succeeds():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post, \
         patch("qgis_ai_plugin.utils.http.time.sleep"):
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("boom"),
            _fake_response(200),
        ]
        resp = post_with_retry("http://x", {}, {}, timeout=5)
    assert resp.status_code == 200
    assert mock_post.call_count == 2


def test_persistent_connection_error_raises_after_three_attempts():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post, \
         patch("qgis_ai_plugin.utils.http.time.sleep"):
        mock_post.side_effect = requests.exceptions.ConnectionError("down")
        with pytest.raises(requests.exceptions.ConnectionError):
            post_with_retry("http://x", {}, {}, timeout=5)
    assert mock_post.call_count == 3


def test_timeout_retried_like_connection_error():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post, \
         patch("qgis_ai_plugin.utils.http.time.sleep"):
        mock_post.side_effect = [
            requests.exceptions.Timeout("slow"),
            requests.exceptions.Timeout("slow"),
            _fake_response(200),
        ]
        resp = post_with_retry("http://x", {}, {}, timeout=5)
    assert resp.status_code == 200
    assert mock_post.call_count == 3


# ─────────────────────────────────────────────────────────────────────────
# Cancellation
# ─────────────────────────────────────────────────────────────────────────

def test_cancel_check_short_circuits_pending_429_retry():
    with patch("qgis_ai_plugin.utils.http.requests.post") as mock_post:
        mock_post.return_value = _fake_response(429)
        with pytest.raises(requests.exceptions.ConnectionError,
                           match="cancelled"):
            post_with_retry("http://x", {}, {}, timeout=5,
                            cancel_check=lambda: True)
    # Single attempt — the cancel must fire before the sleep+retry.
    assert mock_post.call_count == 1


# ─────────────────────────────────────────────────────────────────────────
# Session passthrough
# ─────────────────────────────────────────────────────────────────────────

def test_session_is_used_when_provided():
    session = MagicMock()
    session.post.return_value = _fake_response(200)
    resp = post_with_retry("http://x", {}, {}, timeout=5, session=session)
    assert resp.status_code == 200
    session.post.assert_called_once()
