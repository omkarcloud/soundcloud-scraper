# 🎧 SoundCloud Scraper

SoundCloud Scraper is a **free and open-source** scraper that gets you **unlimited** detailed SoundCloud data for free.

## ✨ What Can I Get?

- 🎵 **Full details on 400M+ tracks** — plays, likes, reposts, comments, ISRC, label, tags & artwork
- 🎤 **Every artist profile** — followers, uploads, likes, reposts, related artists & social links
- 🔍 **Search with SoundCloud's own filters** — genre, duration, upload date, license & city
- 📈 **Official Top 50 & trending charts** — US and UK Top 50s, trending top 100, 20 trending genres

## 🎥 Example: A Full SoundCloud Track

```json
{
  "id": 233719633,
  "title": "Ocean Eyes",
  "link": "https://soundcloud.com/billieeilish/ocean-eyes",
  "genre": "Indie",
  "tags": ["Pop", "Dark", "Billie"],
  "duration_ms": 200456,
  "duration": "3:20",
  "stats": {
    "plays": 75073599,
    "likes": 1334588,
    "reposts": 29311,
    "comments": 28408
  },
  "user": {
    "id": 87105617,
    "username": "Billie Eilish",
    "link": "https://soundcloud.com/billieeilish",
    "followers_count": 3943728,
    "is_verified": true
  },
  "artwork": { "link": "https://i1.sndcdn.com/artworks-000194211850-6zfpyg-t500x500.jpg" },
  "publisher": { "artist": "Billie Eilish", "isrc": "US23A1500056" },
  "purchase": { "title": "STREAM", "link": "https://open.spotify.com/album/2msN7XBgV3JCjQ7Tq3t7i9" },
  "is_streamable": true,
  "created_at": "2015-11-19T03:18:57Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free SoundCloud Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/soundcloud-scraper
cd soundcloud-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/tracks/details?track=https://soundcloud.com/billieeilish/ocean-eyes"
```

```json
{
  "id": 233719633,
  "title": "Ocean Eyes",
  "link": "https://soundcloud.com/billieeilish/ocean-eyes",
  "genre": "Indie",
  "duration": "3:20",
  "stats": {
    "plays": 75073673,
    "likes": 1334591,
    "reposts": 29311,
    "comments": 28408,
    "downloads": 39
  },
  "user": {
    "id": 87105617,
    "username": "Billie Eilish",
    "followers_count": 3943728,
    "is_verified": true
  },
  "publisher": { "artist": "Billie Eilish", "isrc": "US23A1500056" },
  "created_at": "2015-11-19T03:18:57Z"
}
```

All 42 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

42 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Track Details | `/tracks/details` | Plays, likes, ISRC, label, artwork and artist in one call |
| Auto Complete | `/search/auto-complete` | Search suggestions and matching tags as you type |
| Search All / Tracks / Users / Playlists | `/search/all`, `/search/tracks`, `/search/users`, `/search/playlists` | Filtered results with genre and city counts |
| Resolve Link | `/resolve` | Full data for any SoundCloud link |
| Batch Tracks | `/tracks/batch` | Up to 50 tracks in one call |
| Track Stream Links | `/tracks/stream` | Playable MP3 and HLS links with bitrate and expiry |
| Track Comments | `/tracks/comments` | Timed comments with their position in the track |
| Track Likers / Reposters | `/tracks/likers`, `/tracks/reposters` | Everyone who liked or reposted, newest first |
| Related Tracks | `/tracks/related` | Up to 50 tracks SoundCloud relates to it |
| Track Playlists | `/tracks/playlists` | Public playlists and albums containing the track |
| Track / Artist Station | `/tracks/station`, `/users/station` | SoundCloud's endless mix, every track in full |
| Track Waveform | `/tracks/waveform` | Player waveform as samples from 0 to 1 |
| Embed Player | `/embed` | Official iframe player for any link |
| User Details | `/users/details` | Full profile with counters, badges and social links |
| User Tracks / Popular Tracks | `/users/tracks`, `/users/popular-tracks` | Every upload, or the profile's top tracks |
| User Playlists | `/users/playlists` | Playlists and albums with track counts |
| User Likes / Reposts / Activity | `/users/likes`, `/users/reposts`, `/users/activity` | What they liked, reposted and posted, dated |
| User Followers / Followings | `/users/followers`, `/users/followings` | Full follower graph with profile details |
| User Comments | `/users/comments` | Their comments, each with its track |
| Related Artists | `/users/related-artists` | SoundCloud's "Fans also like" artists |
| User Spotlight / Social Links | `/users/spotlight`, `/users/social-links` | Pinned tracks and every website and social link |
| Playlist Details / Tracks | `/playlists/details`, `/playlists/tracks` | Playlist or album with every track numbered |
| Playlist Likers / Reposters | `/playlists/likers`, `/playlists/reposters` | Everyone who liked or reposted it |
| Top 50 Charts | `/charts/top-50` | Official weekly US and UK Top 50s, ranked |
| Trending Chart | `/charts/trending` | Trending top 100 with trending scores |
| Trending by Genre | `/charts/trending-by-genre` | Trending playlist for one of 20 genres |
| Chart List | `/charts/list` | Every chart and genre you can fetch |
| Discover Home / Featured / New Tracks | `/discover/home`, `/discover/featured-tracks`, `/discover/new-tracks` | Discover shelves, front-page picks and newest uploads per tag |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-soundcloud-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-soundcloud-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-soundcloud-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/tracks/details",
    params={"track": "https://soundcloud.com/billieeilish/ocean-eyes"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about SoundCloud Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20SoundCloud%20Scraper%20API.)

[![Ask Us by Email about SoundCloud Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20SoundCloud%20Scraper%20API&body=I%20need%20help%20using%20the%20SoundCloud%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Deezer Scraper**](https://github.com/omkarcloud/deezer-scraper) — tracks, albums, artists, playlists & charts from Deezer
- [**IMDb Scraper**](https://github.com/omkarcloud/imdb-scraper) — movies & TV: ratings, cast, box office & all 6 IMDb charts
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/soundcloud-scraper)

Star the repo ⭐ and become a star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/soundcloud-scraper)
