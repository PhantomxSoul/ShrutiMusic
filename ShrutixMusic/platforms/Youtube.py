import asyncio
import os
import re
from typing import Union
import aiohttp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

# Agar py_yt ya youtubesearchpython installed ho toh import karein
try:
    from py_yt import VideosSearch, Playlist
except ImportError:
    try:
        from youtubesearchpython.__future__ import VideosSearch, Playlist
    except ImportError:
        VideosSearch, Playlist = None, None

# =====================================================================
#                      RYAN API CONFIGURATION
# =====================================================================
# Apne Heroku / Server ka main URL yahan hardcode karein:
API_BASE_URL = "https://ryan-api-bot.herokuapp.com"  # Apna Heroku domain yahan set karein

# Developers ya users ko sirf apni API key set karni hogi:
# Ye key aapke Telegram Bot (@RyanApiBot) par /start ya /getkey karke milegi
API_KEY = os.environ.get("RYAN_API_KEY", "YOUR_API_KEY_HERE")

DOWNLOAD_DIR = "downloads"

# =====================================================================
#                      HELPER FUNCTIONS
# =====================================================================

def _env_dir(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return os.path.abspath(os.path.expanduser(value)) if value else ""

AUDIO_DOWNLOAD_PATH = _env_dir("AUDIO_DOWNLOAD_PATH")
VIDEO_DOWNLOAD_PATH = _env_dir("VIDEO_DOWNLOAD_PATH")
AUDIO_EXTENSIONS = ("webm", "m4a", "mp3", "ogg")
VIDEO_EXTENSIONS = ("mp4", "mkv", "webm")

def is_external_path(path) -> bool:
    if not path:
        return False
    full = os.path.abspath(str(path))
    for base in (AUDIO_DOWNLOAD_PATH, VIDEO_DOWNLOAD_PATH):
        if base and full.startswith(base + os.sep):
            return True
    return False

def _find_external(directory: str, video_id: str, extensions):
    for ext in extensions:
        path = os.path.join(directory, f"{video_id}.{ext}")
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    return None

def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

# =====================================================================
#                  RYAN API CLIENT FETCH ENGINE
# =====================================================================

async def fetch_ryan_api(query: str, timeout: int = 25) -> dict:
    """RyanApi se 4-level fallback resolved stream URL fetch karta hai."""
    url = f"{API_BASE_URL}/api/stream"
    params = {
        "query": query,
        "api_key": API_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("success"):
                        return result.get("data", {})
                elif resp.status == 401:
                    print("❌ [RyanApi Error]: Invalid ya missing API Key! Check @RyanApiBot.")
                else:
                    print(f"⚠️ [RyanApi Warning]: Server returned status {resp.status}")
                return None
    except Exception as e:
        print(f"❌ [RyanApi Request Failed]: {e}")
        return None

async def _download_media(link: str, kind: str, timeout: int) -> str:
    """Link ya ID ke through stream URL lekar local file download karta hai."""
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None

    is_audio = kind == "audio"
    external = AUDIO_DOWNLOAD_PATH if is_audio else VIDEO_DOWNLOAD_PATH
    extensions = AUDIO_EXTENSIONS if is_audio else VIDEO_EXTENSIONS

    # External cache check
    if external:
        found = _find_external(external, video_id, extensions)
        if found:
            return found

    # Local downloads check
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    extension = "mp3" if is_audio else "mp4"
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{extension}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    # Step 1: RyanApi se resolve stream URL fetch karo
    data = await fetch_ryan_api(link, timeout=30)
    if not data or not data.get("stream_url"):
        return None

    stream_url = data["stream_url"]

    # Step 2: Stream URL se chunk download karke local media create karo
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(stream_url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception as e:
        print(f"Download stream error: {e}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None

async def download_song(link: str) -> str:
    return await _download_media(link, "audio", 300)

async def download_video(link: str) -> str:
    return await _download_media(link, "video", 600)

async def get_autoplay(video_id: str, timeout: int = 15) -> list:
    """Autoplay recommendation fallback."""
    # RyanApi query response se title uthakar related videos search kar sakte hain
    track_info = await fetch_ryan_api(video_id, timeout=timeout)
    if track_info and VideosSearch:
        try:
            results = VideosSearch(track_info.get("title", video_id), limit=5)
            tracks = []
            for item in (await results.next()).get("result", []):
                tracks.append(item.get("id"))
            return tracks
        except Exception:
            pass
    return []

# =====================================================================
#                     YOUTUBE API WRAPPER CLASS
# =====================================================================

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        if VideosSearch:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                title = result["title"]
                duration_min = result["duration"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                vidid = result["id"]
                duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
            return title, duration_min, duration_sec, thumbnail, vidid
        
        # Fallback agar py_yt na ho toh RyanApi se direct details lo
        data = await fetch_ryan_api(link)
        if data:
            return data["title"], str(data["duration"]), data["duration"], "", data["video_id"]
        return "Unknown", "0:00", 0, "", ""

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        if VideosSearch:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["title"]
        data = await fetch_ryan_api(link)
        return data.get("title", "Unknown Track") if data else "Unknown Track"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        if VideosSearch:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["duration"]
        data = await fetch_ryan_api(link)
        return str(data.get("duration", "0:00")) if data else "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        if VideosSearch:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["thumbnails"][0]["url"].split("?")[0]
        return ""

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed via RyanApi"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        if not Playlist:
            return []
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if vid:
                ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        if VideosSearch:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                title = result["title"]
                duration_min = result["duration"]
                vidid = result["id"]
                yturl = result["link"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            track_details = {
                "title": title,
                "link": yturl,
                "vidid": vidid,
                "duration_min": duration_min,
                "thumb": thumbnail,
            }
            return track_details, vidid
        
        data = await fetch_ryan_api(link)
        track_details = {
            "title": data.get("title", "Unknown"),
            "link": link,
            "vidid": data.get("video_id", ""),
            "duration_min": str(data.get("duration", 0)),
            "thumb": "",
        }
        return track_details, data.get("video_id", "")

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        if VideosSearch:
            a = VideosSearch(link, limit=10)
            result = (await a.next()).get("result")
            title = result[query_type]["title"]
            duration_min = result[query_type]["duration"]
            vidid = result[query_type]["id"]
            thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
            return title, duration_min, thumbnail, vidid
        return "Unknown", "0:00", "", ""

    async def download(
        self,
        link: str,
        mystic=None,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link
        try:
            if video:
                downloaded_file = await download_video(link)
            else:
                downloaded_file = await download_song(link)
            if downloaded_file:
                return downloaded_file, True
            return None, False
        except Exception:
            return None, False


YouTube = YouTubeAPI()
