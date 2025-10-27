# damnmusic

For Rivals footage. Supports lyrics (occasionally) and album art. Also sucks because sometimes the lyrics are offset but I can't fix that. Thanks Spotify.
Occasionally transitions/animations conflict but ignore it.
Did I mention it's modern and has nice looking animations?

## Setup

```bun run inst```
OR
```npm run inst```
OR
```python3 -m pip install -r requirements.txt```

## Environment Variables

`.env` file

```env
SPOT_API_KEY=your_spotify_api_key
SPOT_API_SECRET=your_spotify_api_secret
FLARESOLVERR_URL=your_flaresolverr_url (optional)
RIVALS_USER=your_rivals_username (optional)
TRACKERGG_API_KEY=your_trackergg_api_key (optional)
SUBTEXT=your_custom_subtext (optional)
WIDGET_PORT=your_widget_port (optional, default 5001)
DISABLE_LYRICS=true/false (optional, default false)
WMARK_SLIDES=/static/wmark.png;thing 1;thing 2;etc (optional, semicolon separated list of images/text for watermark slideshow)
```

Add `http://localhost:5000/callback` as a Redirect URI in your Spotify Developer Dashboard for the app btw.

## Usage

Run with
```bun run start```
OR
```npm run start```
OR
```python3 main.py```

Sign in on any device with the Spotify account connected to the Spotify API application.
Open `http://localhost:5001/music` in your browser to see the now playing info or (for me) add as a Browser source in OBS.

For streaming support, run the streamtop server:
```cd streamtop && bun run dev```
OR
```cd streamtop && npm run dev```
OR
```cd streamtop && npx tsx index.ts```

Then, in OBS, go to Settings > Stream, select Custom, set Server to `rtmp://localhost:1935/live`, and Stream Key to `your_username?password=your_password`.

Open `http://localhost:8005` to view the stream.

Also I suggest you use the Composite Blur plugin with a scaled display source to make it look nice, which is what I do for clips.

## License

Add `http://localhost:5000/callback` as a Redirect URI in your Spotify Developer Dashboard for the app btw.

## Usage

Run with
```bun run start```
OR
```npm run start```
OR
```python3 main.py```

Sign in on any device with the Spotify account connected to the Spotify API application.
Open `http://localhost:5001/music` in your browser to see the now playing info or (for me) add as a Browser source in OBS.


Also I suggest you use the Composite Blur plugin with a scaled display source to make it look nice, which is what I do for clips.

## License

WTFPL(+), I don't care what you do with this, hopefully this now playing application isn't used for global warfare. And if so, don't sue me for it.

## Garbage

**I'm a stonethrow away, laughing down the scale.**
