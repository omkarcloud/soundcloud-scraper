"""Live endpoint smoke tests: one call per /soundcloud/* route against a
running service, with example values proven to return data (2026-09-19).
The listing tooling (derive_facts.py) reads each route's FIRST call from
this file's AST as its working example, so the values stay literals.

Skipped unless SOUNDCLOUD_BASE points at a running service:

    ONLY_SCRAPER=soundcloud python run.py            # or any bottle runner
    SOUNDCLOUD_BASE=http://127.0.0.1:6002 python -m pytest soundcloud/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("SOUNDCLOUD_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set SOUNDCLOUD_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=180)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def test_tracks():
    assert call("/soundcloud/tracks/details", track="https://soundcloud.com/billieeilish/ocean-eyes")["stats"]["plays"]
    assert len(call("/soundcloud/tracks/batch", tracks="233719633,189525707")["tracks"]) == 2
    streams = call("/soundcloud/tracks/stream", track="https://soundcloud.com/billieeilish/ocean-eyes")["streams"]
    # renditions vary per track (Ocean Eyes: HLS only, no progressive MP3)
    assert streams and all(s["link"].startswith("https://") for s in streams)
    assert call("/soundcloud/tracks/waveform", track="https://soundcloud.com/billieeilish/ocean-eyes")["samples"]
    assert call("/soundcloud/tracks/comments", track="https://soundcloud.com/billieeilish/ocean-eyes")["comments"]
    assert call("/soundcloud/tracks/likers", track="https://soundcloud.com/billieeilish/ocean-eyes")["next_cursor"]
    assert call("/soundcloud/tracks/reposters", track="https://soundcloud.com/billieeilish/ocean-eyes")["users"]
    assert call("/soundcloud/tracks/related", track="https://soundcloud.com/billieeilish/ocean-eyes")["tracks"]
    assert call("/soundcloud/tracks/playlists", track="https://soundcloud.com/billieeilish/ocean-eyes")["playlists"]
    assert call("/soundcloud/tracks/station", track="https://soundcloud.com/billieeilish/ocean-eyes")["tracks"]
    # a label track: Go+ 30 s preview anonymously, with ISRC / UPC rights data
    assert call("/soundcloud/tracks/details", track="https://soundcloud.com/edsheeran/photograph")["publisher"]["isrc"]


def test_search():
    assert call("/soundcloud/search/all", query="billie eilish")["results"]
    assert call("/soundcloud/search/tracks", query="lofi hip hop")["tracks"]
    assert call("/soundcloud/search/users", query="post malone")["users"]
    assert call("/soundcloud/search/playlists", query="workout")["playlists"]
    assert call("/soundcloud/search/auto-complete", query="billie")["suggestions"]
    assert call("/soundcloud/search/tracks", query="lofi", genre_or_tag="lofi", uploaded_within="month")["tracks"]
    assert call("/soundcloud/search/playlists", query="ed sheeran", type="albums")["playlists"]


def test_resolve_embed():
    assert call("/soundcloud/resolve", link="https://soundcloud.com/billieeilish/ocean-eyes")["type"] == "track"
    assert "iframe" in call("/soundcloud/embed", link="https://soundcloud.com/billieeilish/ocean-eyes")["html"]
    assert call("/soundcloud/resolve", link="https://soundcloud.com/discover/sets/artist-stations:3685019")["tracks"]


def test_users():
    assert call("/soundcloud/users/details", user="billieeilish")["social_links"]
    assert call("/soundcloud/users/tracks", user="billieeilish")["tracks"]
    assert call("/soundcloud/users/popular-tracks", user="billieeilish")["tracks"]
    assert call("/soundcloud/users/playlists", user="billieeilish")["playlists"]
    assert call("/soundcloud/users/likes", user="billieeilish")["likes"]
    assert call("/soundcloud/users/reposts", user="billieeilish")["reposts"]
    assert call("/soundcloud/users/activity", user="billieeilish")["activity"]
    assert call("/soundcloud/users/followers", user="billieeilish")["users"]
    assert call("/soundcloud/users/followings", user="billieeilish")["users"]
    assert call("/soundcloud/users/comments", user="billieeilish")["comments"]
    assert call("/soundcloud/users/related-artists", user="billieeilish")["users"]
    assert call("/soundcloud/users/spotlight", user="billieeilish")["items"]
    assert call("/soundcloud/users/social-links", user="billieeilish")["social_links"]
    assert call("/soundcloud/users/station", user="billieeilish")["tracks"]


def test_playlists():
    assert call("/soundcloud/playlists/details", playlist="https://soundcloud.com/billieeilish/sets/dont-smile-at-me")["tracks"]
    assert call("/soundcloud/playlists/tracks", playlist="https://soundcloud.com/billieeilish/sets/dont-smile-at-me")["tracks"][0]["position"] == 1
    assert call("/soundcloud/playlists/likers", playlist="https://soundcloud.com/billieeilish/sets/dont-smile-at-me")["users"]
    assert call("/soundcloud/playlists/reposters", playlist="https://soundcloud.com/billieeilish/sets/dont-smile-at-me")["users"]


def test_charts_discover():
    assert call("/soundcloud/charts/top-50", country="US", chart="all-music-genres")["tracks"]
    assert call("/soundcloud/charts/trending", limit=50)["tracks"][0]["rank"] == 1
    assert call("/soundcloud/charts/trending-by-genre", genre="hip-hop")["tracks"]
    assert call("/soundcloud/charts/list")["top_50"]
    assert call("/soundcloud/discover/home")["sections"]
    assert call("/soundcloud/discover/featured-tracks")["tracks"]
    assert call("/soundcloud/discover/new-tracks", tag="lofi")["tracks"]
    assert call("/soundcloud/charts/top-50", country="GB", chart="dance")["tracks"]
