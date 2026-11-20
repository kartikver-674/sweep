"""HTTP + text helpers shared by every free source adapter. stdlib only.

Anything that needs a paid Apify actor stays in scraper.py; everything in
sources/ is free and unauthenticated.
"""
import html
import http.client
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import telemetry

UA = "Mozilla/5.0 (compatible; job-scraper)"
_TAG_RE = re.compile(r"<[^>]+>")


# Retried despite being 4xx: a rate limit or a request timeout says "later",
# not "dead token". Every other 4xx still fails on the first try.
_RETRY_4XX = {408, 429}
_MAX_WAIT = 30          # seconds; a Retry-After longer than this is not worth it
_TOTAL = 90             # seconds for one whole request, body included


def _wait(exc, attempt):
    """Seconds to sleep before the next try: the server's Retry-After when it
    sends a number (capped), else exponential backoff."""
    after = getattr(exc, "headers", None) and exc.headers.get("Retry-After")
    if after and str(after).strip().isdigit():
        return min(int(after), _MAX_WAIT)
    return 2 ** attempt


def _read(req, timeout, total):
    """urlopen + read with a deadline on the WHOLE response.

    `timeout` bounds each socket operation, not the request: a server that
    trickles bytes just under it never times out (lever:veeva took 359 s of
    an 8.8-minute sweep, docs/search-engine-v2-d-finalization.md). Reading in
    chunks against a monotonic deadline caps it.
    """
    deadline = time.monotonic() + total
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        chunks = []
        while True:
            chunk = resp.read(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            if time.monotonic() > deadline:
                raise TimeoutError(f"response took longer than {total}s")


def _retrying(make_req, timeout, retries, total):
    """The shared loop: bounded reads, backoff on transient failures, 4xx
    raised at once except the "come back later" ones."""
    last = None
    for attempt in range(retries + 1):
        try:
            return _read(make_req(), timeout, total)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in _RETRY_4XX:
                raise
            last = exc
        # A truncated body is transient and is NOT an OSError, so without this it
        # escaped the retry loop entirely and killed the fetch (seen on ~200KB+
        # JD pages). http.client.HTTPException is the base of IncompleteRead.
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as exc:
            last = exc
        if attempt < retries:
            # Counted where it happens: a retry is the difference between a
            # slow source and a flaky one, and nothing above this frame can see
            # it. No-op unless telemetry is on.
            telemetry.retried()
            time.sleep(_wait(last, attempt))
    raise last


def get_bytes(url, timeout=25, retries=2, total=_TOTAL):
    """GET with a BOUNDED timeout and backoff on transient failures.

    Bounded is the point: an unbounded read is exactly how the Apify path used
    to wedge a whole sweep (see the note in scraper.scrape_search). 4xx is not
    retried (a dead board token should fail on the first try, not the third)
    except 408 and 429, which honour Retry-After.
    """
    return _retrying(
        lambda: urllib.request.Request(url, headers={"User-Agent": UA}),
        timeout, retries, total)


def get_json(url, **kw):
    return json.loads(get_bytes(url, **kw).decode("utf-8", "replace"))


def post_json(url, payload, timeout=25, retries=2, headers=None, total=_TOTAL):
    """POST a JSON body, get JSON back. Same bounded/retry policy as get_bytes.

    Exists for Workday, whose job search is POST-only — the one thing that kept
    it out of ats.ATS (see that module's "known gaps").
    """
    body = json.dumps(payload).encode()
    head = {"User-Agent": UA, "Content-Type": "application/json",
            "Accept": "application/json"}
    head.update(headers or {})
    raw = _retrying(lambda: urllib.request.Request(url, data=body, headers=head),
                    timeout, retries, total)
    return json.loads(raw.decode("utf-8", "replace"))


def get_xml(url, **kw):
    return ET.fromstring(get_bytes(url, **kw))


def strip_html(s):
    """Unescape entities FIRST (Greenhouse returns entity-encoded markup), then
    drop tags and collapse whitespace."""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(s or ""))).strip()


def dig(obj, path):
    """Walk a dotted path through nested dicts; None if any hop is missing.

    "location.name" -> obj["location"]["name"]. This is what lets an ATS
    adapter be a dict of field -> path instead of a function.
    """
    if not path:
        return None
    for hop in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(hop)
        if obj is None:
            return None
    return obj


def flat(value):
    """Any JSON value -> readable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(flat(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        for k in ("name", "label", "text", "fullLocation", "value"):
            if k in value:
                return flat(value[k])
    return str(value)
