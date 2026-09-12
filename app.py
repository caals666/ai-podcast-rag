from flask import Flask, request, render_template
import yt_dlp, re, os, io
import whisper, json, mariadb
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Base directory = wherever this script lives, so paths work on any machine
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")  # put cookies.txt next to app.py

YOUTUBE_PATTERN = re.compile(
    r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
)

MAX_DURATION_SECONDS = 5 * 60  # 5 minutes, matches the UI label

def groq_keys(text):

    client = Groq(
        api_key=os.getenv("GROQ_API_KEY"),
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f"""Extract 5 distinct, descriptive phrases (3-6 words) representing the key chronological sections of this transcript.
                            Return ONLY a Python list of strings, no explanation, no markdown, no code fences.

                            Example: ["phrase one here", "phrase two here", "phrase three here", "phrase four here", "phrase five here"]

                            Transcript:
                            {text}
                            """,
            }
        ],
        model="openai/gpt-oss-20b",
    )

    return ast.literal_eval(chat_completion.choices[0].message.content.strip())

def insert_db(video_id, whisper_result):
    # 1. Connect
    conn = mariadb.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
    cursor = conn.cursor()

    # 2. Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            video_id VARCHAR(20) NOT NULL,
            segment_text TEXT NOT NULL,
            start_time DECIMAL(10,3) NOT NULL,
            end_time DECIMAL(10,3) NOT NULL,
            timestamped_url VARCHAR(255) NOT NULL,
            embeddings JSON NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_video_id (video_id)
        )
    """)
    conn.commit()

    # 3. Insert one row (put your actual values here)
    insert_sql = """
        INSERT INTO video_data 
        (video_id, segment_text, start_time, end_time, timestamped_url, embeddings)
        VALUES (?, ?, ?, ?, ?, ?)
    """

    rows_to_insert = []
    for segment in whisper_result['segments']:
        start = segment['start']
        end = segment['end']
        text = segment['text'].strip()
        timestamped_url=f"https://youtube.com/watch?v={video_id}&t={int(start)}s"

        rows_to_insert.append((video_id,text,start,end,timestamped_url,None))

    if rows_to_insert:
        cursor.executemany(insert_sql,rows_to_insert)
        conn.commit()
        print(f"✅ Successfully inserted {len(rows_to_insert)} segments into the database.")

    # 4. Close
    cursor.close()
    conn.close()

def extract_video_id(url):
    # This regex looks for the 11-character ID in common YouTube patterns
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def validate_youtube_url(url: str) -> tuple[bool, str | None]:
    """
    Returns (is_valid, video_id).
    Strips whitespace and quotes from input.
    """
    if not url:
        return False, None

    cleaned = url.strip().strip('"').strip("'")
    print(cleaned)
    match = YOUTUBE_PATTERN.search(cleaned)
    if match:
        return True, match.group(1)
    return False, None


def yt_dlp_download(yt_link: str) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '0',
        }],
        'restrictfilenames': True,
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls']  # avoids the n-challenge
            }
        }
    }

    # Only attach a cookiefile if one actually exists, otherwise yt-dlp
    # raises FileNotFoundError before it even tries the download.
    if os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE
        print(f"[cookies] Using cookiefile: {COOKIES_FILE}")
    else:
        print(f"[cookies] WARNING: no cookies.txt found at {COOKIES_FILE} — downloading without cookies")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Pull metadata first so we can enforce the length limit
        # and fail fast on private/unavailable videos.
        info = ydl.extract_info(yt_link, download=False)
        duration = info.get('duration') or 0
        if duration > MAX_DURATION_SECONDS:
            raise ValueError(
                f"Video is {duration // 60}m{duration % 60}s long — please use a video "
                f"5 minutes or under."
            )

        info = ydl.extract_info(yt_link, download=True)
        f_name = ydl.prepare_filename(info)
        return os.path.splitext(f_name)[0] + '.mp3',info['id']

def transcribe_audio(file_path, language="en"):
    model=whisper.load_model("base")
    try:
        result = model.transcribe(file_path, language=language)
        return result

    except Exception as e:
        raise Exception(f"Transcription failed: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api', methods=['POST'])
def api():
    yt_link = request.form.get('ytlink')

    video_id=''

    try:
        f_name,video_id = yt_dlp_download(yt_link)
    except ValueError as e:
        # Our own validation errors (e.g. too long)
        return _result_page("❌ Can't download that one", str(e)), 400
    except yt_dlp.utils.DownloadError as e:
        print("yt-dlp error:", e)
        return _result_page(
            "❌ Download failed",
            "yt-dlp couldn't fetch that video. It may be private, age-restricted, "
            "region-locked, or your cookies.txt may have expired.",
        ), 502
    except Exception as e:
        print("Unexpected error:", e)
        return _result_page("❌ Something went wrong", "Unexpected server error. Check the logs."), 500
    
    print("Download finished:", f_name)

    transcription = transcribe_audio(f_name)
    with open(os.path.join(BASE_DIR,"transcript/transcript.txt"), "w", encoding="utf-8") as f:
        f.write(str(transcription))

    insert_db(video_id,transcription)

    keywords=groq_keys(transcription['text'])

    display_keyword=''
    for i in keywords:
        display_keyword+=i+'\n';

    return _result_page(
        "✅ Transcription complete",
        f"{display_keyword}",
    )

def _result_page(title: str, message: str) -> str:
    return f'''
        <h1>{title}</h1>
        <p>{message}</p>
        <a href="/">Go back</a>
    '''

if __name__ == '__main__':
    app.run(debug=True)