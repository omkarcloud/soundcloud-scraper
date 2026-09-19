"""Configuration for the SoundCloud Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                  port the API listens on (default 8000)
    SOUNDCLOUD_PROXY      proxy URL for every request, e.g. http://user:pass@host:port
                          (default: none — direct). SoundCloud runs no bot
                          protection on the JSON API this scraper uses (60
                          back-to-back requests from one IP all answered), so
                          you very likely don't need it. Set it only if you
                          start seeing 403 / 429 at high volume.
    SOUNDCLOUD_CLIENT_ID  pin SoundCloud's public web client_id by hand
                          (default: none — read from soundcloud.com on first
                          use and refreshed automatically when it rotates)

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

SOUNDCLOUD_CLIENT_ID = os.environ.get("SOUNDCLOUD_CLIENT_ID") or None

# Block fallback: after a 403 / 429 a worker thread may switch to a separate
# proxy for SOUNDCLOUD_DIRECT_COOLDOWN seconds. Off here — with
# SOUNDCLOUD_PROXY set every request already goes through it.
SOUNDCLOUD_FALLBACK_PROXY_COUNTRY = None
SOUNDCLOUD_DIRECT_COOLDOWN = 900


def soundcloud_proxy():
    """Proxy URL for a new session (None = direct)."""
    return os.environ.get("SOUNDCLOUD_PROXY") or None


def soundcloud_fallback_proxy():
    """Proxy for a blocked worker (None = no fallback; see above)."""
    return None
