import sys
import os
import subprocess
import json
from datetime import datetime

def update_lessons_json():
    lessons = []
    lessons_dir = "lessons"
    if not os.path.exists(lessons_dir):
        return

    for dirname in sorted(os.listdir(lessons_dir), reverse=True):
        dirpath = os.path.join(lessons_dir, dirname)
        if not os.path.isdir(dirpath):
            continue

        metadata_path = os.path.join(dirpath, "metadata.json")
        audio_mp3_path = os.path.join(dirpath, "audio.mp3")

        if os.path.exists(metadata_path) and os.path.exists(audio_mp3_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                try:
                    dt = datetime.strptime(dirname, "%Y%m%d_%H%M%S")
                    created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    created_at = datetime.fromtimestamp(os.path.getctime(metadata_path)).strftime("%Y-%m-%d %H:%M:%S")

                lesson_info = {
                    "id": meta.get("id", dirname),
                    "title": meta.get("title", f"Lesson {dirname}"),
                    "createdAt": created_at,
                    "language": meta.get("language", "en"),
                    "source": meta.get("source", ""),
                    "audio": f"/lessons/{dirname}/audio.mp3" # フロントエンドでfetchするためのパス
                }
                lessons.append(lesson_info)
            except Exception as e:
                print(f"⚠️ Error reading lesson {dirname}: {e}")

    with open(os.path.join(lessons_dir, "lessons.json"), "w", encoding="utf-8") as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)
    print("📋 lessons.json updated with", len(lessons), "lessons")

# 引数
if len(sys.argv) < 2:
    print("Usage:")
    print("  Create new lesson: python tools/make_lesson.py <YOUTUBE_URL> [LANG]")
    print("  Rebuild index:     python tools/make_lesson.py --rebuild")
    sys.exit(1)

if sys.argv[1] == "--rebuild":
    update_lessons_json()
    sys.exit(0)

URL = sys.argv[1]
LANG = sys.argv[2] if len(sys.argv) > 2 else "en"

LESSON_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = f"lessons/{LESSON_ID}"

os.makedirs(OUT_DIR, exist_ok=True)

audio_path = f"{OUT_DIR}/audio.mp3"

print("🎬 fetching video title...")
video_title = f"Lesson {LESSON_ID}"
try:
    title_proc = subprocess.run([
        "yt-dlp",
        "--get-title",
        URL
    ], capture_output=True, text=True, check=True)
    video_title = title_proc.stdout.strip()
    print(f"📌 title: {video_title}")
except Exception as e:
    print(f"⚠️ warning: failed to fetch video title: {e}")

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

print("🧠 transcribing with word-level timestamps...")

# ② whisper（言語指定追加 + ワードタイムスタンプ有効化）
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
    OUT_DIR,
    "--word_timestamps",
    "True"
], check=True)

# ③ transcriptファイル取得
json_file = None
for f in os.listdir(OUT_DIR):
    if f.endswith(".json") and f != "metadata.json":
        json_file = os.path.join(OUT_DIR, f)

# もしWhisperが作成したjsonがaudio.jsonでない場合、audio.jsonにリネームする
if json_file and os.path.basename(json_file) != "audio.json":
    target_json_file = os.path.join(OUT_DIR, "audio.json")
    os.rename(json_file, target_json_file)
    json_file = target_json_file

# ④ metadata
metadata = {
    "id": LESSON_ID,
    "title": video_title,
    "source": URL,
    "language": LANG,
    "audio": "audio.mp3",
}

with open(f"{OUT_DIR}/metadata.json", "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)

print("✅ lesson created:", OUT_DIR)

# 最後にlessons.jsonを生成・更新する
update_lessons_json()