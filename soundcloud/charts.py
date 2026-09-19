"""/soundcloud/charts/* and /soundcloud/discover/* — what SoundCloud
itself ranks and features, anonymously:

  * trending   api-v2 /charts?kind=trending&genre=all-music (the only live
               /charts combination: kind=top is gone (404), other genres
               404 and region= is a 400) — top 100 with scores;
  * top 50     the official "Music Charts" playlists (US and UK: all genres,
               New & Hot, Artist Pro and per-genre), from /charts/selections;
  * trending by genre  the "Trending by genre" system playlists on the
               Discover page (trap, hip-hop, pop, electronic, …);
  * discover   the Discover page shelves, SoundCloud's featured tracks and
               the newest uploads for any genre / tag.
"""
from soundcloud import parsers as P
from soundcloud import refs
from soundcloud.fetch import SoundCloudNotFound, api_get, collection, hydrate, tracks_by_ids
from soundcloud.shared import (chart_selections, cursor_list, mixed_selections, paged,
                               station as station_body)

TRENDING_MAX = 100


def trending_chart(page=1, limit=50):
    """SoundCloud's trending chart (all music), ranked, with SoundCloud's
    trending score. Refreshed daily (updated_at)."""
    body, rows, pagination = paged("/charts", page, limit,
                                   params={"kind": "trending", "genre": "soundcloud:genres:all-music"},
                                   parser=lambda r: r if isinstance(r, dict) else None,
                                   max_results=TRENDING_MAX, label="trending chart")
    start = (page - 1) * limit
    tracks = []
    for i, row in enumerate(rows):
        parsed = P.track(row.get("track"))
        if parsed:
            score = row.get("score")
            tracks.append({"rank": start + i + 1,
                           "score": round(score, 6) if isinstance(score, (int, float)) else None,
                           **parsed})
    return {"chart": "trending", "genre": "all-music",
            "updated_at": P.iso_datetime(body.get("last_updated")) if isinstance(body, dict) else None,
            "tracks": tracks, "pagination": pagination}


# ---- top 50 -------------------------------------------------------------------------

def _top50_catalog():
    """[{country, chart, playlist (raw)}] from the live chart selections."""
    urn_country = {v: k for k, v in refs.TOP50_COUNTRIES.items()}
    out = []
    for shelf in chart_selections():
        country = urn_country.get(shelf.get("urn"))
        if not country:
            continue
        for pl in ((shelf.get("items") or {}).get("collection") or []):
            if isinstance(pl, dict) and pl.get("id"):
                out.append({"country": country, "chart": pl.get("permalink"), "playlist": pl})
    return out


def _trending_genres():
    """[system playlist (raw)] of the Discover page's trending-by-genre shelf."""
    for shelf in mixed_selections():
        if str(shelf.get("urn") or "").endswith("trending-by-genre-playlists"):
            return [x for x in ((shelf.get("items") or {}).get("collection") or []) if isinstance(x, dict)]
    return []


def _genre_slug(system_playlist):
    return str(system_playlist.get("permalink") or system_playlist.get("urn") or "").split(":")[-1]


def chart_list():
    """Every chart this API serves: the Top 50 playlists per country and
    the trending-by-genre genres (values for `chart` / `genre`)."""
    top = []
    for row in _top50_catalog():
        pl = row["playlist"]
        top.append({"country": row["country"], "chart": row["chart"], "title": P.text(pl.get("title")),
                    "playlist_id": pl.get("id"), "link": P.text(pl.get("permalink_url")),
                    "track_count": P.to_int(pl.get("track_count")),
                    "updated_at": P.iso_datetime(pl.get("last_modified"))})
    genres = [{"genre": _genre_slug(sp), "title": P.text(sp.get("title")), "link": P.text(sp.get("permalink_url"))}
              for sp in _trending_genres()]
    return {"top_50": top, "trending_by_genre": genres}


def top_50_chart(country="US", chart="all-music-genres"):
    """An official SoundCloud Top 50 (weekly): country US or GB, chart
    all-music-genres | new-hot | artist-pro | hip-hop | pop | … (see
    /soundcloud/charts/list), all tracks ranked."""
    chart = refs.TOP50_CHART_ALIASES.get(chart, refs.slugify(chart))
    rows = [r for r in _top50_catalog() if r["country"] == country]
    match = next((r for r in rows if r["chart"] == chart), None)
    if not match:
        names = ", ".join(r["chart"] for r in rows) or "none right now"
        raise ValueError(f"unknown chart {chart!r} for {country}; one of: {names}")
    obj = api_get(f"/playlists/{match['playlist']['id']}", label=f"top 50 {country} {chart}")
    entries = hydrate([t for t in obj.get("tracks") or [] if isinstance(t, dict)], obj.get("id"))
    return {"country": country, "chart": chart, **P.playlist(obj), "tracks": P.numbered(entries, "rank")}


def trending_by_genre_chart(genre="all-genres", limit=50):
    """The Discover page's "Trending by genre" playlist for one genre
    (trap, hip-hop, pop, electronic, r-n-b, house, …; see /soundcloud/charts/list)."""
    genre = refs.TRENDING_GENRE_ALIASES.get(genre, refs.slugify(genre))
    known = [_genre_slug(sp) for sp in _trending_genres()]
    urn = f"soundcloud:system-playlists:trending-by-genre:{genre}"
    try:
        body = api_get(f"/system-playlists/{urn}", label=f"trending {genre}")
    except SoundCloudNotFound:
        raise ValueError(f"unknown genre {genre!r}; one of: {', '.join(known or refs.TRENDING_GENRES)}")
    return {"genre": genre, **station_body(body, limit)}


# ---- discover -----------------------------------------------------------------------

def discover_home():
    """The Discover page shelves: "Artists to watch out for", "Curated by
    SoundCloud", promo campaigns and "Trending by genre"."""
    return {"sections": [s for s in (P.selection(x) for x in mixed_selections()) if s]}


def discover_featured_tracks():
    """The tracks SoundCloud features on its front page right now."""
    body = api_get("/featured_tracks/front", label="featured tracks")
    rows = [r for r in collection(body) if isinstance(r, dict) and r.get("id")]
    full = tracks_by_ids([r["id"] for r in rows])      # front-page rows are partial
    return {"tracks": P.numbered([full.get(r["id"], r) for r in rows], "position")}


def discover_new_tracks(tag, cursor=None, limit=50):
    """The newest public uploads for a genre or tag (lofi, hiphoprap,
    techno, …), newest first."""
    return {"tag": tag, **cursor_list(f"/recent-tracks/{tag}", cursor, limit, "tracks",
                                      parser=P.track, label=f"new {tag} tracks")}
