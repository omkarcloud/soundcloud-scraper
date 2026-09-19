"""/soundcloud/search/* — everything, tracks, users, playlists / albums and
auto-complete, over api-v2 /search. SoundCloud stops returning rows at
offset 300 whatever `total_results` says, so pages end there (shared.paged
max_results); `count` still reports SoundCloud's full total."""
from soundcloud import parsers as P
from soundcloud import refs
from soundcloud.fetch import api_get, collection, run_parallel
from soundcloud.shared import paged

MAX = refs.SEARCH_MAX_RESULTS


def _filters(genre_or_tag=None, duration=None, uploaded_within=None, license=None, place=None):
    return {
        "filter.genre_or_tag": genre_or_tag,
        "filter.duration": duration,
        "filter.created_at": uploaded_within,
        "filter.license": license,
        "filter.place": place,
    }


def search_all(query, page=1, limit=20):
    """Tracks, users, playlists and albums in one relevance-ranked list;
    each result carries `type`."""
    _, results, pagination = paged("/search", page, limit, params={"q": query}, max_results=MAX,
                                   label="search")
    return {"query": query, "results": results, "pagination": pagination}


def search_tracks(query, page=1, limit=20, genre_or_tag=None, duration=None, uploaded_within=None,
                  license=None):
    """Tracks, with SoundCloud's genre facet (top genres among all hits)."""
    params = {"q": query, "facet": "genre", **_filters(genre_or_tag, duration, uploaded_within, license)}
    body, tracks, pagination = paged("/search/tracks", page, limit, params=params, parser=P.track,
                                     max_results=MAX, label="track search")
    return {"query": query, "tracks": tracks, "genres": P.facets(body, "genre"),
            "pagination": pagination}


def search_users(query, page=1, limit=20, place=None):
    """Users / artists, with the place facet (top cities among all hits;
    pass one back as `place`)."""
    params = {"q": query, "facet": "place", **_filters(place=place)}
    body, users, pagination = paged("/search/users", page, limit, params=params, parser=P.user,
                                    max_results=MAX, label="user search")
    return {"query": query, "users": users, "places": P.facets(body, "place"),
            "pagination": pagination}


def search_playlists(query, type="all", page=1, limit=20, genre_or_tag=None):
    """Playlists and/or albums (type=all | playlists | albums), with the
    genre facet."""
    path = refs.PLAYLIST_KINDS[type][0]
    params = {"q": query, "facet": "genre", **_filters(genre_or_tag)}
    body, playlists, pagination = paged(path, page, limit, params=params, parser=P.playlist,
                                        max_results=MAX, label="playlist search")
    return {"query": query, "type": type, "playlists": playlists, "genres": P.facets(body, "genre"),
            "pagination": pagination}


def auto_complete(query):
    """Search suggestions as the site shows them while typing, plus
    matching tags."""
    queries, tags = run_parallel([
        lambda: api_get("/search/queries", {"q": query, "limit": 10}, label="suggestions"),
        lambda: api_get("/search/suggest/tags", {"q": query, "limit": 10}, label="tag suggestions"),
    ])
    suggestions = []
    for row in collection(queries):
        value = P.text(row.get("output") or row.get("query")) if isinstance(row, dict) else None
        if value and value not in suggestions:
            suggestions.append(value)
    tag_list = []
    for row in (tags or {}).get("suggestions") or []:
        if isinstance(row, dict):
            value = P.text(row.get("id")) or P.unhighlight(row.get("query"))
            if value and value not in tag_list:
                tag_list.append(value)
    return {"query": query, "suggestions": suggestions, "tags": tag_list}
