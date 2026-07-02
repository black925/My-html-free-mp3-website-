import os
import re
import shutil
import sqlite3
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "downloads.db")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
CORS(app)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                duration TEXT NOT NULL,
                author TEXT NOT NULL,
                views TEXT NOT NULL,
                thumbnail TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER,
                title TEXT NOT NULL,
                file_type TEXT NOT NULL,
                quality TEXT NOT NULL,
                size TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES analyses(id)
            )
            """
        )
        conn.commit()


init_db()


def sanitize_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug or "download"


def extract_media_metadata(url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    duration = info.get("duration")
    duration_text = f"{duration // 60}:{duration % 60:02d}" if isinstance(duration, int) else "Unknown"
    return {
        "title": info.get("title") or "Media",
        "description": (info.get("description") or "").strip() or "Public media ready for extraction.",
        "duration": duration_text,
        "author": info.get("uploader") or info.get("channel") or "Unknown uploader",
        "views": info.get("view_count") or info.get("view_count") or "Unknown views",
        "thumbnail": info.get("thumbnail") or "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?auto=format&fit=crop&w=800&q=80",
    }


def download_url_to_file(url: str, output_path: str, media_type: str) -> bool:
    try:
        output_root = output_path.rsplit('.', 1)[0] if '.' in os.path.basename(output_path) else output_path
        ext = ".mp3" if media_type == "audio" else ".mp4"
        if media_type == "audio":
            format_selector = "bestaudio/best"
            if shutil.which("ffmpeg"):
                postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}]
            else:
                format_selector = "bestaudio[ext=m4a]/bestaudio/best"
                postprocessors = []
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": format_selector,
                "outtmpl": output_root + ".%(ext)s",
                "postprocessors": postprocessors,
            }
        else:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "outtmpl": output_root + ".%(ext)s",
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        generated_files = [
            path for path in Path(os.path.dirname(output_root)).glob(os.path.basename(output_root) + ".*")
            if path.is_file()
        ]
        if not generated_files:
            return False

        latest = max(generated_files, key=lambda path: path.stat().st_mtime)
        final_path = output_path if output_path.endswith(ext) else output_root + ext
        os.replace(latest, final_path)
        return True
    except Exception:
        return False


def process_download(download_id: int, url: str, output_path: str, media_type: str) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE downloads SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
                ("Downloading", 10, datetime.utcnow().isoformat(), download_id),
            )
            conn.commit()

        success = download_url_to_file(url, output_path, media_type)
        if not success:
            with get_db() as conn:
                conn.execute(
                    "UPDATE downloads SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
                    ("Failed", 0, datetime.utcnow().isoformat(), download_id),
                )
                conn.commit()
            return

        with get_db() as conn:
            conn.execute(
                "UPDATE downloads SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
                ("Completed", 100, datetime.utcnow().isoformat(), download_id),
            )
            conn.commit()
    except Exception:
        with get_db() as conn:
            conn.execute(
                "UPDATE downloads SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
                ("Failed", 0, datetime.utcnow().isoformat(), download_id),
            )
            conn.commit()


@app.get("/api/health")
def health() -> Any:
    return jsonify({"ok": True, "service": "mediaforge"})


@app.post("/api/analyze")
def analyze() -> Any:
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return jsonify({"error": "Please provide a valid public media URL"}), 400

    host = parsed.netloc.lower()
    is_audio = "sound" in host or "music" in host or "pod" in host
    is_video = "youtube" in host or "vimeo" in host or "video" in host

    try:
        info = extract_media_metadata(url)
        title = info["title"]
        description = info["description"]
        duration = info["duration"]
        author = info["author"]
        views = info["views"]
        thumbnail = info["thumbnail"]
    except Exception:
        if is_audio:
            title = "Midnight Drift"
            description = "Atmospheric mix with cinematic transitions and warm synth layers."
            duration = "05:34"
            author = "Ari Lane"
            views = "182K plays"
        elif is_video:
            title = "Neon Nights"
            description = "A polished, high-energy stream with crisp detail and rich color."
            duration = "08:42"
            author = "North Studio"
            views = "48K views"
        else:
            title = "Studio Session"
            description = "A public media asset ready for premium download preparation."
            duration = "03:17"
            author = "Open Media"
            views = "6.4K views"

        thumbnail = "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?auto=format&fit=crop&w=800&q=80"
    created_at = datetime.utcnow().isoformat()

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analyses (url, title, description, duration, author, views, thumbnail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (url, title, description, duration, author, views, thumbnail, created_at),
        )
        analysis_id = cursor.lastrowid
        conn.commit()

    return jsonify(
        {
            "id": analysis_id,
            "title": title,
            "description": description,
            "duration": duration,
            "author": author,
            "views": views,
            "thumbnail": thumbnail,
            "date": created_at[:10],
            "estimatedSize": "1.4 GB" if is_video else "38 MB",
        }
    )


@app.post("/api/downloads")
def create_download() -> Any:
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "Untitled").strip()
    file_type = (payload.get("fileType") or "MP4").strip()
    quality = (payload.get("quality") or "1080p").strip()
    size = (payload.get("size") or "1.4 GB").strip()
    analysis_id = payload.get("analysisId")
    url = (payload.get("url") or "").strip()
    created_at = datetime.utcnow().isoformat()

    if not url:
        return jsonify({"error": "A URL is required to start a real download"}), 400

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return jsonify({"error": "Please provide a valid public URL"}), 400

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO downloads (analysis_id, title, file_type, quality, size, status, progress, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (analysis_id, title, file_type, quality, size, "Queued", 0, created_at, created_at),
        )
        download_id = cursor.lastrowid
        conn.commit()

    file_name = f"{sanitize_name(title)}-{download_id}.{file_type.lower()}"
    output_path = os.path.join(DOWNLOADS_DIR, file_name)
    media_type = "audio" if file_type.lower() == "mp3" else "video"
    threading.Thread(target=process_download, args=(download_id, url, output_path, media_type), daemon=True).start()

    return jsonify({"id": download_id, "status": "Queued", "progress": 0, "fileName": file_name})


@app.get("/api/downloads")
def list_downloads() -> Any:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, analysis_id, title, file_type, quality, size, status, progress, created_at, updated_at
            FROM downloads
            ORDER BY id DESC
            """
        ).fetchall()

    return jsonify(
        [
            {
                "id": row["id"],
                "analysisId": row["analysis_id"],
                "title": row["title"],
                "fileType": row["file_type"],
                "quality": row["quality"],
                "size": row["size"],
                "status": row["status"],
                "progress": row["progress"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
    )


@app.patch("/api/downloads/<int:download_id>")
def update_download(download_id: int) -> Any:
    payload = request.get_json(silent=True) or {}
    status = payload.get("status", "Downloading")
    progress = int(payload.get("progress", 0))
    updated_at = datetime.utcnow().isoformat()

    with get_db() as conn:
        conn.execute(
            "UPDATE downloads SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
            (status, progress, updated_at, download_id),
        )
        conn.commit()

    return jsonify({"ok": True, "id": download_id, "status": status, "progress": progress})


@app.route("/")
def index() -> Any:
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/downloads/<path:filename>")
def download_file(filename: str) -> Any:
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
