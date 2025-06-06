import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

@app.route('/youtube-import', methods=['POST'])
def download():
    request_json = request.get_json(silent=True)
    if not request_json or 'youtube_url' not in request_json:
        return {'message': 'YouTube URL is required', 'status': 400}, 400

    video_url = request_json['youtube_url']
    
    try:
        # Construct the request body
        payload = {
            # "filenamePattern": "pretty",
            # "isAudioOnly": True,
            "url": video_url
        }

        # Use the environment variable 'ENDPOINT' instead of hardcoded URL
        endpoint = os.getenv('ENDPOINT')
        if not endpoint:
            return {'message': 'ENDPOINT environment variable is not set', 'status': 500}, 500
        
        response = requests.post(endpoint, json=payload)
        response_data = response.json()

        if response.status_code != 200 or 'audioUrl' not in response_data:
            return {'message': 'Failed to retrieve video URL', 'status': response.status_code}, 500
        
        video_download_url = response_data['audioUrl']
        return video_download_url, 200

    except Exception as e:
        return {'message': str(e), 'status': 500}, 500

# This part is for running locally or in a server that supports Flask directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)