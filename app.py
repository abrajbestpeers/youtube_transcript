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
        # Step 1: Download audio from YouTube using yt-dlp
        logging.debug(f"Downloading audio from YouTube URL: {video_url}")
        temp_audio_file = "/tmp/temp_audio.mp3"
        try:
            # Remove file if it exists
            if os.path.exists(temp_audio_file):
                os.remove(temp_audio_file)
            result = subprocess.run([
                'yt-dlp',
                '-f', 'bestaudio',
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0',
                '-o', temp_audio_file,
                video_url
            ], capture_output=True, text=True)
            if result.returncode != 0:
                logging.error(f"yt-dlp failed: {result.stderr}")
                return {'message': f'yt-dlp failed: {result.stderr}', 'status': 400}, 400
            if not os.path.exists(temp_audio_file):
                logging.error("yt-dlp did not produce an audio file.")
                return {'message': 'yt-dlp did not produce an audio file.', 'status': 400}, 400
            logging.debug(f"Audio downloaded successfully to {temp_audio_file}")
        except Exception as e:
            logging.error(f"Error downloading audio with yt-dlp: {str(e)}")
            return {'message': f'Error downloading audio: {str(e)}', 'status': 500}, 500

        mp3_audio_file = temp_audio_file  # Already mp3

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

        # Step 4: Start transcription
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