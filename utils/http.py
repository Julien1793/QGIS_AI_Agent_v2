# utils/http.py
import time
import requests


def post_with_retry(url, json_payload, headers, timeout, stream=False, verify=True,
                    session=None, cancel_check=None):
    # Retry up to 3 attempts on transient errors (network, 429, 503).
    # Client errors (4xx except 429) are returned immediately without retry.
    # Pass cancel_check=callable returning True to skip retry delays on cancellation.
    delays = [1, 2]
    last_exc = None
    requester = session if session is not None else requests
    for attempt in range(3):
        try:
            resp = requester.post(url, json=json_payload, headers=headers,
                                  timeout=timeout, stream=stream, verify=verify)
            if resp.status_code in (429, 503) and attempt < 2:
                if cancel_check and cancel_check():
                    raise requests.exceptions.ConnectionError("cancelled")
                time.sleep(delays[attempt])
                continue
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt < 2:
                if cancel_check and cancel_check():
                    raise
                time.sleep(delays[attempt])
    raise last_exc
