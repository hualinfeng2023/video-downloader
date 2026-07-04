const state = {
  inspected: null,
  selectedPreset: "best",
  jobsTimer: null,
};

const nodes = {
  form: document.querySelector("#inspectForm"),
  urlInput: document.querySelector("#urlInput"),
  playlistInput: document.querySelector("#playlistInput"),
  subtitleInput: document.querySelector("#subtitleInput"),
  cookiesInput: document.querySelector("#cookiesInput"),
  cookieBrowserInput: document.querySelector("#cookieBrowserInput"),
  browserPicker: document.querySelector("#browserPicker"),
  browserPickerButton: document.querySelector("#browserPickerButton"),
  browserPickerIcon: document.querySelector("#browserPickerIcon"),
  browserPickerLabel: document.querySelector("#browserPickerLabel"),
  browserPickerMenu: document.querySelector("#browserPickerMenu"),
  outputInput: document.querySelector("#outputInput"),
  inspectButton: document.querySelector("#inspectButton"),
  downloadButton: document.querySelector("#downloadButton"),
  previewCard: document.querySelector("#previewCard"),
  presetList: document.querySelector("#presetList"),
  presetTemplate: document.querySelector("#presetTemplate"),
  platformLabel: document.querySelector("#platformLabel"),
  healthBadge: document.querySelector("#healthBadge"),
  jobList: document.querySelector("#jobList"),
  openFolderButton: document.querySelector("#openFolderButton"),
};

const statusText = {
  queued: "等待",
  running: "下载中",
  done: "完成",
  error: "失败",
  cancelled: "已取消",
};

const browserLabels = {
  chrome: "Chrome",
  edge: "Edge",
  firefox: "Firefox",
};

function detectPlatform(url) {
  let host = "";
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return "自动识别";
  }
  if (host.includes("youtube.com") || host.includes("youtu.be")) return "YouTube";
  if (host.includes("bilibili.com") || host === "b23.tv" || host.endsWith(".b23.tv")) return "Bilibili";
  if (host.includes("douyin.com")) return "Douyin";
  if (host.includes("vimeo.com")) return "Vimeo";
  return "自动识别";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

function toast(message) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  document.body.appendChild(el);
  window.setTimeout(() => el.remove(), 3600);
}

function closeBrowserMenu() {
  nodes.browserPickerMenu.hidden = true;
  nodes.browserPickerButton.setAttribute("aria-expanded", "false");
}

function updateBrowserPicker(value) {
  const browser = browserLabels[value] ? value : "chrome";
  nodes.cookieBrowserInput.value = browser;
  nodes.browserPickerLabel.textContent = browserLabels[browser];
  nodes.browserPickerIcon.className = `browser-icon ${browser}`;
  nodes.browserPickerMenu.querySelectorAll("[data-browser]").forEach((option) => {
    option.setAttribute("aria-selected", String(option.dataset.browser === browser));
  });
}

function setBrowserPickerEnabled() {
  const isEnabled = nodes.cookiesInput.checked;
  nodes.cookieBrowserInput.disabled = !isEnabled;
  nodes.browserPickerButton.disabled = !isEnabled;
  if (!isEnabled) closeBrowserMenu();
}

function setBusy(isBusy) {
  nodes.inspectButton.disabled = isBusy;
  nodes.inspectButton.textContent = isBusy ? "识别中" : "识别视频";
}

function renderPreview(video) {
  const thumbnail = video.thumbnail
    ? `<img src="${escapeAttr(video.thumbnail)}" alt="">`
    : `<div class="empty-state"><div class="empty-icon">VIDEO</div></div>`;
  const uploader = video.uploader ? `<span>${escapeHtml(video.uploader)}</span>` : "";
  const heights = video.heights?.length
    ? `<span class="chip">最高 ${video.heights[0]}p</span>`
    : "";
  const duration = video.duration
    ? `<span class="duration-pill">${escapeHtml(video.duration)}</span>`
    : "";

  nodes.previewCard.innerHTML = `
    <div class="video-preview">
      <div class="thumb-wrap">
        ${thumbnail}
        ${duration}
      </div>
      <div class="preview-meta">
        <h2>${escapeHtml(video.title)}</h2>
        <div class="meta-row">
          <span class="chip">${escapeHtml(video.platform.label)}</span>
          ${uploader}
          ${heights}
        </div>
      </div>
    </div>
  `;
}

function renderPresets(presets) {
  nodes.presetList.innerHTML = "";
  presets.forEach((preset, index) => {
    const clone = nodes.presetTemplate.content.firstElementChild.cloneNode(true);
    const input = clone.querySelector("input");
    input.value = preset.id;
    input.checked = preset.recommended || index === 0;
    clone.querySelector("strong").textContent = preset.label;
    clone.querySelector("em").textContent = preset.sizeLabel || "大小未知";
    clone.querySelector("small").textContent = preset.detail;
    input.addEventListener("change", () => {
      state.selectedPreset = preset.id;
    });
    nodes.presetList.appendChild(clone);
    if (input.checked) state.selectedPreset = preset.id;
  });
}

async function inspectVideo(event) {
  event.preventDefault();
  const url = nodes.urlInput.value.trim();
  if (!url) return;

  setBusy(true);
  nodes.platformLabel.textContent = detectPlatform(url);
  try {
    const video = await api("/api/inspect", {
      method: "POST",
      body: JSON.stringify({
        url,
        useCookies: nodes.cookiesInput.checked,
        cookieBrowser: nodes.cookieBrowserInput.value,
      }),
    });
    state.inspected = video;
    nodes.urlInput.value = video.url || url;
    nodes.platformLabel.textContent = video.platform.label;
    renderPreview(video);
    renderPresets(video.presets);
    nodes.downloadButton.disabled = false;
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(false);
  }
}

async function startDownload() {
  const url = nodes.urlInput.value.trim();
  if (!url) return toast("请输入视频链接");

  nodes.downloadButton.disabled = true;
  nodes.downloadButton.textContent = "加入任务中";
  try {
    await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url,
        preset: state.selectedPreset,
        title: state.inspected?.title,
        playlist: nodes.playlistInput.checked,
        subtitles: nodes.subtitleInput.checked,
        useCookies: nodes.cookiesInput.checked,
        cookieBrowser: nodes.cookieBrowserInput.value,
        outputDir: nodes.outputInput.value.trim(),
      }),
    });
    await refreshJobs();
    toast("已开始下载");
  } catch (error) {
    toast(error.message);
  } finally {
    nodes.downloadButton.disabled = false;
    nodes.downloadButton.textContent = "开始下载";
  }
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    nodes.outputInput.value = health.downloadDir;
    if (health.ytDlp && health.ffmpeg) {
      nodes.healthBadge.className = "health ready";
      nodes.healthBadge.textContent = `yt-dlp ${health.ytDlp}`;
    } else {
      nodes.healthBadge.className = "health warn";
      nodes.healthBadge.textContent = "缺少下载组件";
    }
  } catch {
    nodes.healthBadge.className = "health warn";
    nodes.healthBadge.textContent = "服务未连接";
  }
}

async function refreshJobs() {
  try {
    const jobs = await api("/api/jobs");
    renderJobs(jobs);
  } catch {
    renderJobs([]);
  }
}

function renderJobs(jobs) {
  if (!jobs.length) {
    nodes.jobList.innerHTML = `<div class="queue-empty">还没有下载任务</div>`;
    return;
  }

  nodes.jobList.innerHTML = jobs.map(jobTemplate).join("");
  nodes.jobList.querySelectorAll("[data-cancel]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.getAttribute("data-cancel");
      await api(`/api/jobs/${id}/cancel`, { method: "POST", body: "{}" }).catch((error) =>
        toast(error.message),
      );
      refreshJobs();
    });
  });
}

function jobTemplate(job) {
  const pct = Math.max(0, Math.min(Number(job.progress) || 0, 100));
  const status = statusText[job.status] || job.status;
  const canCancel = job.status === "queued" || job.status === "running";
  const meta = [
    job.platform,
    job.message,
    job.speed,
    job.eta ? `剩余 ${job.eta}` : "",
  ].filter(Boolean);
  return `
    <article class="job-card">
      <div class="job-title">
        <strong>${escapeHtml(job.title || "视频")}</strong>
        <span class="status-pill ${escapeAttr(job.status)}">${escapeHtml(status)}</span>
      </div>
      <div class="progress-track" aria-label="下载进度">
        <div class="progress-fill" style="width: ${pct}%"></div>
      </div>
      <div class="job-meta">
        <span>${pct.toFixed(pct >= 99 ? 0 : 1)}%</span>
        ${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
      ${job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ""}
      ${canCancel ? `<button class="cancel-button" data-cancel="${escapeAttr(job.id)}">取消任务</button>` : ""}
    </article>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

nodes.form.addEventListener("submit", inspectVideo);
nodes.downloadButton.addEventListener("click", startDownload);
nodes.openFolderButton.addEventListener("click", async () => {
  await api("/api/open-downloads", { method: "POST", body: "{}" }).catch((error) =>
    toast(error.message),
  );
});
nodes.urlInput.addEventListener("input", () => {
  nodes.platformLabel.textContent = detectPlatform(nodes.urlInput.value);
});
nodes.browserPickerButton.addEventListener("click", () => {
  if (nodes.browserPickerButton.disabled) return;
  const shouldOpen = nodes.browserPickerMenu.hidden;
  nodes.browserPickerMenu.hidden = !shouldOpen;
  nodes.browserPickerButton.setAttribute("aria-expanded", String(shouldOpen));
});
nodes.browserPickerMenu.querySelectorAll("[data-browser]").forEach((option) => {
  option.addEventListener("click", () => {
    updateBrowserPicker(option.dataset.browser);
    closeBrowserMenu();
    nodes.browserPickerButton.blur();
  });
});
document.addEventListener("click", (event) => {
  if (!nodes.browserPicker.contains(event.target)) closeBrowserMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeBrowserMenu();
});
nodes.cookiesInput.addEventListener("change", setBrowserPickerEnabled);
updateBrowserPicker(nodes.cookieBrowserInput.value);
setBrowserPickerEnabled();

loadHealth();
refreshJobs();
state.jobsTimer = window.setInterval(refreshJobs, 1200);
