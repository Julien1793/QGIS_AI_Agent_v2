# utils/http.py
import time
import requests


def post_with_retry(url, json_payload, headers, timeout, stream=False, verify=True):
    # Retry up to 3 attempts on transient errors (network, 429, 503).
    # Client errors (4xx except 429) are returned immediately without retry.
    delays = [1, 2]
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.post(url, json=json_payload, headers=headers,
                                 timeout=timeout, stream=stream, verify=verify)
            if resp.status_code in (429, 503) and attempt < 2:
                time.sleep(delays[attempt])
                continue
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt < 2:
                time.sleep(delays[attempt])
    raise last_exc
