"""/soundcloud/playlists/* — playlist / album details with hydrated tracks,
paged tracks, likers and reposters.

api-v2 returns a playlist's full id list but only the first few tracks in
full; the rest are {id, kind, policy} stubs, hydrated here through
/tracks?ids= (50 per call, in parallel; a private playlist's tracks need
its id + secret token alongside)."""
from soundcloud import parsers as P
from soundcloud.fetch import fetch_object, hydrate, object_id
from soundcloud.shared import cursor_list

DETAILS_TRACKS = 100


def _track_page(obj, start, size):
    entries = [t for t in obj.get("tracks") or [] if isinstance(t, dict)]
    chunk = hydrate(entries[start:start + size], obj.get("id"), obj.get("secret_token"))
    return P.numbered(chunk, "position", start=start), len(entries)


def playlist_details(playlist):
    """Playlist / album metadata and its first 100 tracks (numbered by
    position). Page through longer ones with /soundcloud/playlists/tracks."""
    obj = fetch_object(playlist, "playlist")
    tracks, total = _track_page(obj, 0, DETAILS_TRACKS)
    return {**P.playlist(obj), "tracks": tracks, "tracks_has_more": total > DETAILS_TRACKS}


def playlist_tracks(playlist, page=1, limit=50):
    """One page of a playlist's tracks, numbered by position."""
    obj = fetch_object(playlist, "playlist")
    start = (page - 1) * limit
    items, total = _track_page(obj, start, limit)
    pages = (total + limit - 1) // limit
    return {"playlist_id": obj.get("id"), "tracks": items,
            "pagination": {"page": page, "items_per_page": limit, "total_pages": pages,
                           "total_count": total}}


def playlist_likers(playlist, cursor=None, limit=50):
    """Users who liked the playlist, most recent first."""
    pid = object_id(playlist, "playlist")
    return {"playlist_id": pid, **cursor_list(f"/playlists/{pid}/likers", cursor, limit, "users",
                                              parser=P.user, label=f"likers of playlist {pid}")}


def playlist_reposters(playlist, cursor=None, limit=50):
    """Users who reposted the playlist, most recent first."""
    pid = object_id(playlist, "playlist")
    return {"playlist_id": pid, **cursor_list(f"/playlists/{pid}/reposters", cursor, limit, "users",
                                              parser=P.user, label=f"reposters of playlist {pid}")}
