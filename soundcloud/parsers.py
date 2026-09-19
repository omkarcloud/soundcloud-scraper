"""SoundCloud payload normalizers: api-v2 JSON -> one clean snake_case shape
per resource type (track, user, playlist, station, comment, …).

Conventions: `link` for web URLs, `artwork` / `avatar` {link (500x500),
original_link} for images, `duration_ms` + `duration` ("6:18"), `is_*` /
`has_*` booleans, ISO dates (YYYY-MM-DD) and UTC datetimes
(YYYY-MM-DDTHH:MM:SSZ), counters grouped under `stats`, null for missing
(never "" or omitted keys).

Upstream fields dropped on purpose (and why):
  * uri, urn, kind (single objects), user_id, track_id on nested objects —
    API paths / duplicates of `id` and the nested `user`.
  * track_authorization, media.transcodings — per-request playback tokens
    and internal API links; /soundcloud/tracks/stream turns them into
    playable links instead.
  * display_date (= release_date or created_at, presentation only),
    state ("finished" upload-processing flag), has_downloads_left (folded
    into is_downloadable), managed_by_feeds (internal ingestion flag),
    groups_count (SoundCloud groups were retired; always 0), first_name /
    last_name (full_name carries both), date_of_birth (almost always null;
    personal), query_urn / tracking_feature_name / txid /
    query_time_in_millis / sc_a_id (search & tracking ids), station_urn /
    station_permalink (turned into station_link), calculated_artwork_url
    when artwork_url exists, social_proof* (logged-in personalisation, null
    anonymously), p_line / c_line when the *_for_display copy exists.
  * suggestion highlight markup (<b>…</b>) is stripped.
"""
import base64
import json
import re
from urllib.parse import parse_qs, urlparse

from datetime import datetime, timezone

SITE = "https://soundcloud.com"
_SIZE_RE = re.compile(r"-(large|t\d+x\d+|crop|original|small|badge|tiny|mini)\.(jpg|jpeg|png|gif)", re.I)
_DEFAULT_AVATAR_RE = re.compile(r"/images/default_avatar", re.I)
_TAG_RE = re.compile(r'"([^"]+)"|(\S+)')
_HIGHLIGHT_RE = re.compile(r"</?b>")
_PRESET_RE = re.compile(r"^(mp3|aac|opus|abr)_(\d+)(k)?", re.I)


# ---- value helpers -------------------------------------------------------------
# (kept local rather than imported from another site's package so this module
# stands alone — the open-source kit ships it verbatim)

def to_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def iso_date(value):
    """'2014-06-20T00:00:00Z' -> '2014-06-20'; junk -> None."""
    if not value or not isinstance(value, str):
        return None
    return value[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", value) else None


def iso_datetime(value):
    """'2023-05-17T14:41:20Z' -> same (UTC, second precision); junk -> None."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def duration_text(ms):
    """378488 -> '6:18'; 8617898 -> '2:23:37'."""
    ms = to_int(ms)
    if ms is None:
        return None
    hours, rest = divmod(ms // 1000, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def text(value):
    """Trimmed string or None ('' / whitespace -> None)."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def image(url):
    """sndcdn image (any size suffix) -> {link (500x500), original_link};
    SoundCloud's grey default avatar -> None."""
    if not isinstance(url, str) or not url or _DEFAULT_AVATAR_RE.search(url):
        return None
    if not _SIZE_RE.search(url):
        return {"link": url, "original_link": None}
    if "//al.sndcdn.com/" in url:        # generated station collage: 500x500 only
        return {"link": _SIZE_RE.sub(r"-t500x500.\2", url, count=1), "original_link": None}
    return {
        "link": _SIZE_RE.sub(r"-t500x500.\2", url, count=1),
        "original_link": _SIZE_RE.sub(r"-original.\2", url, count=1),
    }


def tags(tag_list):
    """'"Top 50" Charts US' -> ['Top 50', 'Charts', 'US']; machine tags
    (soundcloud:source=web-record) are dropped."""
    if not isinstance(tag_list, str):
        return []
    out = []
    for quoted, bare in _TAG_RE.findall(tag_list):
        tag = (quoted or bare).strip()
        if tag and not re.match(r"^[\w-]+:[\w-]+=", tag) and tag not in out:
            out.append(tag)
    return out


def station_link(permalink):
    return f"{SITE}/discover/sets/{permalink}" if permalink else None


def visuals_link(visuals):
    """{visuals: [{visual_url}]} (profile / track banner) -> the first link."""
    if not isinstance(visuals, dict):
        return None
    for v in visuals.get("visuals") or []:
        if isinstance(v, dict) and v.get("visual_url"):
            return v["visual_url"]
    return None


def purchase(obj):
    link = text(obj.get("purchase_url"))
    if not link:
        return None
    return {"title": text(obj.get("purchase_title")), "link": link}


def lower(value):
    return value.lower() if isinstance(value, str) and value else None


def bool_or_none(value):
    return value if isinstance(value, bool) else None


# ---- users -------------------------------------------------------------------------

def user_summary(obj):
    """The compact user nested in tracks, playlists, comments."""
    if not isinstance(obj, dict) or not obj.get("id"):
        return None
    badges = obj.get("badges") or {}
    return {
        "id": obj.get("id"),
        "username": text(obj.get("username")),
        "link": text(obj.get("permalink_url")),
        "permalink": text(obj.get("permalink")),
        "full_name": text(obj.get("full_name")),
        "avatar": image(obj.get("avatar_url")),
        "city": text(obj.get("city")),
        "country_code": text(obj.get("country_code")),
        "followers_count": to_int(obj.get("followers_count")),
        "is_verified": bool(obj.get("verified") or badges.get("verified")),
    }


def user(obj):
    """A full user (details, followers, likers, search hits…)."""
    if not isinstance(obj, dict) or not obj.get("id"):
        return None
    badges = obj.get("badges") or {}
    subscription = ((obj.get("creator_subscription") or {}).get("product") or {}).get("id")
    return {
        "id": obj.get("id"),
        "username": text(obj.get("username")),
        "link": text(obj.get("permalink_url")),
        "permalink": text(obj.get("permalink")),
        "full_name": text(obj.get("full_name")),
        "description": text(obj.get("description")),
        "city": text(obj.get("city")),
        "country_code": text(obj.get("country_code")),
        "stats": {
            "followers": to_int(obj.get("followers_count")),
            "followings": to_int(obj.get("followings_count")),
            "tracks": to_int(obj.get("track_count")),
            "playlists": to_int(obj.get("playlist_count")),
            "likes": to_int(obj.get("likes_count")),
            "playlist_likes": to_int(obj.get("playlist_likes_count")),
            "reposts": to_int(obj.get("reposts_count")),
            "comments": to_int(obj.get("comments_count")),
        },
        "avatar": image(obj.get("avatar_url")),
        "banner_link": visuals_link(obj.get("visuals")),
        "is_verified": bool(obj.get("verified") or badges.get("verified")),
        "is_pro": bool_or_none(badges.get("pro")),
        "is_pro_unlimited": bool_or_none(badges.get("pro_unlimited")),
        "is_creator_mid_tier": bool_or_none(badges.get("creator_mid_tier")),
        "subscription_plan": text(subscription),
        "station_link": station_link(obj.get("station_permalink")),
        "created_at": iso_datetime(obj.get("created_at")),
        "updated_at": iso_datetime(obj.get("last_modified")),
    }


def web_profile(obj):
    """A profile's external link (website, Instagram, Spotify, …)."""
    if not isinstance(obj, dict) or not obj.get("url"):
        return None
    username = text(obj.get("username"))
    return {
        "network": lower(obj.get("network")),
        "title": text(obj.get("title")),
        "username": None if username == obj.get("url") else username,
        "link": obj.get("url"),
    }


# ---- tracks ------------------------------------------------------------------------

def rights_line(value):
    """'℗ 2014 Warner Music UK' stays; a bare '℗' / '©' -> None."""
    value = text(value)
    return value if value and value.strip("℗©(pPcC) ") else None


def publisher(meta):
    """publisher_metadata (label-supplied rights data) -> clean object;
    None when it only carries the id/urn echo."""
    if not isinstance(meta, dict):
        return None
    out = {
        "artist": text(meta.get("artist")),
        "album_title": text(meta.get("album_title")),
        "release_title": text(meta.get("release_title")),
        "isrc": text(meta.get("isrc")),
        "upc": text(meta.get("upc_or_ean")),
        "publisher": text(meta.get("publisher")),
        "writers": text(meta.get("writer_composer")),
        "p_line": rights_line(meta.get("p_line_for_display") or meta.get("p_line")),
        "c_line": rights_line(meta.get("c_line_for_display") or meta.get("c_line")),
        "is_explicit": bool_or_none(meta.get("explicit")),
        "has_music": bool_or_none(meta.get("contains_music")),
    }
    # every track echoes {id, urn, contains_music}: only real rights data counts
    return out if any(v is not None for k, v in out.items() if k != "has_music") else None


def track(obj):
    """A full track. Playlist / station stubs ({id, kind, policy}) come out
    with nulls — SoundCloud no longer serves them (deleted / region-locked)."""
    if not isinstance(obj, dict) or not obj.get("id"):
        return None
    policy = lower(obj.get("policy"))
    duration = to_int(obj.get("duration"))
    full = to_int(obj.get("full_duration")) or duration
    if policy != "snip" and full:
        duration = full               # the two differ by a few ms of transcoding only
    return {
        "id": obj.get("id"),
        "title": text(obj.get("title")),
        "link": text(obj.get("permalink_url")),
        "permalink": text(obj.get("permalink")),
        "secret_token": text(obj.get("secret_token")),
        "description": text(obj.get("description")),
        "caption": text(obj.get("caption")),
        "genre": text(obj.get("genre")),
        "tags": tags(obj.get("tag_list")),
        "label": text(obj.get("label_name")),
        "license": text(obj.get("license")),
        "duration_ms": full,
        "duration": duration_text(full),
        "playable_duration_ms": duration,
        "release_date": iso_date(obj.get("release_date")),
        "stats": {
            "plays": to_int(obj.get("playback_count")),
            "likes": to_int(obj.get("likes_count")),
            "reposts": to_int(obj.get("reposts_count")),
            "comments": to_int(obj.get("comment_count")),
            "downloads": to_int(obj.get("download_count")),
        },
        "user": user_summary(obj.get("user")),
        "artwork": image(obj.get("artwork_url")),
        "banner_link": visuals_link(obj.get("visuals")),
        "publisher": publisher(obj.get("publisher_metadata")),
        "purchase": purchase(obj),
        "policy": policy,
        "monetization_model": lower(obj.get("monetization_model")),
        "is_preview_only": policy == "snip" if policy else None,
        "is_streamable": bool_or_none(obj.get("streamable")),
        "is_downloadable": bool(obj.get("downloadable") and obj.get("has_downloads_left")) if "downloadable" in obj else None,
        "is_commentable": bool_or_none(obj.get("commentable")),
        "is_public": bool_or_none(obj.get("public")),
        "sharing": text(obj.get("sharing")),
        "embeddable_by": text(obj.get("embeddable_by")),
        "waveform_link": text(obj.get("waveform_url")),
        "station_link": station_link(obj.get("station_permalink")),
        "created_at": iso_datetime(obj.get("created_at")),
        "updated_at": iso_datetime(obj.get("last_modified")),
    }


def track_summary(obj):
    """The compact track attached to a user's comments."""
    if not isinstance(obj, dict) or not obj.get("id"):
        return None
    duration = to_int(obj.get("full_duration") or obj.get("duration"))
    return {
        "id": obj.get("id"),
        "title": text(obj.get("title")),
        "link": text(obj.get("permalink_url")),
        "duration_ms": duration,
        "duration": duration_text(duration),
        "artwork": image(obj.get("artwork_url")),
        "user": user_summary(obj.get("user")),
    }


def numbered(tracks, field="position", start=0, parser=None):
    """Parsed tracks stamped with their 1-based place (position / rank)."""
    parser = parser or track
    out = []
    for i, obj in enumerate(tracks or []):
        parsed = parser(obj)
        if parsed is not None:
            out.append({field: start + i + 1, **parsed})
    return out


# ---- playlists ---------------------------------------------------------------------

def playlist_type(obj):
    """set_type ('album' | 'ep' | 'single' | 'compilation' | '') + is_album
    -> 'album' / 'ep' / 'single' / 'compilation' / 'playlist'."""
    set_type = lower(obj.get("set_type"))
    if set_type:
        return set_type
    return "album" if obj.get("is_album") else "playlist"


def playlist(obj):
    """A playlist or album (without its track list)."""
    if not isinstance(obj, dict) or not obj.get("id"):
        return None
    duration = to_int(obj.get("duration"))
    return {
        "id": obj.get("id"),
        "title": text(obj.get("title")),
        "link": text(obj.get("permalink_url")),
        "permalink": text(obj.get("permalink")),
        "secret_token": text(obj.get("secret_token")),
        "type": playlist_type(obj),
        "description": text(obj.get("description")),
        "genre": text(obj.get("genre")),
        "tags": tags(obj.get("tag_list")),
        "label": text(obj.get("label_name")),
        "license": text(obj.get("license")),
        "track_count": to_int(obj.get("track_count")),
        "duration_ms": duration,
        "duration": duration_text(duration),
        "release_date": iso_date(obj.get("release_date")),
        "stats": {
            "likes": to_int(obj.get("likes_count")),
            "reposts": to_int(obj.get("reposts_count")),
        },
        "user": user_summary(obj.get("user")),
        "artwork": image(obj.get("artwork_url")),
        "purchase": purchase(obj),
        "is_public": bool_or_none(obj.get("public")),
        "sharing": text(obj.get("sharing")),
        "embeddable_by": text(obj.get("embeddable_by")),
        "published_at": iso_datetime(obj.get("published_at")),
        "created_at": iso_datetime(obj.get("created_at")),
        "updated_at": iso_datetime(obj.get("last_modified")),
    }


def station_type(obj):
    """'artist-stations:3685019' -> 'artist_station', 'track-stations:…' ->
    'track_station', 'trending-by-genre:trap' -> 'trending_by_genre'."""
    prefix = str(obj.get("permalink") or obj.get("urn") or "").split(":")
    prefix = prefix[-2] if len(prefix) >= 2 else ""
    return {"artist-stations": "artist_station", "track-stations": "track_station"}.get(
        prefix, prefix.replace("-", "_") or lower(obj.get("playlist_type")))


def system_playlist(obj):
    """A SoundCloud-made playlist: artist / track station, trending-by-genre."""
    if not isinstance(obj, dict) or not (obj.get("urn") or obj.get("id")):
        return None
    return {
        "id": text(obj.get("permalink")) or text(str(obj.get("id") or "")),
        "title": text(obj.get("title")),
        "link": text(obj.get("permalink_url")),
        "station_type": station_type(obj),
        "description": text(obj.get("description")),
        "short_title": text(obj.get("short_title")),
        "short_description": text(obj.get("short_description")),
        "track_count": len(obj["tracks"]) if isinstance(obj.get("tracks"), list) else None,
        "stats": {"likes": to_int(obj.get("likes_count"))},
        "user": user_summary(obj.get("user")),
        "artwork": image(obj.get("artwork_url") or obj.get("calculated_artwork_url")),
        "is_public": bool_or_none(obj.get("is_public")),
        "updated_at": iso_datetime(obj.get("last_updated")),
    }


# ---- comments / activity -------------------------------------------------------------

def comment(obj):
    if not isinstance(obj, dict) or not obj.get("id"):
        return None
    at = to_int(obj.get("timestamp"))
    return {
        "id": obj.get("id"),
        "text": text(obj.get("body")),
        "timestamp_ms": at,
        "timestamp": duration_text(at),
        "user": user_summary(obj.get("user")),
        "created_at": iso_datetime(obj.get("created_at")),
    }


def item(obj):
    """Any typed entity in a mixed list -> {type, …parsed fields}."""
    if not isinstance(obj, dict):
        return None
    kind = obj.get("kind")
    if kind == "track":
        parsed = track(obj)
    elif kind == "user":
        parsed = user(obj)
    elif kind == "playlist":
        parsed = playlist(obj)
    elif kind == "system-playlist":
        parsed = system_playlist(obj)
    else:
        return None
    if parsed is None:
        return None
    kind_name = playlist_type(obj) if kind == "playlist" else ("station" if kind == "system-playlist" else kind)
    return {"type": kind_name, **parsed}


def items(objs, parser=item):
    return [p for p in (parser(o) for o in objs or []) if p is not None]


def activity(obj):
    """A profile feed entry (/stream/users/{id}[/reposts]) or a like:
    {type, created_at, caption, track | playlist}."""
    if not isinstance(obj, dict):
        return None
    kind = lower(obj.get("type")) or lower(obj.get("kind"))
    entity = obj.get("track") or obj.get("playlist")
    if not isinstance(entity, dict):
        return None
    is_track = isinstance(obj.get("track"), dict)
    if kind == "like":
        kind = "track_like" if is_track else "playlist_like"
    return {
        "type": (kind or ("track" if is_track else "playlist")).replace("-", "_"),
        "created_at": iso_datetime(obj.get("created_at")),
        "caption": text(obj.get("caption")),
        "track": track(entity) if is_track else None,
        "playlist": playlist(entity) if not is_track else None,
    }


# ---- search / discovery -----------------------------------------------------------------

def facets(body, name):
    """Search facets ({name, facets: [{value, count}]}) -> [{value, count}]."""
    for block in (body or {}).get("facets") or []:
        if isinstance(block, dict) and block.get("name") == name:
            return [{"value": f.get("value"), "count": to_int(f.get("count"))}
                    for f in block.get("facets") or [] if isinstance(f, dict) and f.get("value")]
    return []


def unhighlight(value):
    return _HIGHLIGHT_RE.sub("", value).strip() if isinstance(value, str) else None


def selection(obj):
    """A /mixed-selections or /charts/selections shelf."""
    if not isinstance(obj, dict):
        return None
    urn = text(obj.get("urn")) or text(str(obj.get("id") or ""))
    return {
        "id": urn.split(":")[-1] if urn else None,
        "title": text(obj.get("title")),
        "description": text(obj.get("description")),
        "items": items(((obj.get("items") or {}).get("collection"))),
        "updated_at": iso_datetime(obj.get("last_updated")),
    }


# ---- streams -----------------------------------------------------------------------

def link_expiry(link):
    """Signed CDN link -> its expiry (UTC ISO): the `expires=` param, else
    the CloudFront policy's DateLessThan epoch."""
    try:
        query = parse_qs(urlparse(link).query)
    except Exception:
        return None
    epoch = to_int((query.get("expires") or query.get("Expires") or [None])[0])
    if epoch is None and query.get("Policy"):
        raw = query["Policy"][0].replace("-", "+").replace("_", "=").replace("~", "/")
        try:
            policy = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
            epoch = to_int(policy["Statement"][0]["Condition"]["DateLessThan"]["AWS:EpochTime"])
        except Exception:
            epoch = None
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def transcoding_info(tc):
    """A media transcoding -> {format, bitrate_kbps, protocol, quality,
    mime_type, is_preview}."""
    preset = tc.get("preset") or ""
    m = _PRESET_RE.match(preset)
    fmt = m.group(1).lower() if m else None
    bitrate = None
    if m and m.group(3):
        bitrate = to_int(m.group(2))
    elif fmt == "mp3":
        bitrate = 128                     # mp3_1_0 / mp3_0_1: the 128 kbps legacy stream
    elif fmt == "opus":
        bitrate = 64
    fmt_info = tc.get("format") or {}
    return {
        "format": fmt,
        "bitrate_kbps": bitrate,
        "protocol": lower(fmt_info.get("protocol")),
        "quality": lower(tc.get("quality")),
        "mime_type": text(fmt_info.get("mime_type")),
        "is_preview": bool(tc.get("snipped")),
    }


def waveform(body, samples=None):
    """wave.sndcdn.com JSON {width, height, samples[]} -> {width, height,
    max_height, samples (0..1 floats), optionally downsampled}."""
    raw = [to_int(s) or 0 for s in (body or {}).get("samples") or []]
    height = to_int((body or {}).get("height")) or (max(raw) if raw else None)
    if samples and raw and samples < len(raw):
        step = len(raw) / samples
        raw = [max(raw[int(i * step):max(int((i + 1) * step), int(i * step) + 1)]) for i in range(samples)]
    return {
        "width": to_int((body or {}).get("width")),
        "max_height": height,
        "sample_count": len(raw),
        "samples": [round(s / height, 4) if height else 0 for s in raw],
    }


# ---- pagination ------------------------------------------------------------------------

def pagination(page, per_page, has_more, total_count=None, max_results=None):
    """The block route_glue.paginate() lifts into the flat gateway shape.
    With a total, total_pages is computed (and capped to what SoundCloud
    will actually serve); without one, "this page + 1" while more exist."""
    if total_count is not None and per_page:
        reachable = min(int(total_count), max_results) if max_results else int(total_count)
        total_pages = (reachable + int(per_page) - 1) // int(per_page)
    else:
        total_pages = page + 1 if has_more else page
    return {"page": page, "items_per_page": per_page,
            "total_pages": total_pages, "total_count": total_count}


def cursor_page(entries, body, key):
    """A cursor-paged list response: {key: entries, next_cursor, has_more}."""
    from soundcloud.fetch import collection, next_offset
    # judged on the raw rows: a page whose rows all fail to parse (deleted
    # tracks, unknown kinds) must not end the pagination early
    nxt = next_offset(body) if (entries or collection(body)) else None
    return {key: entries, "next_cursor": nxt, "has_more": bool(nxt)}

