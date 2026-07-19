import os
import io
import requests
from flask import Flask, jsonify, request, send_file
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from PIL import Image

app = Flask(__name__)

# The script checks the environment variables first.
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID", "YOUR_LOCAL_FALLBACK_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET", "YOUR_LOCAL_FALLBACK_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:5000/callback")

CACHE_PATH = "./.spotify_cache"

sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope="user-read-currently-playing",
    cache_path=CACHE_PATH,
    open_browser=False
)

# ── GLOBAL IMAGE CACHE ────────────────────────────────────────────────
global_state = {
    "current_spotify_art_url": ""
}

# ── IMAGE INTERCEPTION PIPELINE ────────────────────────────────────
@app.route('/get_track_art', methods=['GET'])
def get_track_art():
    try:
        spotify_url = global_state.get("current_spotify_art_url")
        if not spotify_url:
            img = Image.new('RGB', (300, 300), color=(25, 25, 25))
            return serve_pil_image(img)

        response = requests.get(spotify_url, timeout=5)
        if response.status_code != 200:
            raise Exception("Failed to fetch image stream from Spotify")

        img = Image.open(io.BytesIO(response.content))
        
        # TRANSFORMATION ROUTE:
        img = img.convert('RGB')
        img = img.resize((300, 300), Image.Resampling.LANCZOS)
        
        return serve_pil_image(img)

    except Exception as e:
        print(f"Pillow Processing Engine Failure: {e}")
        fail_img = Image.new('RGB', (300, 300), color=(20, 20, 20))
        return serve_pil_image(fail_img)

def serve_pil_image(pil_img):
    """Helper layout logic to stream the image out over HTTP as a clean baseline JPEG"""
    img_io = io.BytesIO()
    # HARD STAGE BASELINE PARSING CODE: Added optimize=False to block progressive shifts completely
    pil_img.save(img_io, 'JPEG', quality=80, progressive=False, optimize=False)
    img_io.seek(0)
    return send_file(img_io, mimetype='image/jpeg')


# ── TRACK METADATA ROUTE ─────────────────────────────────────────────
@app.route('/get_track', methods=['GET'])
def get_track():
    token_info = sp_oauth.validate_token(sp_oauth.cache_handler.get_cached_token())
    if not token_info:
        return jsonify({
            "playing": False, 
            "error": "Authentication required. Visit /login endpoint first."
        }), 401

    sp = spotipy.Spotify(auth=token_info['access_token'])
    try:
        current_track = sp.current_user_playing_track()
        if current_track and current_track.get('is_playing'):
            track_name = current_track['item']['name']
            artist_name = current_track['item']['artists'][0]['name']
            
            raw_spotify_url = current_track['item']['album']['images'][1]['url']
            global_state["current_spotify_art_url"] = raw_spotify_url
            
            host_url = request.host_url.rstrip('/')
            
            return jsonify({
                "playing": True,
                "track": track_name,
                "artist": artist_name,
                "image_url": f"{host_url}/get_track_art"
            })
        
        global_state["current_spotify_art_url"] = ""
        return jsonify({"playing": False, "msg": "No active playback detected"})
        
    except Exception as e:
        return jsonify({"playing": False, "error": str(e)}), 500

@app.route('/login')
def login():
    auth_url = sp_oauth.get_authorize_url()
    return f'''
    <html>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h2>Spotify Display Box Auth</h2>
            <p>Click the link below to grant playback access.</p>
            <a href="{auth_url}" style="padding: 10px 20px; background: #1DB954; color: white; text-decoration: none; border-radius: 20px; font-weight: bold;">Authorize Spotify</a>
        </body>
    </html>
    '''

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if code:
        sp_oauth.get_access_token(code)
        return "<h3>Authentication successful! Your ESP32 frame can now read live metadata.</h3>"
    return "<h3>Error: Authorization token missing from callback request.</h3>", 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)