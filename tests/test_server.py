import json
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

import server


class ServerHelpersTest(unittest.TestCase):
    def test_detect_platform(self):
        self.assertEqual(server.detect_platform("https://youtu.be/demo")["label"], "YouTube")
        self.assertEqual(
            server.detect_platform("https://www.bilibili.com/video/BV123")["label"],
            "Bilibili",
        )
        self.assertEqual(server.detect_platform("https://example.com/watch")["label"], "自动识别")

    def test_preset_arguments_for_mp4_height(self):
        args = server.preset_arguments("mp4_1080")
        joined = " ".join(args)
        self.assertIn("height<=1080", joined)
        self.assertIn("--merge-output-format", args)

    def test_bilibili_network_args_include_origin(self):
        args = server.ytdlp_network_args("https://www.bilibili.com/video/BV123")
        self.assertIn("--referer", args)
        self.assertIn("https://www.bilibili.com/", args)
        self.assertIn("--add-header", args)
        self.assertIn("Origin:https://www.bilibili.com", args)

    def test_presets_include_size_labels(self):
        formats = [
            {
                "height": 1080,
                "vcodec": "avc1",
                "acodec": "none",
                "ext": "mp4",
                "filesize": 100 * 1024 * 1024,
                "tbr": 4000,
            },
            {
                "vcodec": "none",
                "acodec": "mp4a",
                "ext": "m4a",
                "filesize": 10 * 1024 * 1024,
                "abr": 128,
            },
        ]
        presets = server.build_presets(formats, 120)

        self.assertIn("sizeLabel", presets[0])
        self.assertEqual(presets[0]["sizeLabel"], "110 MB")

    def test_progress_line_updates_job(self):
        job = server.DownloadJob(
            id="test",
            url="https://example.com/watch",
            preset="best",
            output_dir=str(Path.cwd()),
        )
        server.apply_process_line(
            job,
            "[download]  42.5% of 10.00MiB at 1.20MiB/s ETA 00:04",
        )
        self.assertEqual(job.status, "running")
        self.assertEqual(job.progress, 42.5)
        self.assertEqual(job.speed, "1.20MiB/s")
        self.assertEqual(job.eta, "00:04")

    def test_error_line_adds_diagnosis_to_job(self):
        job = server.DownloadJob(
            id="test",
            url="https://www.bilibili.com/video/BV123",
            preset="best",
            output_dir=str(Path.cwd()),
        )
        server.apply_process_line(job, "ERROR: HTTP Error 403: Forbidden")

        self.assertEqual(job.status, "error")
        self.assertEqual(job.diagnosis["kind"], "login_required")
        self.assertEqual(job.diagnosis["action"], "enable_cookies")

    def test_diagnose_bilibili_412(self):
        result = server.diagnose_error(
            "HTTP Error 412: Precondition Failed",
            "https://www.bilibili.com/video/BV123",
        )

        self.assertEqual(result["kind"], "platform_risk")
        self.assertEqual(result["action"], "update_components")

    def test_diagnose_cookie_error(self):
        result = server.diagnose_error("could not decrypt cookies: DPAPI failed")

        self.assertEqual(result["kind"], "browser_cookie")
        self.assertEqual(result["action"], "switch_browser")

    def test_diagnose_missing_components(self):
        ytdlp = server.diagnose_error("未找到 yt-dlp，请先安装或放入系统 PATH")
        ffmpeg = server.diagnose_error("ffmpeg not found")

        self.assertEqual(ytdlp["kind"], "missing_ytdlp")
        self.assertEqual(ffmpeg["kind"], "missing_ffmpeg")

    def test_diagnose_network_output_and_unknown_errors(self):
        network = server.diagnose_error("The read operation timed out")
        output = server.diagnose_error("Permission denied: C:/locked")
        unknown = server.diagnose_error("Something unexpected happened")

        self.assertEqual(network["kind"], "network_error")
        self.assertEqual(output["kind"], "output_path_error")
        self.assertEqual(unknown["kind"], "generic_error")

    def test_error_payload_includes_diagnosis(self):
        payload = server.error_payload(
            RuntimeError("HTTP Error 403: Forbidden"),
            "https://youtu.be/demo",
        )

        self.assertIn("error", payload)
        self.assertEqual(payload["diagnosis"]["kind"], "login_required")

    def test_inspect_video_returns_guidance(self):
        output = {
            "webpage_url": "https://www.bilibili.com/video/BV123",
            "title": "demo",
            "formats": [],
        }
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(output), stderr="")
        with mock.patch.object(server, "YTDLP_PATH", "yt-dlp"):
            with mock.patch.object(server.subprocess, "run", return_value=completed):
                result = server.inspect_video("https://www.bilibili.com/video/BV123")

        self.assertEqual(result["guidance"]["kind"], "login_recommended")
        self.assertEqual(result["guidance"]["action"], "enable_cookies")

    def test_resolve_executable_prefers_project_venv(self):
        with mock.patch.object(server, "LOCAL_BIN_DIR", Path("C:/app/.venv/Scripts")):
            with mock.patch.object(Path, "exists", return_value=True):
                self.assertEqual(
                    server.resolve_executable("yt-dlp"),
                    "C:\\app\\.venv\\Scripts\\yt-dlp.exe",
                )

    def test_subprocess_env_adds_project_venv_to_path(self):
        with mock.patch.object(server, "LOCAL_BIN_DIR", Path("C:/app/.venv/Scripts")):
            with mock.patch.object(Path, "exists", return_value=True):
                with mock.patch.dict(server.os.environ, {"PATH": "C:/Windows"}, clear=True):
                    env = server.subprocess_env()
        self.assertTrue(env["PATH"].startswith("C:\\app\\.venv\\Scripts;"))

    def test_resolve_ffmpeg_prefers_imageio_binary_before_path(self):
        imageio_ffmpeg = (
            Path("C:/app/.venv/Lib/site-packages/imageio_ffmpeg/binaries")
            / "ffmpeg-win-x86_64-v7.1.exe"
        )
        with mock.patch.object(server, "LOCAL_BIN_DIR", Path("C:/app/.venv/Scripts")):
            with mock.patch.object(server, "LOCAL_SITE_PACKAGES", Path("C:/app/.venv/Lib/site-packages")):
                with mock.patch.object(Path, "exists", return_value=False):
                    with mock.patch.object(Path, "glob", return_value=[imageio_ffmpeg]):
                        with mock.patch.object(Path, "is_file", return_value=True):
                            with mock.patch.object(server.shutil, "which", return_value="C:/Miniconda3/Library/bin/ffmpeg.exe"):
                                self.assertEqual(server.resolve_ffmpeg(), str(imageio_ffmpeg))

    def test_download_command_uses_selected_ffmpeg(self):
        with mock.patch.object(server, "YTDLP_PATH", "C:/app/.venv/Scripts/yt-dlp.exe"):
            with mock.patch.object(server, "FFMPEG_PATH", "C:/app/ffmpeg.exe"):
                command = server.build_download_command(
                    "https://youtu.be/demo",
                    "audio_mp3",
                    Path("C:/downloads"),
                    False,
                    False,
                    False,
                    None,
                )
        ffmpeg_index = command.index("--ffmpeg-location")
        self.assertEqual(command[ffmpeg_index + 1], "C:/app/ffmpeg.exe")


if __name__ == "__main__":
    unittest.main()
