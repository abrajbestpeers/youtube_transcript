import os
import logging
import subprocess
import shutil
import time
import requests
import tempfile
from flask import Flask, jsonify, request
from youtube_transcript_api import YouTubeTranscriptApi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables for API keys
openai_api_key = os.getenv("OPENAI_API_KEY")
assemblyai_api_key = os.getenv('ASSEMBLYAI_API_KEY')

ASSEMBLYAI_UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
ASSEMBLYAI_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"

# === Helper: CORS Preflight Response ===
def _cors_response():
    return ('', 204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '3600'
    })

# === Hello World Route ===
@app.route('/', methods=['GET'])
def hello():
    return jsonify({"message": "Hello World from youtube-transcript-service"}), 200

# === YouTube Audio Download and Transcription Class ===
class YouTubeTranscriber:
    def __init__(self, video_id, api_key=assemblyai_api_key):
        self.video_id = video_id
        self.api_key = api_key
        self.temp_dir = tempfile.mkdtemp(prefix='youtube_transcription_')
        self.audio_path = None
        logger.info(f"Initialized YouTubeTranscriber for video_id: {video_id}")

    def transcribe(self):
        try:
            logger.info(f"Starting transcription process for video_id: {self.video_id}")
            self.audio_path = self.download_audio(self.video_id)
            logger.info(f"Audio downloaded successfully to: {self.audio_path}")
            
            audio_url = self.upload_audio(self.audio_path)
            logger.info(f"Audio uploaded successfully, URL: {audio_url}")
            
            transcript_id = self.start_transcription(audio_url)
            logger.info(f"Transcription started, ID: {transcript_id}")
            
            transcript_text = self.wait_for_transcription(transcript_id)
            logger.info(f"Transcription completed successfully, length: {len(transcript_text)}")
            
            return transcript_text
        except Exception as e:
            logger.error(f"Error during transcription: {str(e)}")
            raise
        finally:
            if self.audio_path:
                self.cleanup(self.audio_path)

    def download_audio(self, video_id):
        logger.info(f"Starting audio download for video_id: {video_id}")
        self.check_ytdlp_installation()
        temp_audio_file = os.path.join(self.temp_dir, f"youtube_{video_id}.mp3")

        # Download audio using yt-dlp subprocess
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--no-check-certificate",
            "--prefer-insecure",
            "--no-warnings",
            "--ignore-errors",
            "--format", "bestaudio/best",
            "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "-o", temp_audio_file,
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        
        logger.debug(f"Running download command: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            error_msg = f"YouTube download failed: {result.stderr.decode('utf-8')}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        if not os.path.exists(temp_audio_file) or os.path.getsize(temp_audio_file) == 0:
            error_msg = "Audio file not created"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.info(f"Audio download completed: {temp_audio_file}")
        return temp_audio_file

    def upload_audio(self, audio_path):
        logger.info(f"Starting audio upload: {audio_path}")
        with open(audio_path, 'rb') as audio_file:
            file_content = audio_file.read()
            logger.debug(f"Uploading audio file to AssemblyAI..., size: {len(file_content)} bytes")
            
            response = requests.post(
                ASSEMBLYAI_UPLOAD_URL,
                headers={
                    "authorization": self.api_key,
                    "content-type": "application/octet-stream"
                },
                data=file_content
            )
        result = self.handle_response(response, "Upload")
        logger.info(f"Audio upload completed, URL: {result['upload_url']}")
        return result["upload_url"]

    def start_transcription(self, audio_url):
        logger.info(f"Starting transcription for audio URL: {audio_url}")
        response = requests.post(
            ASSEMBLYAI_TRANSCRIPT_URL,
            headers={
                "authorization": self.api_key,
                "content-type": "application/json"
            },
            json={"audio_url": audio_url, "speech_model": "universal"}
        )
        result = self.handle_response(response, "Transcription start")
        logger.info(f"Transcription started, ID: {result['id']}")
        return result["id"]

    def wait_for_transcription(self, transcript_id, max_retries=10, interval=5):
        logger.info(f"Waiting for transcription completion, ID: {transcript_id}")
        retries = 0
        
        while True:
            try:
                response = requests.get(
                    f"{ASSEMBLYAI_TRANSCRIPT_URL}/{transcript_id}",
                    headers={"authorization": self.api_key}
                )
                result = self.handle_response(response, "Transcription status check")
                
                logger.debug(f"Transcription status: {result['status']}")
                
                if result["status"] == "completed":
                    logger.info("Transcription completed successfully")
                    return result["text"]
                elif result["status"] == "error":
                    error_msg = f"Transcription error: {result['error']}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                else:
                    logger.info(f"Transcription in progress, retry {retries + 1}/{max_retries}")
                    retries += 1
                    if retries >= max_retries:
                        raise Exception(f"Transcription polling failed after {max_retries} attempts")
                    time.sleep(interval)
            except Exception as e:
                retries += 1
                if retries >= max_retries:
                    raise Exception(f"Transcription polling failed after {max_retries} attempts: {str(e)}")
                time.sleep(interval)

    def check_ytdlp_installation(self):
        logger.debug("Checking yt-dlp installation")
        if shutil.which("yt-dlp") is None:
            logger.info("yt-dlp not found, attempting to install...")
            if shutil.which("pip3"):
                subprocess.run(["pip3", "install", "yt-dlp"], check=True)
            elif shutil.which("pip"):
                subprocess.run(["pip", "install", "yt-dlp"], check=True)
            else:
                raise Exception("yt-dlp not found and no pip installer available")
            
            if shutil.which("yt-dlp") is None:
                raise Exception("Failed to install yt-dlp")
        logger.debug("yt-dlp is installed")

    def handle_response(self, response, context):
        if not response.ok:
            error_msg = f"{context} failed: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        return response.json()

    def cleanup(self, audio_path):
        logger.info(f"Starting cleanup for: {audio_path}")
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logger.debug(f"Removed audio file: {audio_path}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.debug(f"Removed temp directory: {self.temp_dir}")
            logger.info("Cleanup completed")
        except Exception as e:
            logger.warning(f"Warning: Failed to clean up audio file: {str(e)}")

# === Fetch Transcript Function ===
@app.route('/fetch-transcript', methods=['POST', 'OPTIONS'])
def fetch_transcript():
    if request.method == 'OPTIONS':
        return _cors_response()

    headers = {'Access-Control-Allow-Origin': '*'}
    request_json = request.get_json(silent=True)
    video_id = request_json.get('video_id') if request_json else None

    if not video_id:
        return jsonify({"error": "Missing video_id parameter"}), 400, headers

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcripts = []
        for transcript in transcript_list:
            transcripts.append({
                "language": transcript.language,
                "language_code": transcript.language_code,
                "is_generated": transcript.is_generated,
                "is_translatable": transcript.is_translatable
            })
        return jsonify({"transcripts": transcripts}), 200, headers
    except Exception as e:
        return jsonify({"error": f"Failed to fetch transcripts: {str(e)}"}), 500, headers

# === YouTube Transcribe Function ===
@app.route('/youtube-transcribe', methods=['POST', 'OPTIONS'])
def youtube_transcribe():
    if request.method == 'OPTIONS':
        return _cors_response()

    headers = {'Access-Control-Allow-Origin': '*'}
    request_json = request.get_json(silent=True)
    video_id = request_json.get('video_id') if request_json else None

    if not video_id:
        return jsonify({"error": "Missing video_id parameter"}), 400, headers

    try:
        transcriber = YouTubeTranscriber(video_id)
        transcript = transcriber.transcribe()
        return jsonify({"transcript": transcript}), 200, headers
    except Exception as e:
        return jsonify({"error": f"Failed to transcribe video: {str(e)}"}), 500, headers

# === Summarize Transcript Function ===
@app.route('/summarize-transcript', methods=['POST', 'OPTIONS'])
def summarize_transcript():
    if request.method == 'OPTIONS':
        return _cors_response()

    headers = {'Access-Control-Allow-Origin': '*'}
    request_json = request.get_json(silent=True)
    
    transcript = request_json.get('transcript') if request_json else None
    prompt = request_json.get('prompt', 'Summarize the following transcript:')

    if not transcript:
        return jsonify({"error": "Missing transcript parameter"}), 400, headers

    try:
        import openai
        openai.api_key = openai_api_key
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                { "role": "system", "content": "You are a helpful assistant that summarizes transcripts." },
                { "role": "user", "content": f"{prompt}\n\n{transcript}" }
            ],
            temperature=0.5
        )

        summary = response['choices'][0]['message']['content'].strip()
        return jsonify({ "summary": summary }), 200, headers

    except Exception as e:
        return jsonify({ "error": f"Failed to generate summary: {str(e)}" }), 500, headers

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
