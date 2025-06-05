# YouTube Audio Downloader API

A Flask-based API service that downloads audio from YouTube videos and converts them to MP3 format.

## Features

- Download audio from YouTube videos
- Convert to MP3 format
- RESTful API endpoint
- Production-ready with Gunicorn
- Proper error handling and logging

## Local Development

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the development server:
```bash
python3 app.py
```

The server will start at `http://localhost:8080`

## API Usage

### Download YouTube Audio

```bash
curl -X POST http://localhost:8080/youtube-import \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID"}'
```

Response:
```json
{
  "message": "Download successful",
  "audio_file": "video_title.mp3",
  "file_path": "downloads/video_title.mp3",
  "status": 200
}
```

## Deployment to Render

1. Create a new Web Service on Render
2. Connect your repository
3. Configure the service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Environment Variables:
     - `ENVIRONMENT`: `production`
     - `PORT`: `8080`
     - `DOWNLOAD_FOLDER`: `downloads` (optional)

## Environment Variables

- `ENVIRONMENT`: Set to `production` for production deployment
- `PORT`: Port number for the server (default: 8080)
- `DOWNLOAD_FOLDER`: Directory to store downloaded files (default: 'downloads')

## Requirements

- Python 3.8+
- FFmpeg (for audio conversion)
- Dependencies listed in requirements.txt

## License

MIT 