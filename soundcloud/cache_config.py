"""Cache TTL per /soundcloud/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so `?page=1` and no `page` share a
row).

Tiers follow how fast each surface moves: counters (plays, likes,
followers) tick constantly but a few hours of lag is fine for an API; the
social lists (likers, followers, comments) and uploads move faster; charts
refresh daily (trending) or weekly (Top 50); stream links are signed and
expire within minutes, so they are never cached.
"""
from datetime import timedelta

# --- entities ------------------------------------------------------------------------
TRACK_CACHE = timedelta(hours=6)
USER_CACHE = timedelta(hours=6)
PLAYLIST_CACHE = timedelta(hours=3)
RESOLVE_CACHE = timedelta(hours=6)
EMBED_CACHE = timedelta(days=7)
WAVEFORM_CACHE = timedelta(days=30)        # a waveform never changes after upload

# --- lists ---------------------------------------------------------------------------
SOCIAL_LIST_CACHE = timedelta(hours=1)     # likers, reposters, followers, comments
USER_LIST_CACHE = timedelta(hours=1)       # uploads, likes, reposts, activity
RELATED_CACHE = timedelta(hours=12)
STATION_CACHE = timedelta(hours=6)

# --- search --------------------------------------------------------------------------
AUTOCOMPLETE_CACHE = timedelta(days=1)
SEARCH_CACHE = timedelta(hours=3)

# --- charts / discover -----------------------------------------------------------------
TRENDING_CACHE = timedelta(hours=1)
TOP50_CACHE = timedelta(hours=6)
CHART_LIST_CACHE = timedelta(hours=12)
DISCOVER_CACHE = timedelta(hours=1)
NEW_TRACKS_CACHE = timedelta(minutes=10)
