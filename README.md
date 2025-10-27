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
Make in your `.env` file.   

```
SPOT_API_KEY=your_spotify_api_key
SPOT_API_SECRET=your_spotify_api_secret
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
Open `http://localhost:5000` in your browser to see the now playing info or (for me) add as a Browser source in OBS.   
   
Also I suggest you use the Composite Blur plugin with a scaled display source to make it look nice, which is what I do for clips.   


## License
WTFPL(+), I don't care what you do with this, hopefully this now playing application isn't used for global warfare. And if so, don't sue me for it.

## Garbage
**I'm a stonethrow away, laughing down the scale.**
