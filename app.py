import os
from flask import Flask, request, jsonify
import requests
import time
import logging
import subprocess

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

ASSEMBLYAI_UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
ASSEMBLYAI_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"
ASSEMBLYAI_API_KEY = "f9ae68ba947a46ddbefed5684f83428d"

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
        # Step 1: Download audio from YouTube
        payload = {"url": video_url}
        endpoint = "https://submagic-free-tools.fly.dev/api/youtube-to-audio"
        if not endpoint:
            return {'message': 'ENDPOINT environment variable is not set', 'status': 500}, 500
        
        response = requests.post(endpoint, json=payload)
        response_data = response.json()
        if response.status_code != 200 or 'audioUrl' not in response_data:
            return {'message': 'Failed to retrieve video audio URL', 'status': response.status_code}, 500
        
        audio_url = response_data['audioUrl']
        logging.debug(f"Retrieved audio URL: {audio_url}")

        # Step 2: Upload audio to AssemblyAI
        assembly_audio_url = upload_audio_to_assemblyai(audio_url)

        # Step 3: Transcribe the audio using AssemblyAI
        transcript_id = start_transcription(assembly_audio_url)
        transcript_text = wait_for_transcription(transcript_id)

        return {'transcript': transcript_text, 'status': 200}, 200

    except Exception as e:
        logging.error(f"Error during transcription: {e}")
        return {'message': str(e), 'status': 500}, 500

def upload_audio_to_assemblyai(audio_url):
    headers = {
        'authorization': ASSEMBLYAI_API_KEY,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.youtube.com/',
        'Origin': 'https://www.youtube.com'
    }
    logging.debug(f"Downloading audio from URL: {audio_url}")
    
    # Step 1: Download the audio file locally with .m4a extension
    temp_audio_file = "/tmp/temp_audio.m4a"
    try:
        response = requests.get(audio_url, stream=True, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            raise Exception(f"Failed to download audio from URL: {response.status_code} - {response.text}")
        
        with open(temp_audio_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logging.debug(f"Audio file downloaded and saved locally at {temp_audio_file}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading audio: {str(e)}")
        raise Exception(f"Failed to download audio: {str(e)}")

    # Step 2: Convert the audio to MP3 format using ffmpeg
    mp3_audio_file = "/tmp/temp_audio.mp3"
    try:
        subprocess.run([
            'ffmpeg', '-y',  # Force overwrite output file
            '-i', temp_audio_file,
            '-vn',  # No video
            '-acodec', 'libmp3lame',  # Use MP3 codec
            '-q:a', '2',  # High quality
            mp3_audio_file
        ], check=True, capture_output=True)
        logging.debug(f"Audio converted to MP3 format at {mp3_audio_file}")
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg conversion failed: {e.stderr.decode()}")
        raise Exception("Failed to convert audio to MP3 format")

    # Step 3: Upload the converted MP3 file to AssemblyAI
    logging.debug("Uploading audio to AssemblyAI...")
    try:
        with open(mp3_audio_file, "rb") as f:
            files = {'file': (mp3_audio_file, f, 'audio/mp3')}
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
    
    # Clean up temporary files
    try:
        os.remove(temp_audio_file)
        os.remove(mp3_audio_file)
    except Exception as e:
        logging.warning(f"Failed to clean up temporary files: {e}")
    
    logging.debug(f"Audio uploaded successfully. AssemblyAI upload URL: {upload_response.json().get('upload_url')}")
    return upload_response.json()['upload_url']

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