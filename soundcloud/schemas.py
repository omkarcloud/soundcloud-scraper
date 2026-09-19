"""Marshmallow request schemas for every /soundcloud/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the SoundCloud resolvers and the per-route schemas. Every schema's
load() output is the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `track`, `user` and `playlist` each take a
numeric id, a URN, a permalink path or a soundcloud.com / on.soundcloud.com
link (refs.py); `link` takes any SoundCloud link.

Two pagination styles, matching what SoundCloud itself allows:
  * `page` + `limit` where SoundCloud pages by numeric offset (search,
    comments, charts, playlist tracks, a user's playlists / albums, the
    playlists a track is in) — responses carry count / total_pages / next;
  * `cursor` + `limit` where SoundCloud only hands out opaque cursors
    (followers, followings, likers, reposters, likes, reposts, a user's
    tracks, activity, comments, new tracks) — responses carry next_cursor.
"""
from marshmallow import ValidationError, fields, validate

from schema_fields import (BaseSchema, ChoiceField, PageField, PageSizeField, QueryField, RefField,
                           StrippedString)
from soundcloud import refs

# Choice tables as literals (public value -> api-v2 filter token); the
# publishing tooling reads enums straight from this file's AST.
SEARCH_DURATIONS = {"short": "short", "medium": "medium", "long": "long", "epic": "epic"}
SEARCH_UPLOADED_WITHIN = {"hour": "last_hour", "day": "last_day", "week": "last_week",
                          "month": "last_month", "year": "last_year"}
SEARCH_LICENSES = {"share": "to_share", "use_commercially": "to_use_commercially",
                   "modify_commercially": "to_modify_commercially"}
PLAYLIST_TYPES = ["all", "playlists", "albums"]
LIKE_TYPES = ["all", "tracks", "playlists"]
TOP50_COUNTRIES = {"US": "US", "GB": "GB", "UK": "GB"}


# ---- id-or-link fields -------------------------------------------------------------

class TrackRefField(RefField):
    resolver = staticmethod(refs.resolve_track)


class UserRefField(RefField):
    resolver = staticmethod(refs.resolve_user)


class PlaylistRefField(RefField):
    resolver = staticmethod(refs.resolve_playlist)


class LinkField(RefField):
    resolver = staticmethod(refs.resolve_any_link)


class TrackListField(fields.Field):
    """Comma-separated track ids / URNs / links (max 50) -> list of refs."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        values = [v.strip() for v in str(value).split(",") if v.strip()]
        if not values:
            raise ValidationError("Give at least one track id or link.")
        try:
            return refs.resolve_track_list(values, max_items=50)
        except ValueError as e:
            raise ValidationError(str(e))


class CursorField(StrippedString):
    """Opaque next_cursor from the previous page (absent = first page)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Length(max=400))
        super().__init__(**kwargs)


class LowerText(StrippedString):
    """Optional free text, lower-cased (SoundCloud's genre/tag and place
    filters only match lower case: 'Classical' finds nothing)."""

    def __init__(self, max_length=80, **kwargs):
        kwargs.setdefault("required", False)
        if not kwargs["required"]:
            kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Length(max=max_length))
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        return value.lower() if value else None


class TagField(LowerText):
    """Required genre / tag slug for the new-tracks feed."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        slug = refs.slugify(value)
        if not slug:
            raise ValidationError("Must be a genre or tag, e.g. lofi, hiphoprap, techno.")
        return slug


# ---- search / resolve ------------------------------------------------------------------

class SearchAllSchema(BaseSchema):
    query = QueryField()
    page = PageField(max_page=300)
    limit = PageSizeField(default=20, max_size=100)


class SearchTracksSchema(SearchAllSchema):
    genre_or_tag = LowerText()
    duration = ChoiceField(SEARCH_DURATIONS)
    uploaded_within = ChoiceField(SEARCH_UPLOADED_WITHIN)
    license = ChoiceField(SEARCH_LICENSES)


class SearchUsersSchema(SearchAllSchema):
    place = LowerText()


class SearchPlaylistsSchema(SearchAllSchema):
    type = ChoiceField(PLAYLIST_TYPES, load_default="all")
    genre_or_tag = LowerText()


class AutoCompleteSchema(BaseSchema):
    query = QueryField(max_length=100)


class LinkSchema(BaseSchema):
    link = LinkField()


# ---- tracks ----------------------------------------------------------------------------

class TrackSchema(BaseSchema):
    track = TrackRefField()


class TrackBatchSchema(BaseSchema):
    tracks = TrackListField()


class TrackWaveformSchema(TrackSchema):
    samples = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=10, max=1800))


class TrackPagedSchema(TrackSchema):
    page = PageField(max_page=1000)
    limit = PageSizeField(default=20, max_size=100)


class TrackCommentsSchema(TrackSchema):
    page = PageField(max_page=1000)
    limit = PageSizeField(default=50, max_size=200)


class TrackCursorSchema(TrackSchema):
    cursor = CursorField()
    limit = PageSizeField(default=50, max_size=200)


class TrackRelatedSchema(TrackSchema):
    limit = PageSizeField(default=20, max_size=50)


class TrackPlaylistsSchema(TrackPagedSchema):
    type = ChoiceField(PLAYLIST_TYPES, load_default="all")


class StationSchema(BaseSchema):
    limit = PageSizeField(default=50, max_size=100)


class TrackStationSchema(StationSchema):
    track = TrackRefField()


# ---- users -----------------------------------------------------------------------------

class UserSchema(BaseSchema):
    user = UserRefField()


class UserCursorSchema(UserSchema):
    cursor = CursorField()
    limit = PageSizeField(default=50, max_size=200)


class UserLikesSchema(UserCursorSchema):
    type = ChoiceField(LIKE_TYPES, load_default="all")


class UserPlaylistsSchema(UserSchema):
    type = ChoiceField(PLAYLIST_TYPES, load_default="all")
    page = PageField(max_page=1000)
    limit = PageSizeField(default=20, max_size=100)


class UserStationSchema(StationSchema):
    user = UserRefField()


# ---- playlists -------------------------------------------------------------------------

class PlaylistSchema(BaseSchema):
    playlist = PlaylistRefField()


class PlaylistTracksSchema(PlaylistSchema):
    page = PageField(max_page=1000)
    limit = PageSizeField(default=50, max_size=100)


class PlaylistCursorSchema(PlaylistSchema):
    cursor = CursorField()
    limit = PageSizeField(default=50, max_size=200)


# ---- charts / discover ------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass


class TrendingSchema(BaseSchema):
    page = PageField(max_page=100)
    limit = PageSizeField(default=50, max_size=100)


class Top50Schema(BaseSchema):
    country = ChoiceField(TOP50_COUNTRIES, load_default="US")
    chart = LowerText(load_default="all-music-genres")


class TrendingByGenreSchema(BaseSchema):
    genre = LowerText(load_default="all-genres")
    limit = PageSizeField(default=50, max_size=100)


class NewTracksSchema(BaseSchema):
    tag = TagField(required=True)
    cursor = CursorField()
    limit = PageSizeField(default=50, max_size=200)

