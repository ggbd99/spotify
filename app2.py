from flask import Flask, redirect, request, session, url_for, render_template_string, jsonify
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import requests

app = Flask(__name__)
app.secret_key = os.urandom(24)



# === Spotify Credentials ===
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
SCOPE = 'playlist-read-private playlist-read-collaborative user-read-private user-read-email'

# === YouTube API ===
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')



@app.route('/')
def index():
    sp_oauth = SpotifyOAuth(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, scope=SCOPE)
    if 'token_info' not in session:
        return redirect(sp_oauth.get_authorize_url())

    token_info = session['token_info']
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info

    sp = spotipy.Spotify(auth=token_info['access_token'])
    playlists = sp.current_user_playlists()

    if not playlists['items']:
        return "You have no playlists."

    first_playlist = playlists['items'][0]
    playlist_id = first_playlist['id']
    playlist_name = first_playlist['name']

    tracks = []
    results = sp.playlist_items(playlist_id, limit=100, offset=0)
    while results:
        for item in results['items']:
            track = item['track']
            if track:
                tracks.append({
                    'name': track['name'],
                    'artists': ', '.join([artist['name'] for artist in track['artists']]),
                    'id': track['id']
                })
        if results['next']:
            results = sp.next(results)
        else:
            results = None

    # Render template with playlist and player
    return render_template_string('''
<html>
<head>
  <title>Playlist: {{ playlist_name }}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
    .container { display: flex; }
    .playlist-container { flex: 1; padding-right: 20px; }
    .player-container { width: 640px; position: sticky; top: 20px; }
    ul { list-style: none; padding-left: 0; }
    li { 
      margin-bottom: 12px; 
      padding: 10px; 
      background: #f5f5f5; 
      border-radius: 5px; 
      cursor: pointer;
      transition: background 0.2s;
    }
    li:hover {
      background: #e0e0e0;
    }
    li.playing {
      background: #1db954;
      color: white;
    }
    #player { margin-bottom: 20px; }
    #video-info { 
      display: none; 
      align-items: center; 
      gap: 10px; 
      background: #f9f9f9; 
      padding: 15px; 
      border-radius: 5px;
      margin-bottom: 15px;
    }
    #video-thumb { width: 120px; height: 90px; object-fit: cover; border-radius: 4px; }
    #video-title { font-weight: bold; font-size: 16px; flex-grow: 1; }
    #status { 
      text-align: center; 
      margin: 20px 0; 
      padding: 10px; 
      border-radius: 5px; 
    }
    .loading { background: #e3f2fd; color: #1976d2; }
    .error { background: #ffebee; color: #c62828; }
    .success { background: #e8f5e8; color: #2e7d32; }
    button { 
      padding: 8px 16px; 
      background: #1db954; 
      color: white; 
      border: none; 
      border-radius: 4px; 
      cursor: pointer; 
      margin: 5px; 
    }
    button:hover { background: #1aa34a; }
    h1 { margin-top: 0; }
  </style>
</head>
<body>
  <div class="container">
    <div class="playlist-container">
      <h1>Playlist: {{ playlist_name }}</h1>
      <ul>
        {% for track in tracks %}
          <li data-track-id="{{ track.id }}" onclick='playSong({{ track.id|tojson }}, {{ track.name|tojson }}, {{ track.artists|tojson }}, this)'>
            <b>{{ track.name }}</b> — {{ track.artists }}
          </li>
        {% endfor %}
      </ul>
    </div>

    <div class="player-container">
      <div id="status" class="loading">
        Select a song to play...
      </div>

      <div id="video-info">
        <img id="video-thumb" src="" alt="thumbnail">
        <div>
          <div id="video-title"></div>
          <div style="font-size: 12px; color: #666; margin-top: 5px;">Now Playing</div>
        </div>
      </div>

      <div id="player"></div> <!-- YouTube Player will be injected here -->

      <div style="text-align: center; margin-top: 10px;">
        <button id="play-btn" onclick="startPlaying()" style="display: none;">▶ Click to Play</button>
      </div>
    </div>
  </div>

  <script src="https://www.youtube.com/iframe_api "></script>

  <script>
    let currentVideoId = null;
    let currentTrackElement = null;
    let currentTrackId = null;
    let ytPlayer = null;
    let tracksArray = [];

    // Populate tracks array on load
    document.querySelectorAll('li[data-track-id]').forEach((li, index) => {
        const trackId = li.getAttribute('data-track-id');
        const trackName = li.querySelector('b').textContent;
        const artists = li.textContent.replace(trackName, '').trim();
        tracksArray.push({ element: li, trackId: trackId, name: trackName, artists: artists });
    });

    function playSong(trackId, trackName, artists, element) {
        if (currentTrackId === trackId) return;

        if (currentTrackElement) currentTrackElement.classList.remove('playing');
        element.classList.add('playing');
        currentTrackElement = element;
        currentTrackId = trackId;

        const query = trackName + ' ' + artists;
        loadSong(query);
    }

    async function loadSong(query) {
        updateStatus('Searching YouTube...', 'loading');

        try {
            const encodedQuery = encodeURIComponent(query);
            const response = await fetch('/youtube_search?q=' + encodedQuery);

            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

            const data = await response.json();

            if (data.error) throw new Error(data.error);

            if (data.videoId) {
                currentVideoId = data.videoId;
                displayVideo(data);
                updateStatus('Playing...', 'success');
                document.getElementById('play-btn').style.display = 'none';

                if (!ytPlayer) {
                    ytPlayer = new YT.Player('player', {
                        height: '360',
                        width: '640',
                        videoId: data.videoId,
                        playerVars: { autoplay: 1, rel: 0, enablejsapi: 1 },
                        events: {
                            'onStateChange': onPlayerStateChange
                        }
                    });
                } else {
                    ytPlayer.loadVideoById(data.videoId);
                }
            } else {
                updateStatus('Song not found on YouTube.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            updateStatus('Error: ' + error.message, 'error');
        }
    }

    function displayVideo(data) {
        const videoInfoDiv = document.getElementById('video-info');
        const videoThumb = document.getElementById('video-thumb');
        const videoTitle = document.getElementById('video-title');

        videoInfoDiv.style.display = 'flex';
        videoThumb.src = data.thumbnail;
        videoTitle.textContent = data.title;
    }

    function startPlaying() {
        if (ytPlayer && currentVideoId) {
            ytPlayer.playVideo();
        }
    }

    function updateStatus(message, type) {
        const statusDiv = document.getElementById('status');
        statusDiv.textContent = message;
        statusDiv.className = type;
    }

    function onPlayerStateChange(event) {
        if (event.data === YT.PlayerState.ENDED) {
            playNextSong();
        }
    }

    function playNextSong() {
        const currentIndex = tracksArray.findIndex(t => t.trackId === currentTrackId);
        if (currentIndex === -1 || currentIndex >= tracksArray.length - 1) {
            updateStatus("End of playlist.", "success");
            return;
        }

        const nextTrack = tracksArray[currentIndex + 1];
        const nextElement = nextTrack.element;
        const nextTrackId = nextTrack.trackId;
        const nextName = nextTrack.name;
        const nextArtists = nextTrack.artists;

        playSong(nextTrackId, nextName, nextArtists, nextElement);
    }
  </script>
</body>
</html>
    ''', playlist_name=playlist_name, tracks=tracks)


@app.route('/callback')
def callback():
    sp_oauth = SpotifyOAuth(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, scope=SCOPE)
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('index'))


@app.route('/youtube_search')
def youtube_search():
    q = request.args.get('q')
    if not q:
        return jsonify({'error': 'Missing query parameter'}), 400

    url = 'https://www.googleapis.com/youtube/v3/search'
    params = {
        'part': 'snippet',
        'q': q,
        'type': 'video',
        'maxResults': 1,
        'key': YOUTUBE_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if 'error' in data:
            return jsonify({'error': f"YouTube API error: {data['error']['message']}"}), 400

        if 'items' in data and len(data['items']) > 0:
            video = data['items'][0]
            video_id = video['id']['videoId']
            snippet = video['snippet']

            result = {
                'videoId': video_id,
                'title': snippet['title'],
                'thumbnail': snippet['thumbnails']['default']['url']
            }
            return jsonify(result)
        else:
            return jsonify({'videoId': None, 'error': 'No videos found'})

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timeout'}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Request failed: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(port=8888, debug=True)