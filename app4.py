from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'supersecretkey')

# Spotify OAuth setup
scope = "playlist-read-private"
sp_oauth = SpotifyOAuth(
    client_id=os.environ.get('SPOTIFY_CLIENT_ID'),
    client_secret=os.environ.get('SPOTIFY_CLIENT_SECRET'),
    redirect_uri=os.environ.get('SPOTIFY_REDIRECT_URI'),
    scope=scope,
    cache_path=".spotifycache"
)



def get_spotify_client():
    token_info = session.get('token_info')
    if not token_info:
        return None, jsonify({'error': 'Not authorized'}), 403

    # Refresh token if expired
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info

    sp = spotipy.Spotify(auth=token_info['access_token'])
    return sp, None, None


@app.route('/')
def index():
    if 'token_info' not in session:
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return render_template('index.html')


@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('index'))

@app.route('/playlist_tracks')
def playlist_tracks():
    sp, error_response, status = get_spotify_client()
    if error_response:
        return error_response, status

    playlists = sp.current_user_playlists(limit=1)
    if not playlists['items']:
        return jsonify({'error': 'No playlists found'}), 404

    first_playlist = playlists['items'][0]
    playlist_id = first_playlist['id']

    # Load full playlist using pagination
    tracks = []
    offset = 0
    while True:
        results = sp.playlist_items(playlist_id, offset=offset, limit=100)
        for item in results['items']:
            track = item['track']
            if track is None:
                continue
            track_name = track['name']
            artists = ', '.join(artist['name'] for artist in track['artists'])
            tracks.append({'name': track_name, 'artists': artists})
        if results['next']:
            offset += 100
        else:
            break

    return jsonify(tracks)


@app.route('/youtube_search')
def youtube_search():
    track = request.args.get('track')
    artists = request.args.get('artists', '')

    if not track:
        return jsonify({'error': 'Missing track name'}), 400

    artist_overrides = {
        'sassyde': 'Lenka',
        'cassedy': 'Lenka',
    }

    artists_norm = artists.lower().strip()
    override_artist = None
    for key in artist_overrides:
        if key in artists_norm:
            override_artist = artist_overrides[key]
            break

    if override_artist:
        query = f"{override_artist} \"{track}\""
    else:
        query = f"{artists} \"{track}\"" if artists else f"\"{track}\""

    ydl_opts = {
        'quiet': True,
        'format': 'bestaudio/best',
        'noplaylist': True,
        'default_search': 'ytsearch1',
        'extract_flat': False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]

            return jsonify({
                'videoId': info.get('id'),
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'description': info.get('description'),
                'audio_url': info.get('url')
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


    
if __name__ == '__main__':
    app.run(debug=True, port=8888)
