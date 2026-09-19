"""Offline tests: refs parsing and the api-v2 normalizers against raw
responses captured 2026-09-19 (soundcloud/fixtures/*.json).

    python -m pytest soundcloud/test_parsers.py -q
"""
import json
import os

import pytest

from soundcloud import parsers as P
from soundcloud import refs

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fx(name):
    with open(os.path.join(FIX, name + ".json")) as f:
        return json.load(f)


# ---- refs ----------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("1516134547", {"id": "1516134547", "link": None, "secret_token": None}),
    ("soundcloud:tracks:42", {"id": "42", "link": None, "secret_token": None}),
    ("https://soundcloud.com/edsheeran/photograph?si=abc&utm_source=x",
     {"id": None, "link": "https://soundcloud.com/edsheeran/photograph", "secret_token": None}),
    ("https://m.soundcloud.com/edsheeran/photograph",
     {"id": None, "link": "https://soundcloud.com/edsheeran/photograph", "secret_token": None}),
    ("edsheeran/photograph", {"id": None, "link": "https://soundcloud.com/edsheeran/photograph", "secret_token": None}),
    ("https://soundcloud.com/a/b/s-AbCdE12", {"id": None, "link": "https://soundcloud.com/a/b/s-AbCdE12",
                                              "secret_token": "s-AbCdE12"}),
    ("https://api.soundcloud.com/tracks/soundcloud%3Atracks%3A213950659",
     {"id": "213950659", "link": None, "secret_token": None}),
    ("https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/213950659&auto_play=false",
     {"id": "213950659", "link": None, "secret_token": None}),
    ("https://on.soundcloud.com/AbC123", {"id": None, "link": "https://on.soundcloud.com/AbC123",
                                          "secret_token": None}),
])
def test_resolve_track(value, expected):
    assert refs.resolve_track(value) == expected


@pytest.mark.parametrize("value, message", [
    ("https://soundcloud.com/edsheeran", "user link"),
    ("https://soundcloud.com/a/sets/b", "playlist link"),
    ("soundcloud:users:1", "user URN"),
    ("https://open.spotify.com/track/1", "soundcloud.com link"),
    ("https://soundcloud.com/discover/sets/artist-stations:1", "station link"),
])
def test_resolve_track_rejects(value, message):
    with pytest.raises(ValueError, match=message):
        refs.resolve_track(value)


def test_resolve_user_and_playlist():
    assert refs.resolve_user("edsheeran")["link"] == "https://soundcloud.com/edsheeran"
    assert refs.resolve_user("https://soundcloud.com/edsheeran/likes")["link"] == "https://soundcloud.com/edsheeran"
    assert refs.resolve_user("https://soundcloud.com/edsheeran/sets")["link"] == "https://soundcloud.com/edsheeran"
    assert refs.resolve_playlist("music-charts-us/sets/all-music-genres")["link"] == \
        "https://soundcloud.com/music-charts-us/sets/all-music-genres"
    assert refs.resolve_playlist("https://soundcloud.com/a/sets/b/s-XyZ12")["secret_token"] == "s-XyZ12"
    with pytest.raises(ValueError):
        refs.resolve_user("https://soundcloud.com/charts/top")


def test_resolve_any_link():
    assert refs.resolve_any_link("https://soundcloud.com/discover/sets/trending-by-genre:trap") == \
        "https://soundcloud.com/discover/sets/trending-by-genre:trap"
    assert refs.resolve_any_link("edsheeran") == "https://soundcloud.com/edsheeran"
    with pytest.raises(ValueError):
        refs.resolve_any_link("https://soundcloud.com/search?q=x")


def test_track_list_dedupes():
    out = refs.resolve_track_list(["1", "soundcloud:tracks:1", "edsheeran/photograph"])
    assert [r["id"] or r["link"] for r in out] == ["1", "https://soundcloud.com/edsheeran/photograph"]


# ---- value helpers -------------------------------------------------------------------

def test_image_and_tags():
    img = P.image("https://i1.sndcdn.com/artworks-abc-large.jpg")
    assert img == {"link": "https://i1.sndcdn.com/artworks-abc-t500x500.jpg",
                   "original_link": "https://i1.sndcdn.com/artworks-abc-original.jpg"}
    assert P.image("https://a1.sndcdn.com/images/default_avatar_large.png") is None
    assert P.tags('"Top 50" Charts US soundcloud:source=web-record Charts') == ["Top 50", "Charts", "US"]


def test_link_expiry_from_cloudfront_policy():
    assert P.link_expiry(fx("stream")["url"]).endswith("Z")


def test_transcoding_info():
    info = P.transcoding_info({"preset": "aac_160k", "quality": "sq", "snipped": False,
                               "format": {"protocol": "hls", "mime_type": "audio/mp4"}})
    assert info == {"format": "aac", "bitrate_kbps": 160, "protocol": "hls", "quality": "sq",
                    "mime_type": "audio/mp4", "is_preview": False}
    assert P.transcoding_info({"preset": "mp3_1_0", "format": {}})["bitrate_kbps"] == 128


# ---- entities ------------------------------------------------------------------------

def test_track():
    t = P.track(fx("track"))
    assert t["id"] == 1516134547 and t["link"].startswith("https://soundcloud.com/")
    assert t["stats"]["plays"] > 0 and t["policy"] == "allow" and t["is_preview_only"] is False
    assert t["duration_ms"] == t["playable_duration_ms"]
    assert t["user"]["username"] and t["publisher"] is None     # only the id/urn echo
    assert "track_authorization" not in t and "media" not in t and "uri" not in t


def test_snipped_track_publisher():
    t = P.track(fx("track_snip"))
    assert t["is_preview_only"] is True and t["playable_duration_ms"] == 30000
    assert t["publisher"]["isrc"] == "GBAHS1400094" and t["publisher"]["upc"] == "825646284535"
    assert t["release_date"] == "2014-06-20"


def test_stub_track_keeps_shape():
    t = P.track({"id": 1, "kind": "track", "policy": "BLOCK"})
    assert t["title"] is None and t["policy"] == "block" and t["stats"]["plays"] is None
    assert set(t) == set(P.track(fx("track")))


def test_user():
    u = P.user(fx("user"))
    assert u["username"] == "Ed Sheeran" and u["is_verified"] is True
    assert u["banner_link"].startswith("https://") and u["stats"]["tracks"] > 0
    assert u["city"] is None                       # "" -> null


def test_playlist_and_station():
    pl = P.playlist(fx("playlist"))
    assert pl["type"] == "playlist" and pl["track_count"] == 50 and pl["tags"][0] == "Top 50"
    album = P.item(fx("user_albums")["collection"][0])
    assert album["type"] == "album"
    st = P.system_playlist(fx("artist_station"))
    assert st["station_type"] == "artist_station" and st["artwork"]["original_link"] is None
    assert P.item(fx("system_playlist"))["type"] == "station"


def test_comments_activity_likes():
    c = P.comment(fx("comments_threaded")["collection"][0])
    assert c["text"] and c["timestamp"] and "track_id" not in c
    rows = P.items(fx("user_reposts")["collection"], P.activity)
    assert rows and rows[0]["type"] == "track_repost" and rows[0]["track"]["id"]
    likes = P.items(fx("user_likes")["collection"], P.activity)
    assert likes[0]["type"] == "track_like" and likes[0]["created_at"].endswith("Z")


def test_search_and_discovery():
    body = fx("search_all")
    kinds = {x["type"] for x in P.items(body["collection"])}
    assert {"user", "track"} <= kinds
    facets = P.facets(fx("search_tracks"), "genre")
    assert facets and facets[0]["count"] > 0
    shelves = [P.selection(s) for s in fx("mixed_selections")["collection"]]
    assert shelves[0]["id"] == "buzzing" and shelves[0]["items"]
    assert P.web_profile(fx("web_profiles")[0])["link"].startswith("http")


def test_waveform_downsample():
    wf = P.waveform({"width": 10, "height": 100, "samples": [10, 50, 100, 20, 0, 0, 30, 40, 60, 90]}, samples=5)
    assert wf["samples"] == [0.5, 1.0, 0.0, 0.4, 0.9] and wf["sample_count"] == 5


def test_pagination_caps_search_depth():
    assert P.pagination(1, 20, True, total_count=1441465, max_results=300)["total_pages"] == 15
    assert P.pagination(2, 10, True)["total_pages"] == 3
