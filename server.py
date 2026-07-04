from __future__ import annotations

import json
import mimetypes
import os
import argparse
import traceback
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
DOWNLOAD_ROOT = APP_ROOT / "downloads"
HOST = "127.0.0.1"
PORT = int(os.environ.get("VIDEO_DOWNLOADER_PORT", "8787"))
LOCAL_BIN_DIR = APP_ROOT / ".venv" / ("Scripts" if sys.platform.startswith("win") else "bin")
LOCAL_SITE_PACKAGES = (
    APP_ROOT / ".venv" / "Lib" / "site-packages"
    if sys.platform.startswith("win")
    else APP_ROOT / ".venv" / "lib"
)


def resolve_executable(name: str) -> str | None:
    suffixes = (".exe", "") if sys.platform.startswith("win") else ("",)
    for suffix in suffixes:
        candidate = LOCAL_BIN_DIR / f"{name}{suffix}"
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def resolve_imageio_ffmpeg() -> str | None:
    if sys.platform.startswith("win"):
        binary_dir = LOCAL_SITE_PACKAGES / "imageio_ffmpeg" / "binaries"
        candidates = sorted(binary_dir.glob("ffmpeg*.exe"))
    else:
        candidates = sorted(LOCAL_SITE_PACKAGES.glob("python*/site-packages/imageio_ffmpeg/binaries/ffmpeg*"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_ffmpeg() -> str | None:
    suffixes = (".exe", "") if sys.platform.startswith("win") else ("",)
    for suffix in suffixes:
        candidate = LOCAL_BIN_DIR / f"ffmpeg{suffix}"
        if candidate.exists():
            return str(candidate)
    return resolve_imageio_ffmpeg() or shutil.which("ffmpeg")


def subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    if LOCAL_BIN_DIR.exists():
        env["PATH"] = f"{LOCAL_BIN_DIR}{os.pathsep}{env.get('PATH', '')}"
    return env


YTDLP_PATH = resolve_executable("yt-dlp")
FFMPEG_PATH = resolve_ffmpeg()
JOBS: dict[str, "DownloadJob"] = {}
JOBS_LOCK = threading.Lock()
COOKIE_BROWSERS = {"chrome", "edge", "firefox"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def console_log(message: str) -> None:
    if sys.stdout:
        print(message)


@dataclass
class DownloadJob:
    id: str
    url: str
    preset: str
    title: str = "视频"
    platform: str = "stream"
    status: str = "queued"
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    message: str = "等待开始"
    output_dir: str = ""
    files: list[str] = field(default_factory=list)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    cancel_requested: bool = False

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("process", None)
        payload.pop("cancel_requested", None)
        return payload

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            setattr(self, key, value)
        self.updated_at = time.time()


def command_version(path: str | None) -> str | None:
    if not path:
        return None
    version_flag = "-version" if Path(path).name.lower().startswith("ffmpeg") else "--version"
    try:
        completed = subprocess.run(
            [path, version_flag],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
            env=subprocess_env(),
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.splitlines()[0].strip()


def valid_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入完整的视频链接")
    return url


def detect_platform(url: str) -> dict[str, str]:
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return {"key": "youtube", "label": "YouTube"}
    if "bilibili.com" in host or host == "b23.tv" or host.endswith(".b23.tv"):
        return {"key": "bilibili", "label": "Bilibili"}
    if "douyin.com" in host:
        return {"key": "douyin", "label": "Douyin"}
    if "vimeo.com" in host:
        return {"key": "vimeo", "label": "Vimeo"}
    return {"key": "stream", "label": "自动识别"}


def safe_output_dir(raw_output_dir: str | None) -> Path:
    if not raw_output_dir:
        DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        return DOWNLOAD_ROOT

    candidate = Path(raw_output_dir).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate.resolve()


def duration_label(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def collect_video_heights(formats: list[dict[str, Any]]) -> list[int]:
    heights = set()
    for item in formats:
        height = item.get("height")
        vcodec = item.get("vcodec")
        if isinstance(height, int) and height > 0 and vcodec and vcodec != "none":
            heights.add(height)
    return sorted(heights, reverse=True)


def numeric_value(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def format_file_size(size_bytes: float | None, approximate: bool = False) -> str:
    if not size_bytes or size_bytes <= 0:
        return "大小未知"

    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        rendered = f"{int(value)} {units[unit_index]}"
    elif value >= 100:
        rendered = f"{value:.0f} {units[unit_index]}"
    elif value >= 10:
        rendered = f"{value:.1f} {units[unit_index]}"
    else:
        rendered = f"{value:.2f} {units[unit_index]}"
    return f"约 {rendered}" if approximate else rendered


def estimate_format_size(item: dict[str, Any], duration: Any) -> tuple[float | None, bool]:
    exact = numeric_value(item.get("filesize"))
    if exact:
        return exact, False

    approximate = numeric_value(item.get("filesize_approx"))
    if approximate:
        return approximate, True

    seconds = numeric_value(duration)
    bitrate = (
        numeric_value(item.get("tbr"))
        or numeric_value(item.get("vbr"))
        or numeric_value(item.get("abr"))
    )
    if seconds and bitrate:
        return seconds * bitrate * 1000 / 8, True
    return None, True


def format_score(item: dict[str, Any], duration: Any) -> tuple[float, float, float]:
    size, _ = estimate_format_size(item, duration)
    return (
        numeric_value(item.get("height")) or 0,
        numeric_value(item.get("tbr")) or numeric_value(item.get("vbr")) or numeric_value(item.get("abr")) or 0,
        size or 0,
    )


def best_matching_format(
    formats: list[dict[str, Any]],
    duration: Any,
    prefer_ext: set[str] | None = None,
) -> dict[str, Any] | None:
    if not formats:
        return None
    candidates = formats
    if prefer_ext:
        preferred = [item for item in formats if str(item.get("ext") or "").lower() in prefer_ext]
        if preferred:
            candidates = preferred
    return max(candidates, key=lambda item: format_score(item, duration))


def combined_size(
    items: list[dict[str, Any] | None],
    duration: Any,
) -> tuple[float | None, bool]:
    total = 0.0
    approximate = False
    for item in items:
        if not item:
            return None, True
        size, is_approximate = estimate_format_size(item, duration)
        if not size:
            return None, True
        total += size
        approximate = approximate or is_approximate
    return total, approximate


def estimate_video_size(
    formats: list[dict[str, Any]],
    duration: Any,
    max_height: int | None = None,
    prefer_mp4: bool = False,
) -> tuple[float | None, bool]:
    def within_height(item: dict[str, Any]) -> bool:
        height = item.get("height")
        if not isinstance(height, int) or height <= 0:
            return False
        return max_height is None or height <= max_height

    video_formats = [
        item
        for item in formats
        if within_height(item) and item.get("vcodec") and item.get("vcodec") != "none"
    ]
    video_only = [item for item in video_formats if item.get("acodec") in {None, "none"}]
    combined = [item for item in video_formats if item.get("acodec") and item.get("acodec") != "none"]
    audio_only = [
        item
        for item in formats
        if item.get("acodec") and item.get("acodec") != "none" and item.get("vcodec") in {None, "none"}
    ]

    video_ext = {"mp4"} if prefer_mp4 else None
    audio_ext = {"m4a", "mp4"} if prefer_mp4 else None
    adaptive_video = best_matching_format(video_only, duration, video_ext)
    adaptive_audio = best_matching_format(audio_only, duration, audio_ext)
    adaptive_size, adaptive_approximate = combined_size([adaptive_video, adaptive_audio], duration)
    if adaptive_size:
        return adaptive_size, adaptive_approximate

    combined_format = best_matching_format(combined, duration, video_ext)
    return estimate_format_size(combined_format, duration) if combined_format else (None, True)


def estimate_audio_size(formats: list[dict[str, Any]], duration: Any) -> tuple[float | None, bool]:
    audio_formats = [
        item
        for item in formats
        if item.get("acodec") and item.get("acodec") != "none" and item.get("vcodec") in {None, "none"}
    ]
    selected = best_matching_format(audio_formats, duration)
    return estimate_format_size(selected, duration) if selected else (None, True)


def build_presets(formats: list[dict[str, Any]], duration: Any = None) -> list[dict[str, Any]]:
    heights = collect_video_heights(formats)
    max_height = heights[0] if heights else None
    best_size, best_approximate = estimate_video_size(formats, duration)
    presets: list[dict[str, Any]] = [
        {
            "id": "best",
            "label": "最佳画质",
            "detail": "优先画质和音质，文件更大",
            "sizeLabel": format_file_size(best_size, best_approximate),
            "recommended": True,
            "kind": "video",
        }
    ]
    for height in (2160, 1440, 1080, 720, 480):
        if not max_height or max_height >= height:
            size, approximate = estimate_video_size(formats, duration, height, prefer_mp4=True)
            presets.append(
                {
                    "id": f"mp4_{height}",
                    "label": f"{height}p MP4",
                    "detail": "兼容性好，适合手机和电脑播放",
                    "sizeLabel": format_file_size(size, approximate),
                    "kind": "video",
                }
            )
    audio_size, audio_approximate = estimate_audio_size(formats, duration)
    presets.append(
        {
            "id": "audio_mp3",
            "label": "仅音频 MP3",
            "detail": "适合播客、课程和音乐内容",
            "sizeLabel": format_file_size(audio_size, True if audio_size else audio_approximate),
            "kind": "audio",
        }
    )
    return presets


def ytdlp_network_args(url: str) -> list[str]:
    platform = detect_platform(url)["key"]
    args = [
        "--user-agent",
        BROWSER_USER_AGENT,
        "--retries",
        "8",
        "--fragment-retries",
        "8",
        "--extractor-retries",
        "3",
        "--socket-timeout",
        "30",
    ]
    if platform == "bilibili":
        args.extend(
            [
                "--referer",
                "https://www.bilibili.com/",
                "--add-header",
                "Origin:https://www.bilibili.com",
            ]
        )
    return args


def cookie_args(use_cookies: bool, browser: str | None) -> list[str]:
    if not use_cookies:
        return []
    selected = (browser or "chrome").strip().lower()
    if selected not in COOKIE_BROWSERS:
        selected = "chrome"
    return ["--cookies-from-browser", selected]


def inspect_video(url: str, use_cookies: bool = False, cookie_browser: str | None = None) -> dict[str, Any]:
    if not YTDLP_PATH:
        raise RuntimeError("未找到 yt-dlp，请先安装或放入系统 PATH")

    command = [
        YTDLP_PATH,
        "--dump-single-json",
        "--no-warnings",
        "--ignore-config",
        "--no-playlist",
    ]
    command.extend(ytdlp_network_args(url))
    command.extend(cookie_args(use_cookies, cookie_browser))
    command.append(url)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=75,
        encoding="utf-8",
        errors="replace",
        env=subprocess_env(),
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "识别失败"
        raise RuntimeError(clean_error(message))

    data = json.loads(completed.stdout)
    formats = data.get("formats") or []
    heights = collect_video_heights(formats)
    platform = detect_platform(data.get("webpage_url") or url)
    return {
        "url": data.get("webpage_url") or url,
        "title": data.get("title") or "未命名视频",
        "uploader": data.get("uploader") or data.get("channel") or "",
        "thumbnail": data.get("thumbnail") or "",
        "duration": duration_label(data.get("duration")),
        "platform": platform,
        "heights": heights[:8],
        "presets": build_presets(formats, data.get("duration")),
        "extractor": data.get("extractor_key") or "",
    }


def preset_arguments(preset: str) -> list[str]:
    if preset == "audio_mp3":
        return [
            "-f",
            "bestaudio/best",
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
        ]

    match = re.fullmatch(r"mp4_(\d+)", preset)
    if match:
        height = match.group(1)
        selector = (
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"b[height<={height}][ext=mp4]/"
            f"bv*[height<={height}]+ba/"
            f"best[height<={height}]"
        )
        return ["-f", selector, "--merge-output-format", "mp4"]

    return ["-f", "bv*+ba/best", "--merge-output-format", "mp4"]


def build_download_command(
    url: str,
    preset: str,
    output_dir: Path,
    playlist: bool,
    subtitles: bool,
    use_cookies: bool,
    cookie_browser: str | None,
) -> list[str]:
    if not YTDLP_PATH:
        raise RuntimeError("未找到 yt-dlp，请先安装或放入系统 PATH")

    command = [
        YTDLP_PATH,
        "--newline",
        "--no-colors",
        "--ignore-config",
        "--windows-filenames",
        "-P",
        str(output_dir),
        "-o",
        "%(title).180B [%(id)s].%(ext)s",
        "--print",
        "after_move:VIDEODL_FILE:%(filepath)s",
    ]
    if FFMPEG_PATH:
        command.extend(["--ffmpeg-location", FFMPEG_PATH])
    command.extend(ytdlp_network_args(url))
    command.extend(cookie_args(use_cookies, cookie_browser))
    command.extend(["--yes-playlist" if playlist else "--no-playlist"])
    command.extend(preset_arguments(preset))
    if subtitles:
        command.extend(
            [
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                "zh-CN,zh-Hans,en.*",
                "--convert-subs",
                "srt",
            ]
        )
    command.append(url)
    return command


PROGRESS_PATTERN = re.compile(r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%")
SPEED_PATTERN = re.compile(r"\bat\s+(?P<speed>[^\s]+/s)")
ETA_PATTERN = re.compile(r"\bETA\s+(?P<eta>[0-9:]+)")


def clean_error(message: str) -> str:
    message = re.sub(r"\s+", " ", message).strip()
    message = message.replace("ERROR:", "").strip()
    if "403" in message or "Forbidden" in message:
        message = (
            f"{message}。平台拒绝了当前请求。请在页面勾选“使用浏览器登录状态”，"
            "确认所选浏览器已登录该平台后重试；如果仍失败，请更新 yt-dlp。"
        )
    return message[-800:] if len(message) > 800 else message


def apply_process_line(job: DownloadJob, line: str) -> None:
    line = line.strip()
    if not line:
        return

    if line.startswith("VIDEODL_FILE:"):
        path = line.removeprefix("VIDEODL_FILE:").strip()
        if path and path not in job.files:
            job.files.append(path)
        job.update(progress=100.0, message="下载完成")
        return

    progress_match = PROGRESS_PATTERN.search(line)
    if progress_match:
        percent = float(progress_match.group("percent"))
        speed_match = SPEED_PATTERN.search(line)
        eta_match = ETA_PATTERN.search(line)
        speed = speed_match.group("speed") if speed_match else job.speed
        eta = eta_match.group("eta") if eta_match else job.eta
        job.update(
            status="running",
            progress=max(job.progress, min(percent, 100.0)),
            speed=speed,
            eta=eta,
            message="正在下载",
        )
        return

    if line.startswith("[Merger]") or line.startswith("[ExtractAudio]"):
        job.update(message="正在整理文件")
        return

    if "Destination:" in line:
        job.update(message="已创建下载文件")
        return

    if "ERROR:" in line:
        job.update(status="error", error=clean_error(line), message="下载失败")
        return

    if line.startswith("[download] 100%"):
        job.update(progress=100.0, message="正在收尾")
        return

    if line.startswith("["):
        job.update(message=line[:120])


def run_download_job(job_id: str, command: list[str]) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.update(status="running", message="正在连接视频源")

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
            env=subprocess_env(),
        )
    except Exception as exc:
        with JOBS_LOCK:
            job.update(status="error", error=str(exc), message="启动下载失败")
        return

    with JOBS_LOCK:
        job.process = process

    assert process.stdout is not None
    for line in process.stdout:
        with JOBS_LOCK:
            apply_process_line(job, line)
            if job.cancel_requested and process.poll() is None:
                process.terminate()

    return_code = process.wait()
    with JOBS_LOCK:
        if job.cancel_requested:
            job.update(status="cancelled", message="已取消")
        elif return_code == 0:
            job.update(status="done", progress=100.0, message="下载完成")
        elif job.status != "error":
            job.update(
                status="error",
                error=f"下载进程退出，代码 {return_code}",
                message="下载失败",
            )
        job.process = None


def start_download(payload: dict[str, Any]) -> DownloadJob:
    url = valid_url(payload.get("url", ""))
    preset = payload.get("preset") or "best"
    output_dir = safe_output_dir(payload.get("outputDir"))
    playlist = bool(payload.get("playlist"))
    subtitles = bool(payload.get("subtitles"))
    use_cookies = bool(payload.get("useCookies"))
    cookie_browser = str(payload.get("cookieBrowser") or "chrome")
    title = str(payload.get("title") or "视频")
    platform = detect_platform(url)["label"]

    command = build_download_command(
        url,
        preset,
        output_dir,
        playlist,
        subtitles,
        use_cookies,
        cookie_browser,
    )
    job = DownloadJob(
        id=uuid.uuid4().hex,
        url=url,
        preset=preset,
        title=title,
        platform=platform,
        output_dir=str(output_dir),
    )
    with JOBS_LOCK:
        JOBS[job.id] = job
    thread = threading.Thread(target=run_download_job, args=(job.id, command), daemon=True)
    thread.start()
    return job


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


class AppHandler(BaseHTTPRequestHandler):
    server_version = "VideoDownloader/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        console_log("%s - %s" % (self.address_string(), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/health":
            return json_response(
                self,
                200,
                {
                    "ok": True,
                    "ytDlp": command_version(YTDLP_PATH),
                    "ffmpeg": command_version(FFMPEG_PATH),
                    "downloadDir": str(DOWNLOAD_ROOT),
                    "platforms": ["YouTube", "Bilibili", "Douyin", "Vimeo"],
                },
            )
        if path == "/api/jobs":
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)
                return json_response(self, 200, [job.public() for job in jobs])
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    return json_response(self, 404, {"error": "任务不存在"})
                return json_response(self, 200, job.public())
        return self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = read_json(self)
            if path == "/api/inspect":
                url = valid_url(payload.get("url", ""))
                use_cookies = bool(payload.get("useCookies"))
                cookie_browser = str(payload.get("cookieBrowser") or "chrome")
                return json_response(self, 200, inspect_video(url, use_cookies, cookie_browser))
            if path == "/api/download":
                job = start_download(payload)
                return json_response(self, 200, job.public())
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = path.split("/")[-2]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if not job:
                        return json_response(self, 404, {"error": "任务不存在"})
                    job.cancel_requested = True
                    if job.process and job.process.poll() is None:
                        job.process.terminate()
                    job.update(message="正在取消")
                    return json_response(self, 200, job.public())
            if path == "/api/open-downloads":
                DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
                open_folder(DOWNLOAD_ROOT)
                return json_response(self, 200, {"ok": True})
            return json_response(self, 404, {"error": "接口不存在"})
        except Exception as exc:
            return json_response(self, 400, {"error": clean_error(str(exc))})

    def serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"/", ""} else request_path.lstrip("/")
        target = (STATIC_ROOT / relative).resolve()
        if not str(target).startswith(str(STATIC_ROOT.resolve())) or not target.exists():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type = f"{content_type}; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def open_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local video downloader")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    url = f"http://{args.host}:{args.port}"
    console_log(f"Video Downloader running at {url}")
    console_log(f"Downloads: {DOWNLOAD_ROOT}")
    if not args.no_browser and os.environ.get("VIDEO_DOWNLOADER_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console_log("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (APP_ROOT / "server.crash.log").write_text(
            traceback.format_exc(),
            encoding="utf-8",
        )
        raise
