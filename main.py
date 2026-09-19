"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The functions live in soundcloud/ (tracks, users, playlists,
search, charts, resolve). `track`, `user` and `playlist` take the same
validated refs the API builds, so go through soundcloud.refs first.
"""
import json
import os

from soundcloud import charts, refs, tracks, users

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a track link, numeric id, URN or artist/track permalink
    save("track_ocean_eyes.json", tracks.track_details(refs.resolve_track("https://soundcloud.com/billieeilish/ocean-eyes")))

    # a profile with its bio, counters, badges and social links
    save("user_billie_eilish.json", users.user_details(refs.resolve_user("billieeilish")))

    # SoundCloud's official weekly US Top 50, every track ranked
    save("chart_top_50_us.json", charts.top_50_chart("US", "all-music-genres"))
