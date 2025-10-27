import json
from typing import TypeVar
import flask
from flask import Flask
from flask_socketio import SocketIO, emit
from cryptography.fernet import Fernet
from lrcup import LRCLib
import asyncio
import dotenv
import os
import threading
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
import flask_cors
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.helper import first
import unicodedata

dotenv.load_dotenv()

CONFIG = {}
try:
    with open("config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    CONFIG = {}

def cfg(key: str, default=None):
    """Return config value from config.json if present, otherwise from environment."""
    val = CONFIG.get(key, None)
    if val is None:
        return os.getenv(key, default)
    return val

blocklist_raw = cfg("BLOCKLIST_WORDS", "")
if isinstance(blocklist_raw, list):
    BLOCKLIST_WORDS = [str(w).lower() for w in blocklist_raw]
else:
    BLOCKLIST_WORDS = [w.strip().lower() for w in str(blocklist_raw).split(',') if w.strip()]

def normalize_text(text: str) -> str:
    """Normalize text for blocklist checking by removing special characters and spaces."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    zero_width_and_spaces = '\u200B\u200C\u200D\u200E\u200F\uFEFF\u00A0 \t\n\r'
    text = ''.join(c for c in text if c not in zero_width_and_spaces)
    return text.lower()

username = cfg("LASTFM_USER") or ""

T = TypeVar("T")


def notnone(val: T | None) -> T:
    assert val is not None
    return val


TWITCH_API_ID = os.getenv("TWITCH_API_ID")
TWITCH_API_SECRET = os.getenv("TWITCH_API_SECRET")
assert TWITCH_API_ID, "TWITCH_API_ID environment variable not set"
assert TWITCH_API_SECRET, "TWITCH_API_SECRET environment variable not set"

TWITCH_OAUTH_TOKEN = None

TWITCH_USERNAME = cfg("TWITCH_USERNAME")
assert TWITCH_USERNAME, "TWITCH_USERNAME not set in env or config"

TWITCH_CHANNEL = cfg("TWITCH_CHANNEL")
assert TWITCH_CHANNEL, "TWITCH_CHANNEL not set in env or config"

BROADCASTER_ID = cfg("BROADCASTER_ID")
MODERATOR_ID = cfg("MODERATOR_ID")

TRACKERGG_API_KEY = os.getenv("TRACKERGG_API_KEY")
assert TRACKERGG_API_KEY, "TRACKERGG_API_KEY environment variable not set"

SPOT_API_KEY = os.getenv("SPOT_API_KEY")
SPOT_API_SECRET = os.getenv("SPOT_API_SECRET")

assert SPOT_API_KEY, "SPOT_API_KEY environment variable not set"
assert SPOT_API_SECRET, "SPOT_API_SECRET environment variable not set"

SPOT_CACHE = cfg("SPOT_CACHE") or f".cache-{username or 'spotify'}"
WIDGET_PORT = int(cfg("WIDGET_PORT", "5001") or 5001)
SPOT_REDIRECT_URI = f"http://127.0.0.1:{WIDGET_PORT}/callback"
spot_oauth = SpotifyOAuth(
    client_id=SPOT_API_KEY,
    client_secret=SPOT_API_SECRET,
    redirect_uri=SPOT_REDIRECT_URI,
    scope="user-read-currently-playing",
    cache_path=SPOT_CACHE,
)


async def twitch_chat_listen():
    try:
        twitch = await Twitch(notnone(TWITCH_API_ID), notnone(TWITCH_API_SECRET))

        USER_SCOPES = [
            AuthScope.CHAT_READ,
            AuthScope.CHAT_EDIT,
            AuthScope.CHANNEL_MODERATE,
            AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
            AuthScope.MODERATOR_READ_CHAT_MESSAGES,
            AuthScope.MODERATOR_MANAGE_BLOCKED_TERMS,
            AuthScope.MODERATOR_READ_BLOCKED_TERMS,
        ]

        auth = UserAuthenticator(twitch, USER_SCOPES)
        auth_result = await auth.authenticate()
        assert auth_result is not None, "Authentication failed, no token received."
        token, refresh_token = auth_result
        await twitch.set_user_authentication(token, USER_SCOPES, refresh_token)

        global BROADCASTER_ID, MODERATOR_ID
        broadcaster_user = await first(twitch.get_users(logins=[notnone(TWITCH_CHANNEL)]))
        if broadcaster_user:
            BROADCASTER_ID = broadcaster_user.id
        moderator_user = await first(twitch.get_users())
        if moderator_user:
            MODERATOR_ID = moderator_user.id

        assert TWITCH_CHANNEL is not None, "TWITCH_CHANNEL environment variable not set"
        chat = await Chat(twitch, initial_channel=[notnone(TWITCH_CHANNEL)])

        async def handle_message(msg):
            normalized_msg = normalize_text(msg.text)
            blocked = any(normalize_text(word) in normalized_msg for word in BLOCKLIST_WORDS)
            if blocked:
                print(f"Blocked message from {msg.user.display_name}: {msg.text}")
                if BROADCASTER_ID and MODERATOR_ID:
                    try:
                        await twitch.delete_chat_message(BROADCASTER_ID, MODERATOR_ID, msg.id)
                        print(f"Deleted message ID {msg.id}")
                    except Exception as e:
                        print(f"Failed to delete message: {e}")
                else:
                    print("Broadcaster or Moderator ID not set, cannot delete message")
                return
            
            socketio.emit(
                "chat_message",
                {
                    "user": msg.user.display_name,
                    "channel": msg.room.name,
                    "message": msg.text,
                },
            )
            chat_history.append({
                "user": msg.user.display_name,
                "channel": msg.room.name,
                "message": msg.text,
            })
            if len(chat_history) > 100:
                chat_history.pop(0)

        chat.register_event(ChatEvent.MESSAGE, handle_message)

        chat.start()

        while True:
            await asyncio.sleep(60)

    except Exception as e:
        print(f"twitchAPI chat failed or missing user auth: {e}")
        import traceback

        traceback.print_exc()


def get_spotify_client():
    return spotipy.Spotify(auth_manager=spot_oauth)


def get_current_track_from_spotify():
    try:
        sp = get_spotify_client()
        return sp.current_user_playing_track()
    except Exception as e:
        print(f"Error fetching Spotify track: {e}")
        return None


app = Flask(__name__)
app.config["SECRET_KEY"] = Fernet.generate_key()
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")
flask_cors.CORS(app, resources={r"/*": {"origins": "*"}})


@app.route("/login")
def spotify_login():
    auth_url = spot_oauth.get_authorize_url()
    return flask.redirect(auth_url)


@app.route("/callback")
def spotify_callback():
    code = flask.request.args.get("code")
    error = flask.request.args.get("error")
    if error:
        return flask.Response(f"Spotify auth error: {error}", status=400)
    if not code:
        return flask.Response("No code provided", status=400)
    try:
        token_info = spot_oauth.get_access_token(code)
        print("Spotify token_info acquired:", token_info)
    except Exception as e:
        return flask.Response(f"Error exchanging code for token: {e}", status=500)
    return flask.Response(
        "Spotify authorization complete. You can close this window.", status=200
    )


@app.route("/music")
def home():
    return flask.send_file("pages/music.htm")


@app.route("/rivals")
def rivals():
    return flask.send_file("pages/rivals.htm")


@app.route("/wmark")
def watermark():
    return flask.send_file("pages/wmark.htm")


@app.route("/chat")
def chat():
    return flask.send_file("pages/chat.htm")


@app.route("/logo.svg")
def logo():
    return flask.send_file("logo.svg")


last_title = ""
lrclib = LRCLib()
current_data = {}
current_lyrics = ""
subtext = cfg("SUBTEXT", "")
current_rivals_data = {}
chat_history = []
_d = cfg("DISABLE_LYRICS", False)
if isinstance(_d, str):
    disable_lyrics = _d.lower() == "true"
else:
    disable_lyrics = bool(_d)


@socketio.on("init_client")
def on_connect():
    global current_data, current_lyrics, subtext, current_rivals_data, disable_lyrics, chat_history
    emit("rivals_info", current_rivals_data)
    emit("subtext_info", {"subtext": subtext})
    emit("lyrics", {"disable": disable_lyrics})
    emit("lyrics", {"disabled": disable_lyrics})
    emit(
        "wmark_slides",
        {
            "slides": notnone(cfg("WMARK_SLIDES"))
            if cfg("WMARK_SLIDES")
            else []
        },
    )
    emit("chat_history", chat_history)
    emit("channel_info", {"channel": TWITCH_CHANNEL})


async def fetch_lyrics(artist, title):
    global lrclib, current_lyrics
    results = lrclib.search(
        track=title,
        artist=artist,
    )
    if results and results[0] and results[0].syncedLyrics:
        return results[0].syncedLyrics
    return None


async def monitor_playback():
    global last_title, current_data, current_lyrics
    print("Starting playback monitor...")

    while True:
        try:
            spotify_track = get_current_track_from_spotify()

            if not spotify_track or not spotify_track.get("item"):
                current_data = {
                    "artist_name": "",
                    "title": "",
                    "album_title": "",
                    "art_url": "",
                    "is_playing": False,
                    "progress": 0,
                    "duration": 0,
                    "start_time": 0,
                }
                current_lyrics = ""
                socketio.emit("playback_info", current_data)
                last_title = ""
                await asyncio.sleep(15)
                continue

            is_playing = spotify_track.get("is_playing", False)
            track = spotify_track.get("item", {})
            title = track.get("name", "")

            if title != last_title:
                last_title = title

                artists = track.get("artists", [])
                artist_name = (
                    ", ".join([artist.get("name", "") for artist in artists])
                    if artists
                    else ""
                )

                album = track.get("album", {})
                album_title = album.get("name", "")

                images = album.get("images", [])
                art_url = images[0].get("url") if images else None

                track_duration = track.get("duration_ms", 0) / 1000

                if not disable_lyrics and artist_name and title:
                    lyrics = await fetch_lyrics(artist_name, title)
                    if lyrics:
                        socketio.emit("playback_lyrics", {"lyrics": lyrics})
                        current_lyrics = lyrics
                    else:
                        socketio.emit("playback_lyrics", {"lyrics": ""})
                        current_lyrics = ""
                else:
                    socketio.emit("playback_lyrics", {"lyrics": ""})
                    current_lyrics = ""

                progress_ms = spotify_track.get("progress_ms", 0)
                timestamp_ms = spotify_track.get("timestamp", 0)
                start_time = timestamp_ms / 1000

                progress = (
                    (progress_ms / track.get("duration_ms", 1))
                    if track.get("duration_ms")
                    else 0
                )
                progress = min(max(progress, 0), 1)

                print(
                    f"Track: {title} by {artist_name}, "
                    f"Duration: {track_duration}s, Progress: {progress_ms}ms ({progress * 100:.1f}%)"
                )

                current_data = {
                    "artist_name": artist_name,
                    "title": title,
                    "album_title": album_title,
                    "art_url": art_url,
                    "is_playing": is_playing,
                    "progress": progress,
                    "duration": track_duration,
                    "start_time": start_time,
                }
            socketio.emit("playback_info", current_data)
            track_duration = track.get("duration_ms", 0) / 1000
            progress_ms = spotify_track.get("progress_ms", 0)
            progress = (
                (progress_ms / track.get("duration_ms", 1))
                if track.get("duration_ms")
                else 0
            )
            progress = min(max(progress, 0), 1)

            if (
                current_data.get("progress") != progress
                or current_data.get("is_playing") != is_playing
            ):
                timestamp_ms = spotify_track.get("timestamp", 0)
                start_time = timestamp_ms / 1000

                current_data.update(
                    {
                        "progress": progress,
                        "is_playing": is_playing,
                        "start_time": start_time,
                    }
                )
                socketio.emit("playback_info", current_data)

            await asyncio.sleep(2)

        except Exception as e:
            print(f"Error in monitor_playback: {e}")
            await asyncio.sleep(5)


async def monitor_rivals():
    global TRACKERGG_API_KEY, current_rivals_data, notnone
    print("Starting rivals monitor...")
    while True:
        try:
            rivals_user = notnone(cfg("RIVALS_USER"))
            url = f"https://api.tracker.gg/api/v2/marvel-rivals/standard/profile/ign/{rivals_user}?"
            flaresolverr_url = notnone(cfg("FLARESOLVERR_URL"))

            user = requests.post(
                flaresolverr_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": 15000,
                },
            )

            if user.status_code != 200:
                print(f"FlareSolverr request failed with status {user.status_code}")
                await asyncio.sleep(10)
                continue

            response_json = user.json()

            solution = response_json.get("solution", {})
            response_text = solution.get("response", "")

            if "<pre>" not in response_text or "</pre>" not in response_text:
                print("No <pre> tags found in response")
                await asyncio.sleep(10)
                continue

            text = response_text.split("<pre>")[1].split("</pre>")[0]

            user_data = json.loads(text).get("data", {})
            data = {
                "metadata": user_data.get("metadata", {}),
                "platform": user_data.get("platformInfo", {}),
                "user": user_data.get("userInfo", {}),
                "heroStats": list(
                    filter(
                        lambda x: x.get("type") == "hero", user_data.get("segments", [])
                    )
                ),
                "roleStats": list(
                    filter(
                        lambda x: x.get("type") == "hero-role",
                        user_data.get("segments", []),
                    )
                ),
            }
            current_rivals_data = data
            socketio.emit("rivals_info", data)
            await asyncio.sleep(15 * 60)
        except Exception as e:
            print(f"Error in monitor_rivals: {e}")
            import traceback

            traceback.print_exc()
            await asyncio.sleep(10)


@app.get("/img_proxy")
def img_proxy():
    url = flask.request.args.get("url", "")
    if not url:
        return flask.Response("No URL provided", status=400)
    try:
        resp = requests.get(url)
        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        ]
        headers = [
            (name, value)
            for (name, value) in resp.raw.headers.items()
            if name.lower() not in excluded_headers
        ]
        response = flask.Response(resp.content, resp.status_code, headers)
        return response
    except Exception as e:
        return flask.Response(f"Error fetching image: {e}", status=500)


@app.get("/static/<path:filename>")
def static_files(filename):
    if ".." in filename or filename.startswith("/"):
        return flask.Response("Invalid filename", status=400)
    return flask.send_file(os.path.join("static", filename))


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.create_task(monitor_playback())
    loop.create_task(monitor_rivals())
    loop.create_task(twitch_chat_listen())

    loop_thread = threading.Thread(target=loop.run_forever, name="asyncio_loop_thread")
    loop_thread.start()

    try:
        socketio.run(app, port=int(os.getenv("WIDGET_PORT", 5001)), host="127.0.0.1")
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, shutting down...")
    finally:

        def schedule_cancel_and_stop():
            async def _cancel_tasks_and_stop():
                try:
                    tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                except Exception as e:
                    print("Error cancelling tasks:", e)
                finally:
                    try:
                        loop.stop()
                    except Exception:
                        pass

            try:
                loop.call_soon_threadsafe(
                    asyncio.ensure_future, _cancel_tasks_and_stop()
                )
            except Exception as e:
                print("Failed to schedule cancellation on event loop:", e)

        schedule_cancel_and_stop()

        loop_thread.join(timeout=5)

        print("Shutdown complete. Exiting.")
        exit(0)
