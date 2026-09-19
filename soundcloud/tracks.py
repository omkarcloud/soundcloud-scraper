"""/soundcloud/tracks/* — track details, batch, playable stream links,
waveform, comments, likers, reposters, related tracks, the playlists /
albums a track is in, and its station."""
from soundcloud import parsers as P
from soundcloud import refs
from soundcloud.fetch import (SoundCloudNotFound, api_get, collection, fetch_object, object_id,
                              page_get, run_parallel, tracks_by_ids)
from soundcloud.shared import cursor_list, paged, station as station_body

RELATED_MAX = 50              # /related serves one page of at most 50


def track_details(track):
    """Full track details. Go+ / label tracks streamed as 30 s previews
    outside their markets carry policy=snip and is_preview_only=true."""
    return P.track(fetch_object(track, "track"))


def track_batch(tracks):
    """Up to 50 tracks in one call (ids, URNs or links, mixed). Tracks
    SoundCloud does not serve are listed in not_found (as given)."""
    def to_id(ref):
        try:
            return object_id(ref, "track")
        except SoundCloudNotFound:
            return None

    ids = run_parallel([lambda r=r: to_id(r) for r in tracks])
    found = tracks_by_ids([i for i in ids if i])
    out, not_found = [], []
    for ref, tid in zip(tracks, ids):
        obj = found.get(tid) if tid else None
        if obj:
            out.append(P.track(obj))
        else:
            not_found.append(ref["id"] or ref["link"])
    return {"tracks": out, "not_found": not_found}


def _stream_link(tc, authorization):
    """Resolve one media transcoding to its signed CDN link (None if
    SoundCloud refuses that rendition, e.g. abr_sq -> 404)."""
    try:
        body = api_get("", {"track_authorization": authorization}, url=tc["url"], label="stream link")
    except SoundCloudNotFound:
        return None
    return (body or {}).get("url") if isinstance(body, dict) else None


def track_stream(track):
    """Playable audio links for every rendition SoundCloud offers the
    anonymous web player: progressive MP3 (a plain file link), HLS MP3 /
    AAC playlists (m3u8). Links are signed and expire (expires_at, ~a few
    minutes to hours). Go+ tracks (policy=snip) only offer a 30 s preview
    outside SoundCloud's paid tier; is_preview says so per stream."""
    obj = fetch_object(track, "track")
    authorization = obj.get("track_authorization")
    transcodings = [tc for tc in ((obj.get("media") or {}).get("transcodings") or [])
                    if isinstance(tc, dict) and tc.get("url")]
    links = run_parallel([lambda tc=tc: _stream_link(tc, authorization) for tc in transcodings])
    streams = []
    for tc, link in zip(transcodings, links):
        if not link:
            continue
        streams.append({**P.transcoding_info(tc), "link": link, "expires_at": P.link_expiry(link)})
    # progressive MP3 first (directly downloadable), then by bitrate
    streams.sort(key=lambda s: (s["protocol"] != "progressive", -(s["bitrate_kbps"] or 0)))
    parsed = P.track(obj)
    return {
        "id": parsed["id"],
        "title": parsed["title"],
        "link": parsed["link"],
        "duration_ms": parsed["duration_ms"],
        "playable_duration_ms": parsed["playable_duration_ms"],
        "policy": parsed["policy"],
        "is_preview_only": parsed["is_preview_only"],
        "is_downloadable": parsed["is_downloadable"],
        "streams": streams,
    }


def track_waveform(track, samples=None):
    """The waveform SoundCloud draws under the player: amplitude samples
    normalised to 0..1 (1800 by default; `samples` downsamples by max)."""
    obj = fetch_object(track, "track")
    link = obj.get("waveform_url")
    if not link:
        raise SoundCloudNotFound(f"track {obj.get('id')} has no waveform")
    resp = page_get(link, headers={"accept": "application/json"}, label="waveform")
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200 or not isinstance(body, dict):
        raise SoundCloudNotFound(f"waveform of track {obj.get('id')} is unavailable")
    return {"track_id": obj.get("id"), "waveform_link": link, **P.waveform(body, samples)}


def track_comments(track, page=1, limit=50):
    """Timed comments, newest first (timestamp = position in the track).
    Replies are plain comments starting with @username."""
    tid = object_id(track, "track")
    _, items, pagination = paged(f"/tracks/{tid}/comments", page, limit, params={"threaded": 0},
                                 parser=P.comment, label=f"comments of track {tid}")
    return {"track_id": tid, "comments": items, "pagination": pagination}


def track_likers(track, cursor=None, limit=50):
    """Users who liked the track, most recent first."""
    tid = object_id(track, "track")
    return {"track_id": tid, **cursor_list(f"/tracks/{tid}/likers", cursor, limit, "users",
                                           parser=P.user, label=f"likers of track {tid}")}


def track_reposters(track, cursor=None, limit=50):
    """Users who reposted the track, most recent first."""
    tid = object_id(track, "track")
    return {"track_id": tid, **cursor_list(f"/tracks/{tid}/reposters", cursor, limit, "users",
                                           parser=P.user, label=f"reposters of track {tid}")}


def related_tracks(track, limit=20):
    """SoundCloud's "Related tracks" (similar-sounds model, up to 50).
    Empty for preview-only (Go+) tracks."""
    tid = object_id(track, "track")
    body = api_get(f"/tracks/{tid}/related", {"limit": min(limit, RELATED_MAX)},
                   label=f"related tracks of {tid}")
    return {"track_id": tid, "tracks": P.items(collection(body), P.track)}


def track_playlists(track, type="all", page=1, limit=20):
    """Public playlists and/or albums (type=all | playlists | albums) that
    contain the track."""
    tid = object_id(track, "track")
    tail = refs.PLAYLIST_KINDS[type][2]
    _, items, pagination = paged(f"/tracks/{tid}/{tail}", page, limit, parser=P.playlist,
                                 label=f"playlists of track {tid}")
    return {"track_id": tid, "type": type, "playlists": items, "pagination": pagination}


def track_station(track, limit=50):
    """The track's station: an endless mix SoundCloud seeds from it."""
    tid = object_id(track, "track")
    urn = f"soundcloud:system-playlists:track-stations:{tid}"
    return station_body(api_get(f"/system-playlists/{urn}", label=f"station of track {tid}"), limit)
