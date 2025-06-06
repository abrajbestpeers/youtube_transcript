import os
from flask import Flask, request, jsonify
import requests
import time
import logging
import subprocess
import random
import json
from datetime import datetime
import tempfile

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

ASSEMBLYAI_UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
ASSEMBLYAI_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"
ASSEMBLYAI_API_KEY = "f9ae68ba947a46ddbefed5684f83428d"

# List of common user agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def download_with_retry(video_url, max_retries=5, delay=10):
    temp_audio_file = "/tmp/temp_audio.mp3"
    user_agent = get_random_user_agent()
    
    for attempt in range(max_retries):
        try:
            # Remove file if it exists
            if os.path.exists(temp_audio_file):
                os.remove(temp_audio_file)
            
            # Construct yt-dlp command with enhanced options
            cmd = [
                'yt-dlp',
                '--no-warnings',
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0',
                '--add-header', f'User-Agent: {user_agent}',
                '--add-header', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                '--add-header', 'Accept-Language: en-US,en;q=0.5',
                '--add-header', 'Connection: keep-alive',
                '--add-header', 'Upgrade-Insecure-Requests: 1',
                '--add-header', 'Cache-Control: max-age=0',
                '--add-header', 'Sec-Fetch-Dest: document',
                '--add-header', 'Sec-Fetch-Mode: navigate',
                '--add-header', 'Sec-Fetch-Site: none',
                '--add-header', 'Sec-Fetch-User: ?1',
                '--geo-bypass',
                '--no-check-certificate',
                '--extractor-args', 'youtube:player_client=web',
                '--extractor-args', 'youtube:player_skip=webpage',
                '--extractor-args', 'youtube:player_params={"hl":"en"}',
                '--format', 'bestaudio/best',
                '--prefer-ffmpeg',
                '--postprocessor-args', '-vn',
                '--socket-timeout', '30',
                '--retries', '10',
                '--fragment-retries', '10',
                '--file-access-retries', '10',
                '--extractor-retries', '10',
                '--ignore-errors',
                '--no-abort-on-error',
                '--proxy', 'socks5://127.0.0.1:9050',  # Use Tor proxy
                '-o', temp_audio_file,
                video_url
            ]
            
            logging.debug(f"Attempt {attempt + 1}: Downloading with command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10-minute timeout
            )
            
            if result.returncode == 0 and os.path.exists(temp_audio_file):
                file_size = os.path.getsize(temp_audio_file)
                if file_size > 0:
                    logging.debug(f"Download successful on attempt {attempt + 1}, file size: {file_size} bytes")
                    return temp_audio_file
                else:
                    logging.warning(f"Download completed but file is empty on attempt {attempt + 1}")
            else:
                logging.warning(f"Attempt {attempt + 1} failed: {result.stderr}")
            
            if attempt < max_retries - 1:
                sleep_time = delay * (2 ** attempt)  # Exponential backoff with base delay
                logging.debug(f"Waiting {sleep_time} seconds before retry...")
                time.sleep(sleep_time)
            
        except subprocess.TimeoutExpired:
            logging.error(f"Download timed out on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
        except Exception as e:
            logging.error(f"Error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
    
    raise Exception(f"Failed to download after {max_retries} attempts")

@app.route('/')
def hello():
    return 'Hello, World!'

@app.route('/youtube-transcribe', methods=['POST'])
def youtube_transcribe():
    request_json = request.get_json(silent=True)
    if not request_json or 'youtube_url' not in request_json:
        return {'message': 'YouTube URL is required', 'status': 400}, 400

    video_url = request_json['youtube_url']
    
    try:
        # Step 1: Download audio from YouTube using yt-dlp with retry logic
        logging.debug(f"Downloading audio from YouTube URL: {video_url}")
        try:
            temp_audio_file = download_with_retry(video_url)
            logging.debug(f"Audio downloaded successfully to {temp_audio_file}")
        except Exception as e:
            logging.error(f"Error downloading audio: {str(e)}")
            return {'message': f'Error downloading audio: {str(e)}', 'status': 500}, 500

        # Step 2: Upload the audio file to AssemblyAI
        logging.debug("Uploading audio to AssemblyAI...")
        try:
            with open(temp_audio_file, "rb") as f:
                files = {'file': (temp_audio_file, f, 'audio/mp3')}
                upload_response = requests.post(
                    ASSEMBLYAI_UPLOAD_URL,
                    headers={'authorization': ASSEMBLYAI_API_KEY},
                    files=files
                )
            if upload_response.status_code != 200:
                logging.error(f"Failed to upload audio to AssemblyAI: {upload_response.status_code} - {upload_response.text}")
                raise Exception(f"Failed to upload audio to AssemblyAI: {upload_response.status_code} - {upload_response.text}")
        except Exception as e:
            logging.error(f"Error uploading to AssemblyAI: {str(e)}")
            raise Exception(f"Failed to upload to AssemblyAI: {str(e)}")

        # Step 3: Start transcription
        assembly_audio_url = upload_response.json()['upload_url']
        transcript_id = start_transcription(assembly_audio_url)
        transcript_text = wait_for_transcription(transcript_id)

        # Clean up temporary files
        try:
            os.remove(temp_audio_file)
        except Exception as e:
            logging.warning(f"Failed to clean up temporary files: {e}")

        return {'transcript': transcript_text, 'status': 200}, 200

    except Exception as e:
        logging.error(f"Error during transcription: {str(e)}")
        return {'message': str(e), 'status': 500}, 500

def start_transcription(audio_url):
    headers = {
        'authorization': ASSEMBLYAI_API_KEY,
        'content-type': 'application/json'
    }
    payload = {
        'audio_url': audio_url,
        'speech_model': 'universal'
    }
    logging.debug(f"Starting transcription for audio URL: {audio_url}")
    response = requests.post(ASSEMBLYAI_TRANSCRIPT_URL, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Failed to start transcription: {response.status_code} - {response.text}")
    return response.json()['id']

def wait_for_transcription(transcript_id, max_retries=10, interval=5):
    headers = {
        'authorization': ASSEMBLYAI_API_KEY
    }
    retries = 0
    while retries < max_retries:
        logging.debug(f"Polling transcription status for ID: {transcript_id}")
        response = requests.get(f"{ASSEMBLYAI_TRANSCRIPT_URL}/{transcript_id}", headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch transcription status: {response.status_code} - {response.text}")
        result = response.json()
        if result['status'] == 'completed':
            logging.debug("Transcription completed successfully.")
            return result['text']
        elif result['status'] == 'error':
            raise Exception(f"Transcription error: {result['error']}")
        retries += 1
        time.sleep(interval)
    raise Exception("Transcription polling failed after maximum retries")

# This part is for running locally or in a server that supports Flask directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)