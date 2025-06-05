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
        return {'message': 'YouTube URL is required', 'status': 400}

    url = request_json['youtube_url']
    ydl_opts = {
        'format': "140",
        'outtmpl': '%(id)s.%(ext)s',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(info['url'])
            video_url = info['url'] if 'url' in info else 'Video URL not found'
            return  video_url
    except Exception as e:
        return {'message': str(e), 'status': 500}

# This part is for running locally or in a server that supports Flask directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)

# This part is for running as a Cloud Function with functions_framework
import functions_framework

@functions_framework.http
def function_handler(request):
    return download()

app = function_handler

if __name__ == '__main__':
    function_handler()