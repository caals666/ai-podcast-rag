import os
from dotenv import load_dotenv

load_dotenv()

from groq import Groq

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

transcription=''
with open(os.path.join(BASE_DIR, "transcript/transcript.txt"), "r", encoding="utf-8") as f:
    transcription = f.read()

print(transcription)

prompt = f"Extract 5 distinct, descriptive phrases (1-2 words) representing the key chronological sections of this transcript. Numbered list:\n\n{transcription}"

chat_completion = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {
            "role": "user",
            "content": prompt,
        }
    ]
)

print(chat_completion.choices[0].message.content)