from flask import Flask, redirect, request, session, url_for, render_template_string, jsonify
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import requests
import isodate
from rapidfuzz import fuzz
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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Playlist: {{ playlist_name }}</title>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      margin: 0;
      padding: 0;
      background-color: #121212;
      color: #f5f5f5;
      overflow: hidden;
    }

    .player-container {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 1000;
      background-color: #1e1e1e;
      padding: 10px;
      box-shadow: 0 4px 8px rgba(0,0,0,0.3);
      text-align: center;
    }

    #player {
      width: 100%;
      max-width: 640px;
      margin: 0 auto;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 0 20px #000;
    }

    #video-info {
      display: none;
      align-items: center;
      gap: 10px;
      background: #2a2a2a;
      padding: 10px;
      border-radius: 8px;
      margin-top: 10px;
    }

    #video-thumb {
      width: 80px;
      height: 60px;
      object-fit: cover;
      border-radius: 6px;
    }

    #video-title {
      font-size: 14px;
      flex-grow: 1;
    }

    .scrollable-playlist {
      margin-top: 340px; /* Adjust based on player height */
      padding: 10px;
      overflow-y: scroll;
      height: calc(100vh - 340px);
      -webkit-overflow-scrolling: touch;
    }

    h1 {
      margin: 0;
      font-size: 18px;
      text-align: center;
      color: #1db954;
    }

    ul {
      list-style: none;
      padding-left: 0;
      margin: 0;
    }

    li {
      margin-bottom: 12px;
      padding: 12px 16px;
      background: #1e1e1e;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.3s ease;
      border: 1px solid transparent;
    }

    li:hover {
      background: #2a2a2a;
      border: 1px solid #1db954;
    }

    li.playing {
      background: #1db954;
      color: white;
      border: 1px solid #fff;
    }

    #status {
      text-align: center;
      margin: 10px 0;
      padding: 10px;
      border-radius: 5px;
      font-size: 14px;
    }

    .loading { background: #1c1c2b; color: #7ec6e9; }
    .error { background: #2b1c1c; color: #ff6666; }
    .success { background: #1c2b1c; color: #66ff66; }

    button {
      padding: 10px 20px;
      background: #1db954;
      color: white;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      margin-top: 10px;
    }

    button:hover {
      background: #1aa34a;
    }

    /* Optional custom scrollbar for webkit browsers */
    .scrollable-playlist::-webkit-scrollbar {
      width: 8px;
    }

    .scrollable-playlist::-webkit-scrollbar-track {
      background: #121212;
    }

    .scrollable-playlist::-webkit-scrollbar-thumb {
      background: #333;
      border-radius: 4px;
    }

  </style>
</head>
<body>

  <!-- Fixed Player Section -->
  <div class="player-container">
    <div id="status" class="loading">Select a song to play...</div>
    <div id="video-info">
      <img id="video-thumb" src="" alt="thumbnail">
      <div>
        <div id="video-title"></div>
        <div style="font-size: 12px; color: #aaa;">Now Playing</div>
      </div>
    </div>
    <div id="player"></div>
    <div style="text-align: center; margin-top: 10px;">
      <button id="play-btn" onclick="startPlaying()" style="display: none;">▶ Click to Play</button>
    </div>
  </div>

  <!-- Scrollable Playlist Section -->
  <div class="scrollable-playlist">
    <h1>Playlist: {{ playlist_name }}</h1>
    <ul>
      {% for track in tracks %}
        <li data-track-id="{{ track.id }}" onclick='playSong({{ track.id|tojson }}, {{ track.name|tojson }}, {{ track.artists|tojson }}, this)'>
          <b>{{ track.name }}</b> — {{ track.artists }}
        </li>
      {% endfor %}
    </ul>
  </div>

  <!-- YouTube API -->
 <script src="https://www.youtube.com/iframe_api"></script>

  <script>
    let currentVideoId = null;
    let currentTrackElement = null;
    let currentTrackId = null;
    let ytPlayer = null;
    let tracksArray = [];
    let currentMatches = [];
    let currentMatchIndex = 0;

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
        currentMatchIndex = 0;
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

            if (data.matches && data.matches.length > 0) {
                currentMatches = data.matches;
                currentMatchIndex = 0;
                playNextValidMatch();
            } else {
                updateStatus('Song not found on YouTube.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            updateStatus('Error: ' + error.message, 'error');
        }
    }

    function playNextValidMatch() {
        if (currentMatchIndex >= currentMatches.length) {
            updateStatus('No playable match found.', 'error');
            return;
        }

        const match = currentMatches[currentMatchIndex];
        currentMatchIndex++;

        displayVideo(match);

        if (!ytPlayer) {
            ytPlayer = new YT.Player('player', {
                height: '270',
                width: '100%',
                videoId: match.videoId,
                playerVars: { autoplay: 1, rel: 0, enablejsapi: 1 },
                events: {
                    'onStateChange': onPlayerStateChange,
                    'onError': onPlayerError
                }
            });
        } else {
            ytPlayer.loadVideoById(match.videoId);
        }
    }

    function onPlayerError(event) {
        console.warn("Player error:", event.data);
        // Try next match
        playNextValidMatch();
    }

    function displayVideo(match) {
        const videoInfoDiv = document.getElementById('video-info');
        const videoThumb = document.getElementById('video-thumb');
        const videoTitle = document.getElementById('video-title');
        videoInfoDiv.style.display = 'flex';
        videoThumb.src = match.thumbnail;
        videoTitle.innerHTML = `
            <div style="font-size:14px; font-weight:bold;">${match.title}</div>
            <div style="font-size:12px; color:#aaa;">${match.description.slice(0, 80)}...</div>
          `;
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
    query = request.args.get('q')
    if not query:
        return jsonify({'error': 'Missing query parameter'}), 400

    # Parse song and artist
    words = query.strip().split()
    if len(words) > 1:
        artist = words[-1].lower()
        song = " ".join(words[:-1])
    else:
        artist = ""
        song = query

    # Artist override logic
    artist_overrides = {
        'sassydee': 'lenka'
    }
    if artist in artist_overrides:
        artist = artist_overrides[artist]

    def perform_search(search_query):
        search_url = 'https://www.googleapis.com/youtube/v3/search'
        params = {
            'part': 'snippet',
            'q': f"{search_query} official audio lyrics",
            'type': 'video',
            'maxResults': 10,
            'key': YOUTUBE_API_KEY
        }
        r = requests.get(search_url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get('items', [])

    def get_video_details(video_id):
        video_url = 'https://www.googleapis.com/youtube/v3/videos'
        params = {
            'part': 'status,contentDetails,snippet',
            'id': video_id,
            'key': YOUTUBE_API_KEY
        }
        r = requests.get(video_url, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get('items', [])
        if not items:
            return None
        item = items[0]
        content_details = item.get('contentDetails', {})
        status = item.get('status', {})
        snippet = item.get('snippet', {})

        duration = content_details.get('duration', 'PT0S')
        try:
            td = isodate.parse_duration(duration)
            duration_sec = td.total_seconds()
        except:
            duration_sec = 0

        return {
            'embeddable': status.get('embeddable', True),
            'privacyStatus': status.get('privacyStatus'),
            'regionRestricted': 'regionRestriction' in content_details.get('regionRestriction', {}),
            'durationSec': duration_sec,
            'title': snippet.get('title'),
            'description': snippet.get('description'),
            'thumbnail': snippet.get('thumbnails', {}).get('default', {}).get('url', ""),
        }

    def score_result(details, require_artist=True):
      title = details['title'].lower()
      description = (details['description'] or '').lower()
      channel = details.get('channelTitle', '').lower()
      score = 0

      if details['privacyStatus'] != 'public':
          return -1
      if details['durationSec'] < 60:
          return -1
      if details['regionRestricted']:
          return -1
      if not details['embeddable']:
          return -1

      if require_artist:
        # Check artist in title or description or channel title fuzzy match
        artist_in_title = artist in title
        artist_in_description = artist in description
        artist_in_channel = fuzz.partial_ratio(artist, channel) > 70

        if artist_in_title or artist_in_description or artist_in_channel:
            score += 5
        else:
            return -1  # reject if artist required but not present
      else:
        if artist in title or artist in description or fuzz.partial_ratio(artist, channel) > 70:
            score += 5

      # rest unchanged...
      if 'official' in title or 'official' in description:
          score += 3
      if 'audio' in title:
          score += 2
      if 'lyric' in title or 'lyrics' in title:
          score += 1
      if 'remix' in title or 'cover' in title:
          score -= 2
      if 'live' in title or 'performance' in title:
          score -= 1

      fuzzy_similarity = fuzz.ratio(query.lower(), details['title'].lower())
      score += fuzzy_similarity / 20

      return score


    candidates = []
    search_variants = [f"{song} {artist}".strip(), song]

    for i, variant in enumerate(search_variants):
        require_artist = (i == 0)  # Only require artist on first search (song+artist)
        items = perform_search(variant)
        for item in items:
            video_id = item.get('id', {}).get('videoId')
            if not video_id:
                continue
            details = get_video_details(video_id)
            if not details:
                continue
            score = score_result(details, require_artist=require_artist)
            if score > -1:
                candidates.append({
    'score': score,
    'videoId': video_id,
    'title': details['title'],
    'description': details['description'],
    'thumbnail': details['thumbnail'],
    'channel': details.get('channelTitle', '')
})

        if candidates:
            break


    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:3]

    if top_candidates:
        return jsonify({'matches': top_candidates})
    else:
        return jsonify({'error': 'No suitable match found'})


if __name__ == '__main__':
    app.run(port=8888, debug=True)
