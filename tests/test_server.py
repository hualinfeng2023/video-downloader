import unittest
from unittest import mock
from pathlib import Path

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
