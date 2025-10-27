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

dotenv.load_dotenv()

SPOT_API_KEY = os.getenv("SPOT_API_KEY")
SPOT_API_SECRET = os.getenv("SPOT_API_SECRET")

assert SPOT_API_KEY, "SPOT_API_KEY environment variable not set"
assert SPOT_API_SECRET, "SPOT_API_SECRET environment variable not set"

username = os.getenv("LASTFM_USER") or ""

def get_spotify_client():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOT_API_KEY,
        client_secret=SPOT_API_SECRET,
        redirect_uri="http://localhost:5000/callback",
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


@app.route("/")
def home():
    return flask.send_file("index.htm")


@app.route("/logo.svg")
def logo():
    return flask.send_file("logo.svg")


last_title = ""
lrclib = LRCLib()
current_data = {}
current_lyrics = ""
subtext = os.getenv("SUBTEXT", "")

@socketio.on("init_client")
def on_connect():
    global current_data, current_lyrics, subtext
    emit("subtext_info", {"subtext": subtext})


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
                
                if artist_name and title:
                    lyrics = await fetch_lyrics(artist_name, title)
                    if lyrics:
                        socketio.emit("playback_lyrics", {"lyrics": lyrics})
                        current_lyrics = lyrics
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


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    threading.Thread(
        target=lambda: loop.run_until_complete(monitor_playback()), daemon=True
    ).start()
    socketio.run(app, port=5000)
