"""SoundCloud reference parsing: ONE param per input that auto-detects its
forms (tripadvisor QueryOrLinkField convention — never a sibling `url`/`id`
pair). Parsing is offline: every resolver returns a small JSON-able dict
{"id", "link", "secret_token"} (the unused keys None, so the validated
params stay a stable response-cache key); fetch.object_id() / fetch_object()
turn a link into the object with one /resolve call at request time.

  track     1516134547 | soundcloud:tracks:1516134547
            | https://soundcloud.com/edsheeran/photograph
            | edsheeran/photograph                        (bare path)
            | https://soundcloud.com/artist/track/s-AbCdE (secret link)
            | https://on.soundcloud.com/XyZ12             (share short link)
            | https://api.soundcloud.com/tracks/1516134547
            | https://w.soundcloud.com/player/?url=…tracks%2F1516134547
  user      3685019 | soundcloud:users:3685019 | edsheeran (permalink)
            | https://soundcloud.com/edsheeran[/tracks|/likes|…]
  playlist  1714689261 | soundcloud:playlists:1714689261
            | https://soundcloud.com/music-charts-us/sets/all-music-genres
            | music-charts-us/sets/all-music-genres  (albums are sets too)
  link      any soundcloud.com / on.soundcloud.com link (resolve, embed)

m.soundcloud.com / www.soundcloud.com links are rewritten to soundcloud.com
(/resolve 404s on the mobile host) and tracking query strings (?si=,
?utm_*, ?in=) are dropped.

Also holds the route tables: search filters, playlist / like kinds and the
chart names.
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

SITE = "https://soundcloud.com"

_DIGITS_RE = re.compile(r"^\d{1,12}$")
_URN_RE = re.compile(r"^soundcloud:(tracks|users|playlists):(\d{1,12})$")
_SECRET_RE = re.compile(r"^s-[A-Za-z0-9]{4,}$")
_PERMALINK_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_API_PATH_RE = re.compile(r"/(tracks|users|playlists)/(?:soundcloud(?::|%3A)\1(?::|%3A))?(\d{1,12})")
_SITE_HOSTS = {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}

# First path segments that are site sections, not user permalinks.
RESERVED = {
    "discover", "charts", "search", "stream", "upload", "you", "messages", "notifications",
    "settings", "pages", "terms-of-use", "imprint", "jobs", "tags", "stations", "feed",
    "people", "popular", "signin", "login", "logout", "mobile", "apps", "creators", "go",
    "artists", "premium", "pro", "connect", "home", "trending", "for-artists", "community-guidelines",
}
# Profile tabs: soundcloud.com/<user>/<tab> is still the user.
USER_TABS = {"tracks", "albums", "sets", "reposts", "likes", "followers", "following",
             "comments", "popular-tracks", "spotlight", "playlists", "insights"}

_KIND_OF_URN = {"tracks": "track", "users": "user", "playlists": "playlist"}


def _ref(oid=None, link=None, secret_token=None):
    return {"id": str(oid) if oid else None, "link": link, "secret_token": secret_token}


def _is_link(text):
    return text.startswith(("http://", "https://", "//")) or "soundcloud.com" in text.split("/")[0]


def parse_link(text):
    """A SoundCloud link -> (kind, value) where kind is 'short' (value =
    the short link), 'api' (value = (urn kind, id)) or 'site' (value =
    path segments on soundcloud.com). ValueError for another site."""
    url = text if "://" in text else ("https:" + text if text.startswith("//") else "https://" + text)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "on.soundcloud.com":
        code = parsed.path.strip("/")
        if not code:
            raise ValueError("empty on.soundcloud.com short link")
        return "short", f"https://on.soundcloud.com/{code}"
    if host in ("api.soundcloud.com", "api-v2.soundcloud.com"):
        m = _API_PATH_RE.search(unquote(parsed.path).replace("%3A", ":"))
        if m:
            return "api", (m.group(1), m.group(2))
        raise ValueError("unrecognised api.soundcloud.com link")
    if host == "w.soundcloud.com":            # embed player: ?url=<api link>
        inner = (parse_qs(parsed.query).get("url") or [""])[0]
        if inner:
            return parse_link(inner)
        raise ValueError("embed player link without a url")
    if host not in _SITE_HOSTS:
        raise ValueError("must be a SoundCloud id or a soundcloud.com link")
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    if not segments:
        raise ValueError("the soundcloud.com home page is not a track, user or playlist")
    return "site", segments


def site_link(segments):
    return SITE + "/" + "/".join(segments)


def classify_segments(segments):
    """soundcloud.com path segments -> ('user'|'track'|'playlist'|'station'|
    'other', canonical segments, secret token)."""
    first = segments[0].lower()
    if first == "discover" and len(segments) >= 3 and segments[1] == "sets":
        return "station", segments[:3], None
    if first in RESERVED:
        return "other", segments, None
    if len(segments) == 1 or segments[1].lower() in USER_TABS and not (
            segments[1].lower() == "sets" and len(segments) >= 3):
        return "user", segments[:1], None
    if segments[1].lower() == "sets":
        secret = segments[3] if len(segments) >= 4 and _SECRET_RE.match(segments[3]) else None
        return "playlist", segments[:3], secret
    secret = segments[2] if len(segments) >= 3 and _SECRET_RE.match(segments[2]) else None
    return "track", segments[:2], secret


def _resolve(value, kind):
    """Shared id / urn / link / bare-path parsing for track, user, playlist."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{kind} must not be empty")
    if _DIGITS_RE.match(text):
        return _ref(oid=text)
    m = _URN_RE.match(text)
    if m:
        if _KIND_OF_URN[m.group(1)] != kind:
            raise ValueError(f"{text} is a {_KIND_OF_URN[m.group(1)]} URN, not a {kind}")
        return _ref(oid=m.group(2))
    if not _is_link(text):
        # bare permalink path: "edsheeran", "edsheeran/photograph", "user/sets/slug"
        segments = [s for s in text.split("/") if s]
        if not all(_PERMALINK_RE.match(s) for s in segments):
            raise ValueError(f"{kind} must be a SoundCloud id, URN, permalink or soundcloud.com link")
        return _resolve_segments(segments, kind, text)
    form, parsed = parse_link(text)
    if form == "short":
        return _ref(link=parsed)             # expanded (and kind-checked) at request time
    if form == "api":
        urn_kind, oid = parsed
        if _KIND_OF_URN[urn_kind] != kind:
            raise ValueError(f"that link is a {_KIND_OF_URN[urn_kind]}, not a {kind}")
        return _ref(oid=oid)
    return _resolve_segments(parsed, kind, text)


def _resolve_segments(segments, kind, text):
    got, canon, secret = classify_segments(segments)
    if got != kind:
        what = {"station": "station", "other": "SoundCloud site page"}.get(got, got)
        raise ValueError(f"{text} is a {what} link, not a {kind}")
    return _ref(link=site_link(canon + ([secret] if secret else [])), secret_token=secret)


def resolve_track(value):
    return _resolve(value, "track")


def resolve_user(value):
    return _resolve(value, "user")


def resolve_playlist(value):
    return _resolve(value, "playlist")


def resolve_any_link(value):
    """Any SoundCloud link (or a bare permalink path) -> canonical link
    string, for /resolve and /embed."""
    text = str(value or "").strip()
    if not _is_link(text):
        segments = [s for s in text.split("/") if s]
        if not segments or not all(_PERMALINK_RE.match(s) or s.startswith("s-") for s in segments):
            raise ValueError("link must be a soundcloud.com link or a permalink path like edsheeran/photograph")
        return site_link(segments)
    form, parsed = parse_link(text)
    if form == "short":
        return parsed
    if form == "api":
        urn_kind, oid = parsed
        return f"https://api.soundcloud.com/{urn_kind}/{oid}"
    kind, canon, secret = classify_segments(parsed)
    if kind == "other":
        raise ValueError(f"{text} is a SoundCloud site page, not a track, user, playlist or station")
    return site_link(canon + ([secret] if secret else []))


def resolve_track_list(values, max_items=50):
    """Comma list of track ids / links -> list of refs (deduped, order kept)."""
    out, seen = [], set()
    for value in values:
        ref = resolve_track(value)
        key = ref["id"] or ref["link"]
        if key not in seen:
            seen.add(key)
            out.append(ref)
    if len(out) > max_items:
        raise ValueError(f"at most {max_items} tracks")
    return out


# ---- route tables -------------------------------------------------------------------

# search filter tables live in schemas.py (public value -> api-v2 token)
SEARCH_MAX_RESULTS = 300          # api-v2 search rows stop at offset 300

# playlist kinds -> (search path, user list path, track list path)
PLAYLIST_KINDS = {
    "all": ("/search/playlists", "playlists", "playlists"),
    "playlists": ("/search/playlists_without_albums", "playlists_without_albums", "playlists_without_albums"),
    "albums": ("/search/albums", "albums", "albums"),
}
LIKE_KINDS = {"all": "likes", "tracks": "track_likes", "playlists": "playlist_likes"}

# Top 50 charts: country -> the official chart account's selection urn.
TOP50_COUNTRIES = {"US": "soundcloud:selections:music-charts-us",
                   "GB": "soundcloud:selections:music-charts-uk"}
TOP50_COUNTRY_ALIASES = {"UK": "GB"}
TOP50_CHART_ALIASES = {"all": "all-music-genres", "all-music": "all-music-genres",
                       "new-and-hot": "new-hot", "new": "new-hot", "rnb": "r-b", "r&b": "r-b",
                       "hiphop": "hip-hop"}

# Trending-by-genre system playlists (live list read from /mixed-selections;
# this copy only documents the defaults seen 2026-09-19).
TRENDING_GENRES = ["all-genres", "trap", "hip-hop", "pop", "electronic", "r-n-b", "alternative-hip-hop",
                   "indie", "dubstep", "house", "folk", "alternative-rock", "hardcore", "rock", "reggae",
                   "latin", "ambient", "metal", "dancehall", "afrobeat"]
TRENDING_GENRE_ALIASES = {"all": "all-genres", "hiphop": "hip-hop", "rnb": "r-n-b", "r&b": "r-n-b",
                          "r-b": "r-n-b", "edm": "electronic"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower().replace("&", "-")).strip("-")
