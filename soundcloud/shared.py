"""Helpers shared by the SoundCloud endpoint modules: numeric-offset pages,
cursor pages, station hydration and the in-process lookup tables (chart
selections, trending-by-genre shelves) several routes resolve names
against."""
import threading
import time

from soundcloud import parsers as P
from soundcloud.fetch import api_get, collection, hydrate, next_offset


LOOKUP_TTL = 3600          # seconds an in-process lookup table is reused
_lookup_lock = threading.Lock()
_lookups = {}


def lookup(key, build):
    """Memoise build() for LOOKUP_TTL seconds (chart / discover shelves)."""
    now = time.time()
    with _lookup_lock:
        hit = _lookups.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = build()
    with _lookup_lock:
        _lookups[key] = (now + LOOKUP_TTL, value)
    return value


def offset_of(page, limit):
    return (page - 1) * limit


def paged(path, page, limit, *, params=None, parser=P.item, max_results=None, label=None):
    """One numeric-offset page of an api-v2 list -> (raw body, parsed
    entries, pagination block). `max_results` is SoundCloud's hard depth
    (search: 300 rows) — asking past it is a 400, and the last reachable
    page is shortened to end exactly there."""
    offset = offset_of(page, limit)
    if max_results is not None and offset >= max_results:
        last = (max_results + limit - 1) // limit
        raise ValueError(f"SoundCloud serves only the first {max_results} results of a search: "
                         f"with limit={limit} the last page is {last}; narrow the query or filters instead")
    size = min(limit, max_results - offset) if max_results is not None else limit
    body = api_get(path, {**(params or {}), "offset": offset, "limit": size}, label=label)
    raw = collection(body)
    entries = P.items(raw, parser)
    has_more = bool(raw) and next_offset(body) is not None
    if max_results is not None and offset + size >= max_results:
        has_more = False
    total = body.get("total_results") if isinstance(body, dict) else None
    return body, entries, P.pagination(page, limit, has_more, total, max_results)


def cursor_list(path, cursor, limit, key, *, parser=P.item, params=None, label=None, prepare=None):
    """One cursor page of an api-v2 list -> {key: entries, next_cursor,
    has_more}. `prepare(raw_items)` may enrich the raw rows first."""
    body = api_get(path, {**(params or {}), "offset": cursor, "limit": limit},
                   label=label, cursor_param="offset")
    raw = collection(body)
    if prepare:
        raw = prepare(raw)
    return P.cursor_page(P.items(raw, parser), body, key)


def station(obj, limit):
    """A system playlist (station / trending-by-genre) with its first
    `limit` tracks hydrated and numbered."""
    out = P.system_playlist(obj) or {}
    tracks = [t for t in (obj or {}).get("tracks") or [] if isinstance(t, dict)]
    out["tracks"] = P.numbered(hydrate(tracks[:limit]))
    return out


def mixed_selections():
    """The Discover page shelves (buzzing, curated, promos, trending by
    genre), memoised for an hour."""
    return lookup(("soundcloud", "mixed-selections"),
                  lambda: collection(api_get("/mixed-selections", {"limit": 20}, label="discover page")))


def chart_selections():
    """The official Music Charts US / UK shelves, memoised for an hour."""
    return lookup(("soundcloud", "chart-selections"),
                  lambda: collection(api_get("/charts/selections", label="chart list")))
