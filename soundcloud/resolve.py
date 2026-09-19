"""/soundcloud/resolve and /soundcloud/embed — any SoundCloud link (track,
user, playlist / album, station, on.soundcloud.com short link) to its
object, and to its official embed player."""
from soundcloud import parsers as P
from soundcloud.fetch import SITE, SoundCloudNotFound, expand_short_link, page_get, resolve_link
from soundcloud.shared import station

STATION_TRACKS = 50


def resolve_link_details(link):
    """What a link points at: {type, …parsed object}. Stations come with
    their tracks; playlists without (see /soundcloud/playlists/details)."""
    obj = resolve_link(link)
    if isinstance(obj, dict) and obj.get("kind") == "system-playlist":
        return {"type": "station", **station(obj, STATION_TRACKS)}
    parsed = P.item(obj)
    if parsed is None:
        raise SoundCloudNotFound(f"{link} does not point at a track, user, playlist or station")
    return parsed


def embed_player(link):
    """oEmbed: the iframe player HTML plus title, author and thumbnail."""
    if link.startswith("https://on.soundcloud.com/"):
        link = expand_short_link(link)
    resp = page_get(SITE + "/oembed", {"url": link, "format": "json"},
                    headers={"accept": "application/json"}, label="embed")
    if resp.status_code == 404:
        raise SoundCloudNotFound(f"{link} is not a public, embeddable SoundCloud page")
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200 or not isinstance(body, dict):
        raise SoundCloudNotFound(f"no embed player for {link} (HTTP {resp.status_code})")
    return {
        "title": P.text(body.get("title")),
        "link": link,
        "author": {"name": P.text(body.get("author_name")), "link": P.text(body.get("author_url"))},
        "description": P.text(body.get("description")),
        "thumbnail_link": P.text(body.get("thumbnail_url")),
        "html": P.text(body.get("html")),
        "width": body.get("width"),
        "height": P.to_int(body.get("height")),
    }
