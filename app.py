import os
from flask import Flask, request, jsonify
import yt_dlp
import logging
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Handle proxy headers for deployment
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configuration
DOWNLOAD_FOLDER = os.getenv('DOWNLOAD_FOLDER', 'downloads')

# Ensure download folder exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route('/')
def hello():
    return jsonify({
        'status': 'healthy',
        'message': 'YouTube Audio Downloader API is running'
    })

@app.route('/youtube-import', methods=['POST'])
def download():
    try:
        request_json = request.get_json(silent=True)
        if not request_json or 'youtube_url' not in request_json:
            return jsonify({
                'message': 'YouTube URL is required',
                'status': 400
            }), 400

        video_url = request_json['youtube_url']
        logger.info(f"Processing URL: {video_url}")

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            # Add YouTube access configuration
            'geo_bypass': True,
            'referer': 'https://www.youtube.com/',
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'cookiefile': os.path.join(DOWNLOAD_FOLDER, 'cookies.txt'),
            'noplaylist': True,
            'ignoreerrors': False,
            'verbose': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=True)
                audio_file = f"{info['title']}.mp3"
                file_path = os.path.join(DOWNLOAD_FOLDER, audio_file)
                
                if not os.path.exists(file_path):
                    raise Exception("File was not downloaded successfully")

                return jsonify({
                    'message': 'Download successful',
                    'audio_file': audio_file,
                    'file_path': file_path,
                    'status': 200
                }), 200

            except yt_dlp.utils.DownloadError as e:
                logger.error(f"YouTube access error: {str(e)}")
                return jsonify({
                    'message': f"YouTube content unavailable: {str(e)}",
                    'status': 403,
                    'error_code': e.exc_info[0].code if hasattr(e, 'exc_info') else 'UNKNOWN'
                }), 403

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'message': f"An error occurred: {str(e)}",
            'status': 500
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    # Use gunicorn in production, Flask's development server in development
    if os.environ.get('ENVIRONMENT') == 'production':
        # This will be used by gunicorn
        app
    else:
        app.run(host='0.0.0.0', port=port, debug=True)