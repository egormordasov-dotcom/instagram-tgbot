import aiohttp
import asyncio
import json
import os
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_URL   = "https://i.instagram.com"
APP_ID     = "936619743392459"
COOKIES_FILE = "cookies.json"

def load_cookies() -> dict:
    path = os.environ.get("COOKIES_FILE", COOKIES_FILE)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл куки не найден: {path}")
    with open(path) as f:
        data = json.load(f)
    cookies = data if isinstance(data, list) else data.get("cookies", [])
    return {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}

def make_headers(cookies: dict) -> dict:
    csrf = cookies.get("csrftoken", "")
    return {
        "User-Agent":       "Instagram 269.0.0.18.75 Android",
        "X-IG-App-ID":      APP_ID,
        "X-CSRFToken":      csrf,
        "Accept-Language":  "ru-RU,ru;q=0.9",
        "Accept":           "*/*",
        "Connection":       "keep-alive",
    }

async def get_user_id(session: aiohttp.ClientSession, username: str) -> str | None:
    url = f"{BASE_URL}/api/v1/users/web_profile_info/?username={username}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning(f"get_user_id {username}: статус {resp.status}")
                return None
            data = await resp.json()
            return data.get("data", {}).get("user", {}).get("id")
    except Exception as e:
        logger.error(f"get_user_id {username}: {e}")
        return None

async def fetch_reels(session: aiohttp.ClientSession, user_id: str, max_pages: int = 100):
    """Получает все Reels аккаунта постранично."""
    reels = []
    max_id = None

    for page in range(max_pages):
        payload = {"target_user_id": user_id, "page_size": 12, "include_feed_video": True}
        if max_id:
            payload["max_id"] = max_id

        try:
            async with session.post(
                f"{BASE_URL}/api/v1/clips/user/",
                data=payload,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"fetch_reels page {page}: статус {resp.status}")
                    break
                data = await resp.json()
        except Exception as e:
            logger.error(f"fetch_reels page {page}: {e}")
            break

        items = data.get("items", [])
        for item in items:
            media = item.get("media", item)
            code  = media.get("code", "")
            caption_data = media.get("caption") or {}
            caption_text = caption_data.get("text", "") if isinstance(caption_data, dict) else ""
            taken_at     = media.get("taken_at")
            views        = media.get("play_count") or media.get("view_count") or 0

            reels.append({
                "video_id":    code,
                "title":       caption_text[:80],
                "description": caption_text,
                "published_at": datetime.fromtimestamp(taken_at, tz=timezone.utc) if taken_at else None,
                "views":       views,
            })

        if not data.get("paging_info", {}).get("more_available", False):
            break
        max_id = data.get("paging_info", {}).get("max_id")
        if not max_id:
            break

        await asyncio.sleep(0.5)

    return reels

async def collect_account(username: str) -> tuple[str | None, list]:
    """Собирает user_id и все Reels для аккаунта."""
    cookies = load_cookies()
    headers = make_headers(cookies)

    async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
        user_id = await get_user_id(session, username)
        if not user_id:
            return None, []
        reels = await fetch_reels(session, user_id)
        return user_id, reels

def find_articles_in_text(text: str, articles: list[str]) -> list[str]:
    """Ищет артикулы в тексте с защитой от ложных срабатываний."""
    found = []
    for article in articles:
        pattern = r"(?<![A-Za-z0-9А-Яа-яЁё])" + re.escape(article) + r"(?![A-Za-z0-9А-Яа-яЁё])"
        if re.search(pattern, text, re.IGNORECASE):
            found.append(article)
    return found
