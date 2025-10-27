import json
import flask
from flask import Flask, Response
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

dotenv.load_dotenv()

TRACKERGG_API_KEY = os.getenv("TRACKERGG_API_KEY")
assert TRACKERGG_API_KEY, "TRACKERGG_API_KEY environment variable not set"

SPOT_API_KEY = os.getenv("SPOT_API_KEY")
SPOT_API_SECRET = os.getenv("SPOT_API_SECRET")

assert SPOT_API_KEY, "SPOT_API_KEY environment variable not set"
assert SPOT_API_SECRET, "SPOT_API_SECRET environment variable not set"

username = os.getenv("LASTFM_USER") or ""

def get_spotify_client():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOT_API_KEY,
        client_secret=SPOT_API_SECRET,
        redirect_uri="http://127.0.0.1:5000/callback",
        scope="user-read-currently-playing"
    ))

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

@app.route("/music")
def home():
    return flask.send_file("pages/music.htm")

@app.route("/rivals")
def rivals():
    return flask.send_file("pages/rivals.htm")

@app.route("/wmark")
def watermark():
    return flask.send_file("pages/wmark.htm")

@app.route("/logo.svg")
def logo():
    return flask.send_file("logo.svg")


last_title = ""
lrclib = LRCLib()
current_data = {}
current_lyrics = ""
subtext = os.getenv("SUBTEXT", "")
current_rivals_data = {}
disable_lyrics = os.getenv("DISABLE_LYRICS", "false").lower() == "true"

@socketio.on("init_client")
def on_connect():
    global current_data, current_lyrics, subtext, current_rivals_data, disable_lyrics
    emit("rivals_info", current_rivals_data)
    emit("subtext_info", {"subtext": subtext})
    emit("lyrics", {"disable": disable_lyrics})
    emit("lyrics", {"disabled": os.getenv("DISABLE_LYRICS", "false").lower() == "true"})
    emit("wmark_slides", {"slides": notnone(os.getenv("WMARK_SLIDES")).split(";") if os.getenv("WMARK_SLIDES") else []})


async def fetch_lyrics(artist, title):
    global lrclib, current_lyrics
    results = lrclib.search(
        track=title,
        artist=artist,
    )
    if results and results[0] and results[0].syncedLyrics:
        print(results[0].syncedLyrics)
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
                artist_name = ", ".join([artist.get("name", "") for artist in artists]) if artists else ""
                
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
                
                progress = (progress_ms / track.get("duration_ms", 1)) if track.get("duration_ms") else 0
                progress = min(max(progress, 0), 1)
                
                print(
                    f"Track: {title} by {artist_name}, "
                    f"Duration: {track_duration}s, Progress: {progress_ms}ms ({progress*100:.1f}%)"
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
            progress = (progress_ms / track.get("duration_ms", 1)) if track.get("duration_ms") else 0
            progress = min(max(progress, 0), 1)
            
            if current_data.get("progress") != progress or current_data.get("is_playing") != is_playing:
                timestamp_ms = spotify_track.get("timestamp", 0)
                start_time = timestamp_ms / 1000
                
                current_data.update({
                    "progress": progress,
                    "is_playing": is_playing,
                    "start_time": start_time,
                })
                socketio.emit("playback_info", current_data)
            
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error in monitor_playback: {e}")
            await asyncio.sleep(5)

def notnone(val):
     assert val is not None
     return val

async def monitor_rivals():
    global TRACKERGG_API_KEY, current_rivals_data, notnone
    print("Starting rivals monitor...")
    while True:
        try:
            rivals_user = notnone(os.getenv("RIVALS_USER"))
            url = f"https://api.tracker.gg/api/v2/marvel-rivals/standard/profile/ign/{rivals_user}?"
            print(f"Making direct request to: {url}")
            
            flaresolverr_url = notnone(os.getenv("FLARESOLVERR_URL"))
            print(f"Making request to FlareSolverr: {flaresolverr_url} for URL: {url}")
            
            user = requests.post(flaresolverr_url, headers={ "Content-Type": "application/json", "Accept": "application/json" }, json={
                 "cmd": "request.get",
                 "url": url,
                 "maxTimeout": 15000,
            })
            print(f"FlareSolverr response status: {user.status_code}")
            print(f"FlareSolverr response text (first 500 chars): {user.text[:500]}")
            
            if user.status_code != 200:
                print(f"FlareSolverr request failed with status {user.status_code}")
                await asyncio.sleep(10)
                continue
            
            response_json = user.json()
            print(f"FlareSolverr JSON response: {response_json}")
            
            solution = response_json.get("solution", {})
            response_text = solution.get("response", "")
            print(f"Extracted response text (first 500 chars): {response_text[:500]}")
            
            if "<pre>" not in response_text or "</pre>" not in response_text:
                print("No <pre> tags found in response")
                await asyncio.sleep(10)
                continue
            
            text = response_text.split("<pre>")[1].split("</pre>")[0]
            print(f"Extracted JSON text: {text}")
            
            user_data = json.loads(text).get("data", {})
            data = {
                "metadata": user_data.get("metadata", {}),
                "platform": user_data.get("platformInfo", {}),
                "user": user_data.get("userInfo", {}),
                "heroStats": list(filter(lambda x: x.get("type") == "hero", user_data.get("segments", []))),
                "roleStats": list(filter(lambda x: x.get("type") == "hero-role", user_data.get("segments", []))),
            }
            current_rivals_data = data
            socketio.emit("rivals_info", data)
            await asyncio.sleep(15*60)
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
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]
        response = flask.Response(resp.content, resp.status_code, headers)
        return response
    except Exception as e:
        return flask.Response(f"Error fetching image: {e}", status=500)

@app.get("/static/<path:filename>")
def static_files(filename):
    if '..' in filename or filename.startswith('/'):
        return flask.Response("Invalid filename", status=400)
    return flask.send_file(os.path.join("static", filename))

def make_stream_app():
    app2 = Flask("stream_app")

    @app2.get("/")
    def index():
        return flask.send_file("pages/st/index.html")

    @app2.get("/stream")
    def stream():
        r = requests.get("http://localhost:8080/live/livestream.flv", stream=True)
        headers = {
            "Content-Type": "video/x-flv",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        def generate_chunks():
            with r.raw as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    yield chunk

        return Response(generate_chunks(), mimetype='video/x-flv', headers=headers)

    app2.run(port=8005, host="127.0.0.1")
    
    

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(monitor_playback())
    loop.create_task(monitor_rivals())
    threading.Thread(target=make_stream_app).start()
    threading.Thread(target=loop.run_forever).start()
    socketio.run(app, port=int(os.getenv("WIDGET_PORT", 5001)), host="127.0.0.1")
