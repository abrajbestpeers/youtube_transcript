import os
from flask import Flask, request
import yt_dlp
import json

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

@app.route('/youtube-import', methods=['POST'])
def download():
    request_json = request.get_json(silent=True)
    if not request_json or 'youtube_url' not in request_json:
        return {'message': 'YouTube URL is required', 'status': 400}, 400

    url = request_json['youtube_url']
    ydl_opts = {
        'format': "140",
        'outtmpl': '%(id)s.%(ext)s',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info['url'] if 'url' in info else 'Video URL not found'
            return {'video_url': video_url, 'status': 200}
    except Exception as e:
        return {'message': str(e), 'status': 500}, 500

# This is the Flask app instance that gunicorn will use
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)