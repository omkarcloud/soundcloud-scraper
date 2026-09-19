"""/soundcloud/users/* — profile details (with social links), tracks,
popular tracks, playlists / albums, likes, reposts, activity feed,
followers, followings, comments, related artists, spotlight, social links
and the artist station."""
from soundcloud import parsers as P
from soundcloud import refs
from soundcloud.fetch import (api_get, collection, fetch_object, object_id,
                              tracks_by_ids)
from soundcloud.shared import cursor_list, paged, station as station_body


def _web_profiles(uid):
    # the bare numeric id answers 400 here: only the URN form works
    body = api_get(f"/users/soundcloud:users:{uid}/web-profiles", label=f"social links of user {uid}")
    return P.items(body if isinstance(body, list) else [], P.web_profile)


def user_details(user):
    """Full profile: bio, location, counters, badges, avatar and banner,
    plus the social / website links shown on the profile."""
    obj = fetch_object(user, "user")
    links = _web_profiles(obj["id"])
    return {**P.user(obj), "social_links": links}


def user_social_links(user):
    """Only the profile's website / social links (Instagram, Spotify, …)."""
    uid = object_id(user, "user")
    return {"user_id": uid, "social_links": _web_profiles(uid)}


def user_tracks(user, cursor=None, limit=50):
    """The user's uploads, newest first."""
    uid = object_id(user, "user")
    return {"user_id": uid, **cursor_list(f"/users/{uid}/tracks", cursor, limit, "tracks",
                                          parser=P.track, label=f"tracks of user {uid}")}


def user_popular_tracks(user):
    """The profile's "Popular tracks" (all of them in one response)."""
    uid = object_id(user, "user")
    body = api_get(f"/users/{uid}/toptracks", {"limit": 50}, label=f"popular tracks of user {uid}")
    return {"user_id": uid, "tracks": P.numbered(collection(body), "rank")}


def user_playlists(user, type="all", page=1, limit=20):
    """The user's playlists and/or albums (type=all | playlists | albums)."""
    uid = object_id(user, "user")
    tail = refs.PLAYLIST_KINDS[type][1]
    _, items, pagination = paged(f"/users/{uid}/{tail}", page, limit, parser=P.playlist,
                                 label=f"playlists of user {uid}")
    return {"user_id": uid, "type": type, "playlists": items, "pagination": pagination}


def user_likes(user, type="all", cursor=None, limit=50):
    """Tracks and/or playlists the user liked (type=all | tracks |
    playlists), most recent first, each with liked_at."""
    uid = object_id(user, "user")
    tail = refs.LIKE_KINDS[type]
    page = cursor_list(f"/users/{uid}/{tail}", cursor, limit, "likes", parser=P.activity,
                       label=f"likes of user {uid}")
    page["likes"] = [_liked(x) for x in page["likes"]]
    return {"user_id": uid, "type": type, **page}


def _liked(entry):
    """activity() row of a like -> {type, liked_at, track | playlist}."""
    return {"type": "track" if entry["track"] else "playlist", "liked_at": entry["created_at"],
            "track": entry["track"], "playlist": entry["playlist"]}


def user_reposts(user, cursor=None, limit=50):
    """Tracks and playlists the user reposted, most recent first."""
    uid = object_id(user, "user")
    page = cursor_list(f"/stream/users/{uid}/reposts", cursor, limit, "reposts", parser=P.activity,
                       label=f"reposts of user {uid}")
    page["reposts"] = [_reposted(x) for x in page["reposts"]]
    return {"user_id": uid, **page}


def _reposted(entry):
    return {"type": "track" if entry["track"] else "playlist", "reposted_at": entry["created_at"],
            "caption": entry["caption"], "track": entry["track"], "playlist": entry["playlist"]}


def user_activity(user, cursor=None, limit=50):
    """The profile's "All" feed: uploads, playlist posts and reposts, newest
    first (type = track | playlist | track_repost | playlist_repost)."""
    uid = object_id(user, "user")
    return {"user_id": uid, **cursor_list(f"/stream/users/{uid}", cursor, limit, "activity",
                                          parser=P.activity, label=f"activity of user {uid}")}


def user_followers(user, cursor=None, limit=50):
    """Users following this user, most recent first."""
    uid = object_id(user, "user")
    return {"user_id": uid, **cursor_list(f"/users/{uid}/followers", cursor, limit, "users",
                                          parser=P.user, label=f"followers of user {uid}")}


def user_followings(user, cursor=None, limit=50):
    """Users this user follows, most recent first."""
    uid = object_id(user, "user")
    return {"user_id": uid, **cursor_list(f"/users/{uid}/followings", cursor, limit, "users",
                                          parser=P.user, label=f"followings of user {uid}")}


def user_comments(user, cursor=None, limit=50):
    """Comments the user posted, newest first, each with the track it is on."""
    uid = object_id(user, "user")

    def with_tracks(rows):
        # comment rows only carry track_id: attach the tracks in one batch
        found = tracks_by_ids([r.get("track_id") for r in rows if isinstance(r, dict)])
        return [{**r, "_track": found.get(r.get("track_id"))} for r in rows if isinstance(r, dict)]

    def parse(row):
        parsed = P.comment(row)
        if parsed is None:
            return None
        parsed.pop("user", None)      # always the profile owner
        # a deleted track still gets the full (null) summary shape
        return {**parsed, "track": P.track_summary(row.get("_track") or {"id": row.get("track_id")})}

    return {"user_id": uid, **cursor_list(f"/users/{uid}/comments", cursor, limit, "comments",
                                          parser=parse, prepare=with_tracks,
                                          label=f"comments of user {uid}")}


def user_related_artists(user):
    """Artists SoundCloud relates to this one ("Fans also like")."""
    uid = object_id(user, "user")
    body = api_get(f"/users/{uid}/relatedartists", {"limit": 50}, label=f"related artists of user {uid}")
    return {"user_id": uid, "users": P.items(collection(body), P.user)}


def user_spotlight(user):
    """The tracks / playlists pinned to the top of the profile (Pro users)."""
    uid = object_id(user, "user")
    body = api_get(f"/users/{uid}/spotlight", label=f"spotlight of user {uid}")
    return {"user_id": uid, "items": P.items(collection(body))}


def user_station(user, limit=50):
    """The artist station: an endless mix SoundCloud seeds from this artist."""
    uid = object_id(user, "user")
    urn = f"soundcloud:system-playlists:artist-stations:{uid}"
    return station_body(api_get(f"/system-playlists/{urn}", label=f"station of user {uid}"), limit)
