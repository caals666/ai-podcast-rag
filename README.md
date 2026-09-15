# YouTube Video Keyword Timestamper

A Flask app that takes a YouTube video link, transcribes it, and generates a clickable list of chapter-style navigation links — each jumping to the moment in the video where that topic is actually discussed.

## How it works

1. You paste a YouTube link into the web form.
2. The app downloads the audio with `yt-dlp` (capped at 5 minutes to keep processing fast).
3. [OpenAI Whisper](https://github.com/openai/whisper) transcribes the audio locally, producing a full transcript with per-segment timestamps.
4. The transcript is sent to a Groq-hosted LLM, which extracts 5 distinct, chronologically-ordered phrases representing the substantive content of the video (skipping intros, sponsor reads, outros, and filler).
5. Each phrase is semantically matched back against the transcript segments using [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`), to find the timestamp where that topic actually starts.
6. Results are cached in memory per video ID, so re-processing the same video is instant on subsequent requests.
7. You get a numbered list of clickable links, each opening the video at the exact timestamp for that topic.

## Tech stack

| Layer              | Technology                                  |
| ------------------ | -------------------------------------------- |
| Web framework       | Flask                                        |
| Video/audio fetch   | yt-dlp                                       |
| Transcription       | OpenAI Whisper (local, `base` model)         |
| Keyword extraction  | Groq API (`openai/gpt-oss-20b`)              |
| Semantic matching   | sentence-transformers (`all-MiniLM-L6-v2`)   |
| Caching             | Flask-Caching (in-memory `SimpleCache`)      |

## Prerequisites

- Python 3.10+
- **ffmpeg** installed and available on your system PATH (required by both `yt-dlp`'s audio extraction and Whisper)
  - Windows: `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin` folder to PATH
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` (Debian/Ubuntu) or your distro's equivalent
  - Verify with `ffmpeg -version` in a terminal
- A [Groq API key](https://console.groq.com/)
- A MariaDB/MySQL server (if you plan to use the DB persistence layer)
- A `cookies.txt` file — **required** for most videos, since YouTube blocks unauthenticated bot-like requests:
  1. Install the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension
  2. Go to youtube.com while logged in
  3. Click the extension icon and export cookies for the current site
  4. Save the exported file as `cookies.txt` in the project root, next to `app.py`

## Setup

Clone the repo and install dependencies:

```bash
git clone <your-repo-url>
cd <your-repo-folder>
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```dotenv
GROQ_API_KEY=your_groq_api_key_here
DB_USER=root
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=your_db_name
```

`GROQ_API_KEY` is required for keyword extraction to work at all. The `DB_*` variables are only used if/when the commented-out MariaDB persistence layer is enabled — leave them as placeholders otherwise, but the app currently runs fine without a real database connection since that code path isn't active.

Place your exported `cookies.txt` next to `app.py` (see Prerequisites above for how to generate it) — without it, most video downloads will fail or be rate-limited by YouTube.

Make sure the following folders exist (the app expects them):

```
downloads/
transcript/
```

## Running the app

```bash
python app.py
```

Then open:

```
http://127.0.0.1:5000
```

Paste a YouTube link (5 minutes or under) and submit — the app will download, transcribe, extract keywords, and return a list of timestamped links.

## Project structure

```
.
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── templates/
│   └── index.html          # Upload form
├── downloads/              # Downloaded audio files (created at runtime)
├── transcript/
│   └── transcript.txt      # Latest Whisper transcript (JSON, overwritten each run)
├── cookies.txt             # Required — exported YouTube session cookies (see Prerequisites)
└── .env                    # Environment variables (not committed)
```

## Notes & limitations

- Videos longer than 5 minutes are rejected before download to keep processing time reasonable.
- The in-memory cache (`SimpleCache`) resets on server restart and does not share state across multiple worker processes — fine for local/single-process use, but not suitable for a multi-worker production deployment as-is.
- `transcript.txt` is overwritten on every new video processed; it holds only the most recent transcript at any given time.
- A MariaDB persistence layer is scaffolded in the code (commented out) for storing per-segment transcript data, but is not currently wired in.

## Roadmap / possible next steps

- Move caching to a persistent store (SQLite, or Redis for multi-process deployments)
- Wire up the MariaDB storage layer for full transcript history
- Support videos longer than 5 minutes via chunked processing
- Add error handling/UI feedback for malformed LLM keyword responses