"""The 42 SoundCloud endpoints. Every path is served with and without the
`/soundcloud` prefix, so code generated against the hosted API on RapidAPI
(paths like /tracks/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in soundcloud/schemas.py
(the same ones the hosted API uses): ONE param per input — `track`,
`user` and `playlist` each take a numeric id, a URN, a permalink path or a
soundcloud.com / on.soundcloud.com link. Unknown params are rejected with a
400 so typos surface.

Two pagination styles, matching what SoundCloud itself allows: numeric-offset
lists page with `page` + `limit` (count / total_pages / next / previous in
the response), opaque-cursor lists with `cursor` + `limit` (`next_cursor` in
the response)."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from soundcloud import charts, playlists, resolve, search, tracks, users
from soundcloud import schemas as S


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Beyoncé" would arrive as "BeyoncÃ©")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema, fn, paginated=False):
    """Validate the query, run the scraper, map errors: bad params -> 400,
    missing entity -> 404, transport/blocks -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:                # bad id / params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # upstream rejected the request
        return json_response({"error": f"soundcloud rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"soundcloud {label} failed: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


def mount(path, schema, fn, paginated=False):
    """Serve an endpoint at /path and /soundcloud/path."""
    def handler():
        return call(path.strip("/"), schema, fn, paginated)
    handler.__name__ = "soundcloud_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/soundcloud" + path, method="GET")(handler)


P = True   # paginated (page + limit)
ENDPOINTS = [
    ("/tracks/details", S.TrackSchema, tracks.track_details, False),
    ("/search/auto-complete", S.AutoCompleteSchema, search.auto_complete, False),
    ("/search/all", S.SearchAllSchema, search.search_all, P),
    ("/search/tracks", S.SearchTracksSchema, search.search_tracks, P),
    ("/search/users", S.SearchUsersSchema, search.search_users, P),
    ("/search/playlists", S.SearchPlaylistsSchema, search.search_playlists, P),
    ("/resolve", S.LinkSchema, resolve.resolve_link_details, False),
    ("/tracks/batch", S.TrackBatchSchema, tracks.track_batch, False),
    ("/tracks/stream", S.TrackSchema, tracks.track_stream, False),
    ("/tracks/comments", S.TrackCommentsSchema, tracks.track_comments, P),
    ("/tracks/likers", S.TrackCursorSchema, tracks.track_likers, False),
    ("/tracks/reposters", S.TrackCursorSchema, tracks.track_reposters, False),
    ("/tracks/related", S.TrackRelatedSchema, tracks.related_tracks, False),
    ("/tracks/playlists", S.TrackPlaylistsSchema, tracks.track_playlists, P),
    ("/tracks/station", S.TrackStationSchema, tracks.track_station, False),
    ("/tracks/waveform", S.TrackWaveformSchema, tracks.track_waveform, False),
    ("/embed", S.LinkSchema, resolve.embed_player, False),
    ("/users/details", S.UserSchema, users.user_details, False),
    ("/users/tracks", S.UserCursorSchema, users.user_tracks, False),
    ("/users/popular-tracks", S.UserSchema, users.user_popular_tracks, False),
    ("/users/playlists", S.UserPlaylistsSchema, users.user_playlists, P),
    ("/users/likes", S.UserLikesSchema, users.user_likes, False),
    ("/users/reposts", S.UserCursorSchema, users.user_reposts, False),
    ("/users/activity", S.UserCursorSchema, users.user_activity, False),
    ("/users/followers", S.UserCursorSchema, users.user_followers, False),
    ("/users/followings", S.UserCursorSchema, users.user_followings, False),
    ("/users/comments", S.UserCursorSchema, users.user_comments, False),
    ("/users/related-artists", S.UserSchema, users.user_related_artists, False),
    ("/users/spotlight", S.UserSchema, users.user_spotlight, False),
    ("/users/social-links", S.UserSchema, users.user_social_links, False),
    ("/users/station", S.UserStationSchema, users.user_station, False),
    ("/playlists/details", S.PlaylistSchema, playlists.playlist_details, False),
    ("/playlists/tracks", S.PlaylistTracksSchema, playlists.playlist_tracks, P),
    ("/playlists/likers", S.PlaylistCursorSchema, playlists.playlist_likers, False),
    ("/playlists/reposters", S.PlaylistCursorSchema, playlists.playlist_reposters, False),
    ("/charts/top-50", S.Top50Schema, charts.top_50_chart, False),
    ("/charts/trending", S.TrendingSchema, charts.trending_chart, P),
    ("/charts/trending-by-genre", S.TrendingByGenreSchema, charts.trending_by_genre_chart, False),
    ("/charts/list", S.EmptySchema, charts.chart_list, False),
    ("/discover/home", S.EmptySchema, charts.discover_home, False),
    ("/discover/featured-tracks", S.EmptySchema, charts.discover_featured_tracks, False),
    ("/discover/new-tracks", S.NewTracksSchema, charts.discover_new_tracks, False),
]

for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
