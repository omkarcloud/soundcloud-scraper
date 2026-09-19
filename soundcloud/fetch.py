"""SoundCloud transport: plain curl_cffi with browser-impersonated TLS
against the same JSON API the soundcloud.com web app calls
(https://api-v2.soundcloud.com). No browser, no cookies, no login and no
proxy needed (validated 2026-09-19 from direct Indian egress and through a
US residential exit; 60 back-to-back calls from one IP all answered 200).

How the web app authenticates, and how this module copies it:

  1. Every soundcloud.com page server-renders `window.__sc_hydration`, a
     JSON list whose `apiClient` entry carries the public web `client_id`
     (32 chars, identical for every visitor, rotated every few weeks). The
     last a-v2.sndcdn.com asset bundle embeds the same id as
     `client_id:"…"`, used here as the fallback source.
  2. Every api-v2 GET carries `?client_id=…` plus `Origin/Referer:
     https://soundcloud.com`. A stale id answers 401 -> re-harvest once.

The id is harvested once per process and re-harvested on the first 401.
config.SOUNDCLOUD_CLIENT_ID pins one by hand.

Surfaces used (all GET, all anonymous):
  /resolve?url=                                 any soundcloud.com link -> object
  /tracks/{id}, /tracks?ids=                    track details / batch (50 max)
  /tracks/{id}/{comments|likers|reposters|related|albums|playlists_without_albums}
  /media/…/stream/{progressive|hls}             -> signed CDN stream link
  /users/{id}, /users/{id}/{tracks|toptracks|albums|playlists_without_albums|
      playlists|likes|track_likes|playlist_likes|followers|followings|
      comments|spotlight|relatedartists}
  /users/soundcloud:users:{id}/web-profiles     (bare numeric id -> 400)
  /stream/users/{id}[/reposts]                  profile feed / reposts
  /playlists/{id}, /playlists/{id}/{likers|reposters}
  /search[/tracks|users|playlists|albums|playlists_without_albums|queries]
  /search/suggest/tags, /charts, /charts/selections, /mixed-selections,
  /system-playlists/{urn}, /recent-tracks/{tag}, /featured_tracks/front
  soundcloud.com/oembed, wave.sndcdn.com/<id>_m.json

Upstream quirks this layer absorbs:
  * search rows stop at offset 300 whatever the total_results says;
  * opaque list cursors (`offset=<timestamp>,…`) answer 500 when garbled;
  * a playlist / station response carries only its first few tracks in
    full, the rest as {id, kind, policy} stubs -> hydrate via /tracks?ids=.

Block fallback: if the pod's own IP is ever refused (403 / 429 / non-JSON on
calls that normally answer), the worker thread switches to a sticky
residential exit (config.SOUNDCLOUD_FALLBACK_PROXY_COUNTRY) for
config.SOUNDCLOUD_DIRECT_COOLDOWN seconds, rotating exits on repeat blocks.
A patchright pool was NOT built: nothing on api-v2 needs a browser today,
and the SSR hydration of any page (track/user pages embed `sound` / `user`)
is the next fallback if api-v2 itself is ever closed.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  SoundCloudUpstreamError  transport failure / 5xx            — retryable
  SoundCloudBlocked        403 / 429 / non-JSON body          — retryable
  SoundCloudBadRequest     upstream 400, garbled cursor        — never retried
  SoundCloudNotFound       404 / private / deleted            — never retried
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "https://soundcloud.com"
API = "https://api-v2.soundcloud.com"
IMPERSONATE = "chrome"
TIMEOUT = 30
FANOUT_WORKERS = 6
BATCH_MAX = 50                 # /tracks?ids= answers at most 50 per call

_HYDRATION_RE = re.compile(r"window\.__sc_hydration\s*=\s*(\[.*?\]);\s*</script>", re.S)
_VERSION_RE = re.compile(r'__sc_version\s*=\s*"(\d+)"')
_ASSET_RE = re.compile(r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"')
_BUNDLE_ID_RE = re.compile(r'client_id\s*[:=]\s*"([A-Za-z0-9]{32})"')

PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
}
API_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "origin": SITE,
    "referer": SITE + "/",
}


class SoundCloudUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class SoundCloudBlocked(SoundCloudUpstreamError, Blocked):
    """403 / 429 or a non-JSON body where JSON was expected — retryable."""


class SoundCloudBadRequest(BadRequest):
    """Upstream 400, or a cursor SoundCloud cannot read — never retried."""


class SoundCloudNotFound(NotFound):
    """Deleted, private or never-existing resource — never retried."""


class _ClientIdRejected(SoundCloudUpstreamError):
    """401: the web client_id was rotated — re-harvest once."""


# ---- sessions ---------------------------------------------------------------------
# One curl session per worker thread (a curl handle must not be shared). A
# thread whose direct egress got blocked moves to a residential exit until
# `until`, then goes back to direct.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    via_proxy = getattr(_local, "proxy_until", 0) > time.time()
    if sess is not None and getattr(sess, "_sc_proxied", False) != via_proxy:
        _drop_session()
        sess = None
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.soundcloud_proxy() or (config.soundcloud_fallback_proxy() if via_proxy else None)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess._sc_proxied = via_proxy
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _escalate():
    """Direct egress (or the current exit) was blocked: run this thread
    through a fresh residential exit for a while (None configured = just
    rebuild the session)."""
    if config.soundcloud_fallback_proxy() is not None:
        _local.proxy_until = time.time() + config.SOUNDCLOUD_DIRECT_COOLDOWN
    _drop_session()


def dump_debug(name, text):
    """Write a raw response to $SOUNDCLOUD_DEBUG_DIR/<name>.txt."""
    dbg = os.environ.get("SOUNDCLOUD_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- client_id --------------------------------------------------------------------

def client_id_from_page(html):
    """(client_id, app_version) out of a soundcloud.com page's hydration."""
    version = _VERSION_RE.search(html or "")
    version = version.group(1) if version else None
    match = _HYDRATION_RE.search(html or "")
    if match:
        try:
            for entry in json.loads(match.group(1)):
                if isinstance(entry, dict) and entry.get("hydratable") == "apiClient":
                    cid = (entry.get("data") or {}).get("id")
                    if cid:
                        return cid, version
        except ValueError:
            pass
    return None, version


def _harvest_client_id():
    sess = _session()
    try:
        page = sess.get(SITE + "/", headers=PAGE_HEADERS, timeout=TIMEOUT)
    except Exception as e:
        raise SoundCloudUpstreamError(f"client_id harvest failed: {type(e).__name__}: {e}")
    if page.status_code in (403, 429):
        raise SoundCloudBlocked(f"HTTP {page.status_code} on the soundcloud.com homepage")
    cid, version = client_id_from_page(page.text)
    if cid:
        return cid, version
    # Fallback: the asset bundles (the id sits in the last one).
    for src in reversed(_ASSET_RE.findall(page.text or "")):
        try:
            js = sess.get(src, headers={"accept": "*/*", "referer": SITE + "/"}, timeout=60).text
        except Exception:
            continue
        m = _BUNDLE_ID_RE.search(js or "")
        if m:
            return m.group(1), version
    dump_debug("homepage", page.text)
    raise SoundCloudUpstreamError("no client_id on the soundcloud.com homepage (page format changed?)")


_cid_lock = threading.Lock()
_cid = {"value": None, "version": None, "pinned_rejected": False}


def client_id(force=False):
    """(client_id, app_version): harvested on first use, re-harvested when
    forced (after a 401). config.SOUNDCLOUD_CLIENT_ID pins one until
    SoundCloud rejects it; the harvested id is used from then on."""
    pinned = getattr(config, "SOUNDCLOUD_CLIENT_ID", None)
    if pinned and not force and not _cid["pinned_rejected"]:
        return pinned, None
    with _cid_lock:
        if pinned and force:
            _cid["pinned_rejected"] = True
        if force or not _cid["value"]:
            _cid["value"], _cid["version"] = _harvest_client_id()
        return _cid["value"], _cid["version"]


# ---- requests ---------------------------------------------------------------------

def _classify(resp, label, has_cursor):
    status = resp.status_code
    if status == 200:
        return
    if status == 401:
        raise _ClientIdRejected(f"HTTP 401 on {label}")
    if status == 404:
        raise SoundCloudNotFound(f"{label}: not found on SoundCloud (deleted, private or wrong id)")
    if status == 400:
        if has_cursor:
            raise SoundCloudBadRequest("invalid cursor: pass the next_cursor value from the previous page unchanged")
        raise SoundCloudBadRequest(f"SoundCloud rejected {label}")
    if status == 500 and has_cursor:
        raise SoundCloudBadRequest("invalid cursor: pass the next_cursor value from the previous page unchanged")
    if status in (403, 429):
        dump_debug("blocked", resp.text)
        raise SoundCloudBlocked(f"HTTP {status} on {label}")
    raise SoundCloudUpstreamError(f"HTTP {status} on {label}")


def api_get(path, params=None, *, label=None, cursor_param=None, url=None):
    """GET one api-v2 path (e.g. "/tracks/123") -> parsed JSON.

    `params` values that are None/"" are dropped. `cursor_param` names the
    param carrying a caller-supplied cursor (a 400/500 then means the
    cursor is garbled, not that SoundCloud is down). `url` replaces
    API+path (media transcoding links). Retries transport errors, 5xx and
    blocks with backoff (escalating to a residential exit on blocks); a 401
    re-harvests the client_id once. 400/404 raise immediately."""
    label = label or path
    query = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    has_cursor = bool(cursor_param and query.get(cursor_param) not in (None, "", 0, "0"))
    refreshed = False
    last = None
    attempt = 0
    while attempt < config.MAX_RETRIES:
        attempt += 1
        cid, version = client_id()
        q = {**query, "client_id": cid, "app_locale": "en"}
        if version:
            q["app_version"] = version
        try:
            resp = _session().get(url or API + path, params=q, headers=API_HEADERS, timeout=TIMEOUT)
        except Exception as e:
            last = SoundCloudUpstreamError(f"request failed: {type(e).__name__}: {e}")
            _drop_session()
        else:
            try:
                _classify(resp, label, has_cursor)
                body = (resp.text or "").lstrip()
                if not body.startswith(("{", "[")):
                    dump_debug("nonjson", resp.text)
                    raise SoundCloudBlocked(f"{label} returned a non-JSON body")
                return resp.json()
            except _ClientIdRejected as e:
                last = e
                if refreshed:
                    break
                refreshed = True
                client_id(force=True)
                attempt -= 1          # a client_id refresh is not a failed attempt
                continue
            except SoundCloudBlocked as e:
                last = e
                _escalate()
            except SoundCloudUpstreamError as e:
                last = e
                _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def page_get(url, params=None, *, headers=None, label=None):
    """GET a non-api page (oembed, waveform JSON, short-link redirect) ->
    the curl response (raises on transport errors / 5xx / blocks)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _session().get(url, params=params, headers=headers or PAGE_HEADERS,
                                  timeout=TIMEOUT, allow_redirects=False)
        except Exception as e:
            last = SoundCloudUpstreamError(f"request failed: {type(e).__name__}: {e}")
            _drop_session()
        else:
            if resp.status_code in (403, 429):
                last = SoundCloudBlocked(f"HTTP {resp.status_code} on {label or url}")
                _escalate()
            elif resp.status_code >= 500:
                last = SoundCloudUpstreamError(f"HTTP {resp.status_code} on {label or url}")
            else:
                return resp
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- lists -------------------------------------------------------------------------

def next_offset(body):
    """The `offset` of a list response's next_href (None on the last page).
    Numeric for search / comments / charts, opaque for followers, likes, …"""
    href = (body or {}).get("next_href") if isinstance(body, dict) else None
    if not href:
        return None
    try:
        return (parse_qs(urlparse(href).query).get("offset") or [None])[0]
    except Exception:
        return None


def collection(body):
    items = (body or {}).get("collection") if isinstance(body, dict) else None
    return items if isinstance(items, list) else []


# ---- resolution ----------------------------------------------------------------------

_KIND_PATH = {"track": "tracks", "user": "users", "playlist": "playlists"}
_resolved_lock = threading.Lock()
_resolved = {}                # link -> (expires, id)  (link -> id never changes)
RESOLVE_MEMO_TTL = 6 * 3600


def expand_short_link(link):
    """on.soundcloud.com/<code> -> the soundcloud.com link it redirects to."""
    resp = page_get(link, label="short link")
    location = resp.headers.get("location") or resp.headers.get("Location")
    if resp.status_code in (301, 302, 303, 307, 308) and location:
        parsed = urlparse(location)
        host = (parsed.hostname or "").lower()
        if host.endswith("soundcloud.com") and host != "on.soundcloud.com":
            return f"{SITE}{parsed.path}"
    raise SoundCloudNotFound(f"short link {link} does not lead to a SoundCloud page")


def resolve_link(link):
    """/resolve a soundcloud.com link -> the full object (any kind)."""
    if urlparse(link).hostname == "on.soundcloud.com":
        link = expand_short_link(link)
    try:
        return api_get("/resolve", {"url": link}, label=f"link {link}")
    except SoundCloudNotFound:
        raise SoundCloudNotFound(f"{link} is not a public SoundCloud page (deleted, private or mistyped)")


def fetch_object(ref, kind):
    """A validated ref ({"id"} | {"link"} [+ "secret_token"]) -> the full
    upstream object of `kind` (track / user / playlist)."""
    if ref.get("id"):
        params = {"secret_token": ref.get("secret_token")} if ref.get("secret_token") else None
        try:
            return api_get(f"/{_KIND_PATH[kind]}/{ref['id']}", params, label=f"{kind} {ref['id']}")
        except SoundCloudNotFound:
            raise SoundCloudNotFound(f"{kind} {ref['id']} not found on SoundCloud (deleted, private or wrong id)")
    obj = resolve_link(ref["link"])
    got = obj.get("kind") if isinstance(obj, dict) else None
    if got != kind:
        raise SoundCloudBadRequest(f"{ref['link']} is a SoundCloud {got or 'page'}, not a {kind}")
    _remember(ref["link"], obj.get("id"))
    return obj


def _remember(link, oid):
    if oid:
        with _resolved_lock:
            _resolved[link] = (time.time() + RESOLVE_MEMO_TTL, oid)


def object_id(ref, kind):
    """A validated ref -> the numeric id (one /resolve call for a link,
    memoised in-process since a permalink's id never changes)."""
    if ref.get("id"):
        return int(ref["id"])
    with _resolved_lock:
        hit = _resolved.get(ref["link"])
    if hit and hit[0] > time.time():
        return int(hit[1])
    return int(fetch_object(ref, kind)["id"])


# ---- hydration ---------------------------------------------------------------------

def is_stub(track):
    """A playlist / station track entry carrying only {id, kind, policy, …}."""
    return isinstance(track, dict) and not track.get("title")


def tracks_by_ids(ids, playlist_id=None, secret_token=None):
    """Full track objects for `ids` (any count, 50 per call in parallel),
    keyed by id. Ids SoundCloud no longer serves are absent from the map.
    playlist_id / secret_token let a private playlist's tracks resolve."""
    ids = [int(i) for i in dict.fromkeys(ids) if i]
    chunks = [ids[i:i + BATCH_MAX] for i in range(0, len(ids), BATCH_MAX)]

    def fetch(chunk):
        params = {"ids": ",".join(map(str, chunk))}
        if playlist_id:
            params["playlistId"] = playlist_id
            params["playlistSecretToken"] = secret_token
        body = api_get("/tracks", params, label="track batch")
        return body if isinstance(body, list) else []

    found = {}
    for batch in run_parallel([lambda c=c: fetch(c) for c in chunks]):
        for t in batch:
            if isinstance(t, dict) and t.get("id"):
                found[t["id"]] = t
    return found


def hydrate(tracks, playlist_id=None, secret_token=None):
    """Replace the stub entries of a playlist / station track list with
    full objects, keeping order (unserved stubs stay as stubs)."""
    tracks = [t for t in tracks or [] if isinstance(t, dict)]
    missing = [t["id"] for t in tracks if is_stub(t) and t.get("id")]
    if not missing:
        return tracks
    found = tracks_by_ids(missing, playlist_id, secret_token)
    return [found.get(t.get("id"), t) if is_stub(t) else t for t in tracks]


def run_parallel(fns):
    """Run zero-arg callables in parallel; results align with `fns`.
    Exceptions propagate from the first failing call."""
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(FANOUT_WORKERS, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


if __name__ == "__main__":
    # Smoke test: python soundcloud/fetch.py [soundcloud.com link]
    target = sys.argv[1] if len(sys.argv) > 1 else "https://soundcloud.com/edsheeran/photograph"
    print("client_id:", client_id())
    obj = resolve_link(target)
    print(obj.get("kind"), obj.get("id"), obj.get("title") or obj.get("username"))
