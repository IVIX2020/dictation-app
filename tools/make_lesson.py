import sys
import os
import subprocess
import json
from datetime import datetime

# 引数
URL = sys.argv[1]
LANG = sys.argv[2] if len(sys.argv) > 2 else "en"

LESSON_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = f"lessons/{LESSON_ID}"

os.makedirs(OUT_DIR, exist_ok=True)

audio_path = f"{OUT_DIR}/audio.mp3"

print(f"🎬 downloading audio... ({LANG})")

# ① yt-dlp
subprocess.run([
    "yt-dlp",
    "--extractor-args",
    "youtube:player_client=android",
    "-x",
    "--audio-format",
    "mp3",
    "-o",
    audio_path,
    URL
], check=True)

print("🧠 transcribing...")

# ② whisper（言語指定追加）
subprocess.run([
    "whisper",
    audio_path,
    "--model",
    "base",
    "--language",
    LANG,
    "--output_format",
    "json",
    "--output_dir",
    OUT_DIR
], check=True)

# ③ transcriptファイル取得
json_file = None
for f in os.listdir(OUT_DIR):
    if f.endswith(".json"):
        json_file = os.path.join(OUT_DIR, f)

with open(json_file, "r") as f:
    transcript = json.load(f)

# ④ metadata
metadata = {
    "id": LESSON_ID,
    "source": URL,
    "language": LANG,
    "audio": "audio.mp3",
}

with open(f"{OUT_DIR}/metadata.json", "w") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)

print("✅ lesson created:", OUT_DIR)