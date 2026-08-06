"""Post poster image + caption to X (Twitter) and Instagram when credentials are set."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger("oer.social")


def absolute_media_url(poster_image_path: str) -> str:
    base = settings.public_base_url.rstrip("/")
    path = poster_image_path if poster_image_path.startswith("/") else f"/{poster_image_path}"
    return f"{base}{path}"


def local_media_file(poster_image_path: str) -> Path | None:
    if not poster_image_path:
        return None
    # /media/posters/x.png -> media_dir/posters/x.png
    rel = poster_image_path.lstrip("/")
    if rel.startswith("media/"):
        rel = rel[len("media/") :]
    path = Path(settings.media_dir) / rel
    return path if path.is_file() else None


def x_configured() -> bool:
    return bool(
        settings.x_api_key
        and settings.x_api_secret
        and settings.x_access_token
        and settings.x_access_token_secret
    )


def instagram_configured() -> bool:
    return bool(settings.instagram_access_token and settings.instagram_user_id)


async def post_to_x(*, caption: str, poster_image_path: str) -> tuple[str, str]:
    """Returns (external_id, error). error empty on success."""
    if not x_configured():
        return "", "X credentials not configured (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)"

    media_file = local_media_file(poster_image_path)
    if not media_file:
        return "", "Poster image file missing; generate pack with image first"

    try:
        media_id = await _x_upload_media(media_file)
        tweet_id = await _x_create_tweet(caption[:280], media_id)
        return tweet_id, ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("X post failed")
        return "", str(exc)


async def post_to_instagram(*, caption: str, poster_image_path: str) -> tuple[str, str]:
    """Instagram requires a publicly reachable image URL (PUBLIC_BASE_URL)."""
    if not instagram_configured():
        return "", "Instagram credentials not configured (INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID)"

    image_url = absolute_media_url(poster_image_path)
    if "localhost" in image_url or "127.0.0.1" in image_url:
        return (
            "",
            "Instagram needs a public HTTPS image URL. Set PUBLIC_BASE_URL to your deployed API "
            f"(current: {image_url})",
        )

    token = settings.instagram_access_token
    user_id = settings.instagram_user_id
    try:
        async with httpx.AsyncClient(timeout=120.0) as http:
            create = await http.post(
                f"https://graph.facebook.com/v21.0/{user_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption[:2200],
                    "access_token": token,
                },
            )
            create.raise_for_status()
            creation_id = create.json().get("id")
            if not creation_id:
                return "", f"Instagram media create failed: {create.text}"

            publish = await http.post(
                f"https://graph.facebook.com/v21.0/{user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": token},
            )
            publish.raise_for_status()
            post_id = publish.json().get("id", creation_id)
            return str(post_id), ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("Instagram post failed")
        return "", str(exc)


async def _x_upload_media(path: Path) -> str:
    """Upload media via Twitter API v1.1 (OAuth 1.0a)."""
    url = "https://upload.twitter.com/1.1/media/upload.json"
    data = path.read_bytes()
    async with httpx.AsyncClient(timeout=120.0) as http:
        auth_header = _oauth1_header(
            "POST",
            url,
            {},
        )
        files = {"media": (path.name, data, "image/png")}
        res = await http.post(url, headers={"Authorization": auth_header}, files=files)
        if res.status_code >= 400:
            raise RuntimeError(f"X media upload failed: {res.status_code} {res.text}")
        media_id = res.json().get("media_id_string")
        if not media_id:
            raise RuntimeError(f"X media upload missing id: {res.text}")
        return str(media_id)


async def _x_create_tweet(text: str, media_id: str) -> str:
    url = "https://api.twitter.com/2/tweets"
    body = {"text": text, "media": {"media_ids": [media_id]}}
    # OAuth1 for JSON body — sign without body params
    auth_header = _oauth1_header("POST", url, {})
    async with httpx.AsyncClient(timeout=60.0) as http:
        res = await http.post(
            url,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            json=body,
        )
        if res.status_code >= 400:
            raise RuntimeError(f"X tweet failed: {res.status_code} {res.text}")
        tweet_id = res.json().get("data", {}).get("id")
        if not tweet_id:
            raise RuntimeError(f"X tweet missing id: {res.text}")
        return str(tweet_id)


def _oauth1_header(method: str, url: str, extra_params: dict[str, str]) -> str:
    """Build OAuth 1.0a Authorization header."""
    oauth = {
        "oauth_consumer_key": settings.x_api_key,
        "oauth_nonce": hashlib.sha1(str(time.time()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": settings.x_access_token,
        "oauth_version": "1.0",
    }
    params = {**oauth, **extra_params}
    param_str = "&".join(
        f"{quote(k, safe='~')}={quote(str(v), safe='~')}" for k, v in sorted(params.items())
    )
    base = "&".join(
        [
            method.upper(),
            quote(url, safe="~"),
            quote(param_str, safe="~"),
        ]
    )
    key = f"{quote(settings.x_api_secret, safe='~')}&{quote(settings.x_access_token_secret, safe='~')}"
    signature = base64_hmac(key, base)
    oauth["oauth_signature"] = signature
    return "OAuth " + ", ".join(
        f'{quote(k, safe="~")}="{quote(str(v), safe="~")}"' for k, v in sorted(oauth.items())
    )


def base64_hmac(key: str, raw: str) -> str:
    digest = hmac.new(key.encode(), raw.encode(), hashlib.sha1).digest()
    import base64 as b64

    return b64.b64encode(digest).decode()
