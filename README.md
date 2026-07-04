# Video Downloader

一个本地运行的流媒体视频下载工具，前端提供粘贴链接、识别视频、选择保存方式、查看下载进度等主流程；后端使用 `yt-dlp` 和 `ffmpeg` 处理 YouTube、Bilibili 等平台的视频解析与下载。

## 启动

```powershell
python server.py
```

启动后打开：

```text
http://127.0.0.1:8787
```

下载文件默认保存到项目内的 `downloads` 文件夹，也可以在界面里填写其他目录。

## 下载组件

本工具会优先使用项目内 `.venv\Scripts\yt-dlp.exe`，并使用项目内带 MP3 编码能力的 ffmpeg。首次配置或更新下载组件：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U -r requirements.txt
```

## 功能

- 自动识别 YouTube、Bilibili、Douyin、Vimeo 以及 yt-dlp 支持的其他站点
- 识别标题、封面、作者、时长和可用清晰度
- 支持最佳画质、常用 MP4 清晰度、仅音频 MP3，并显示预计文件大小
- 支持合集下载和字幕保存
- 支持读取 Chrome、Edge、Firefox 的登录状态，用于处理会员、年龄限制或平台 403
- 下载队列显示进度、速度、剩余时间、失败原因和取消按钮

## 403 Forbidden

如果下载任务提示 `HTTP Error 403: Forbidden`：

1. 先在 Chrome、Edge 或 Firefox 打开对应平台并登录账号。
2. 回到本工具，勾选“使用浏览器登录状态”。
3. 选择刚才登录的平台浏览器，再重新识别或下载。
4. 如果仍失败，更新项目内下载组件：

```powershell
.\.venv\Scripts\python.exe -m pip install -U -r requirements.txt
```

请仅下载你拥有权利或被授权保存的内容，并遵守对应平台条款。
