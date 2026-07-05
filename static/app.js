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
  outputSummary: document.querySelector("#outputSummary"),
  advancedToggle: document.querySelector("#advancedToggle"),
  advancedPanel: document.querySelector("#advancedPanel"),
  inspectButton: document.querySelector("#inspectButton"),
  inspectButtonLabel: document.querySelector("#inspectButtonLabel"),
  downloadButton: document.querySelector("#downloadButton"),
  downloadButtonLabel: document.querySelector("#downloadButtonLabel"),
  advancedToggleLabel: document.querySelector("#advancedToggleLabel"),
  previewCard: document.querySelector("#previewCard"),
  presetList: document.querySelector("#presetList"),
  presetTemplate: document.querySelector("#presetTemplate"),
  platformLabel: document.querySelector("#platformLabel"),
  healthBadge: document.querySelector("#healthBadge"),
  statusRegion: document.querySelector("#statusRegion"),
  guidancePanel: document.querySelector("#guidancePanel"),
  jobList: document.querySelector("#jobList"),
  queueSummary: document.querySelector("#queueSummary"),
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
    const error = new Error(payload.error || "请求失败");
    error.payload = payload;
    error.diagnosis = payload.diagnosis || null;
    throw error;
  }
  return payload;
}

function setStatus(message = "", tone = "neutral") {
  nodes.statusRegion.textContent = message;
  nodes.statusRegion.dataset.tone = tone;
}

function toast(message, tone = "neutral") {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const el = document.createElement("div");
  el.className = `toast ${tone}`;
  el.textContent = message;
  document.body.appendChild(el);
  setStatus(message, tone);
  window.setTimeout(() => el.remove(), 3600);
}

function closeBrowserMenu() {
  nodes.browserPickerMenu.hidden = true;
  nodes.browserPickerButton.setAttribute("aria-expanded", "false");
}

function openBrowserMenu() {
  if (nodes.browserPickerButton.disabled) return;
  nodes.browserPickerMenu.hidden = false;
  nodes.browserPickerButton.setAttribute("aria-expanded", "true");
  const selected = nodes.browserPickerMenu.querySelector('[aria-selected="true"]');
  selected?.focus();
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
  nodes.browserPicker.classList.toggle("is-disabled", !isEnabled);
  if (!isEnabled) closeBrowserMenu();
}

function setAdvancedOpen(isOpen) {
  nodes.advancedPanel.hidden = !isOpen;
  nodes.advancedToggle.setAttribute("aria-expanded", String(isOpen));
  nodes.advancedToggleLabel.textContent = isOpen ? "收起设置" : "高级设置";
}

function setBusy(isBusy) {
  nodes.inspectButton.disabled = isBusy;
  nodes.inspectButton.classList.toggle("is-loading", isBusy);
  nodes.inspectButtonLabel.textContent = isBusy ? "识别中" : "识别视频";
}

function setDownloadLabel(label) {
  nodes.downloadButtonLabel.textContent = label;
}

function icon(name) {
  return `<svg class="icon" aria-hidden="true"><use href="#icon-${escapeAttr(name)}"></use></svg>`;
}

function presetIconName(kind) {
  return kind === "audio" ? "music" : "video";
}

function actionIconName(action) {
  return {
    enable_cookies: "user",
    switch_browser: "sliders",
    check_output_dir: "folder-open",
    update_components: "refresh-cw",
    try_again: "refresh-cw",
  }[action] || "circle-dot";
}

function statusIconName(status) {
  return {
    queued: "circle-dot",
    running: "download",
    done: "check-circle",
    error: "alert-triangle",
    cancelled: "x-circle",
  }[status] || "circle-dot";
}

function compactPath(path) {
  const parts = String(path || "")
    .split(/[\\/]/)
    .filter(Boolean);
  return parts.at(-1) || "downloads";
}

function updateOutputSummary() {
  const value = nodes.outputInput.value.trim();
  nodes.outputSummary.textContent = `保存到 ${compactPath(value)}`;
  nodes.outputSummary.title = value || "默认下载目录";
}

function renderLoadingPreview() {
  nodes.previewCard.innerHTML = `
    <div class="loading-state">
      <div class="preview-frame loading-preview" aria-hidden="true">
        <div class="preview-frame-top"></div>
        <div class="preview-frame-play">${icon("search")}</div>
        <div class="preview-frame-line wide"></div>
        <div class="preview-frame-line"></div>
      </div>
      <p class="eyebrow">Preview</p>
      <h2>正在识别视频</h2>
      <p>正在读取标题、封面、时长和可保存规格。</p>
      <div class="loading-bar" aria-hidden="true"></div>
    </div>
  `;
}

function renderPreview(video) {
  const thumbnail = video.thumbnail
    ? `<img src="${escapeAttr(video.thumbnail)}" alt="" referrerpolicy="no-referrer">`
    : `<div class="thumbnail-fallback">${icon("play-circle")}<span>没有可用封面</span></div>`;
  const platform = video.platform?.label || "视频";
  const uploader = video.uploader
    ? `<span class="meta-item">${icon("user")}<span>${escapeHtml(video.uploader)}</span></span>`
    : "";
  const heights = video.heights?.length ? `<span class="media-badge">最高 ${video.heights[0]}p</span>` : "";
  const duration = video.duration
    ? `<span class="media-badge dark">${escapeHtml(video.duration)}</span>`
    : "";

  nodes.previewCard.innerHTML = `
    <div class="video-preview">
      <div class="thumb-wrap">
        ${thumbnail}
        <div class="media-badges">
          <span class="media-badge">${icon("video")}${escapeHtml(platform)}</span>
          ${heights}
          ${duration}
        </div>
      </div>
      <div class="preview-meta">
        <p class="eyebrow">Identified</p>
        <h2>${escapeHtml(video.title)}</h2>
        <div class="meta-row">
          ${uploader}
          <span class="chip">${icon("check-circle")}可保存规格已就绪</span>
        </div>
      </div>
    </div>
  `;
}

function renderFormatEmpty(title = "还没有可选规格", body = "先识别视频，再选择最佳画质、MP4 或仅音频。") {
  nodes.presetList.innerHTML = `
    <div class="format-empty">
      <span class="empty-icon" aria-hidden="true">${icon("sparkles")}</span>
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(body)}</span>
    </div>
  `;
}

function renderPresets(presets) {
  nodes.presetList.innerHTML = "";
  presets.forEach((preset, index) => {
    const clone = nodes.presetTemplate.content.firstElementChild.cloneNode(true);
    const input = clone.querySelector("input");
    const kind = preset.kind || "video";
    input.value = preset.id;
    input.checked = preset.recommended || index === 0;
    clone.dataset.kind = kind;
    if (preset.recommended) clone.classList.add("recommended");
    clone.querySelector(".preset-icon").innerHTML = icon(presetIconName(kind));
    clone.querySelector(".recommended-badge").hidden = !preset.recommended;
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

function actionLabel(action) {
  return {
    enable_cookies: "启用登录状态",
    switch_browser: "切换浏览器",
    check_output_dir: "检查保存位置",
    update_components: "查看更新方法",
    try_again: "重新尝试",
    none: "",
  }[action] || "";
}

function fallbackDiagnosis(message) {
  const raw = String(message || "请求失败");
  const lower = raw.toLowerCase();
  if (lower.includes("cookie") || lower.includes("dpapi") || lower.includes("decrypt")) {
    const browser = browserLabels[nodes.cookieBrowserInput.value] || "浏览器";
    return {
      kind: "browser_cookie",
      title: "无法读取浏览器登录状态",
      summary: `${browser} 的登录数据当前不可读取，常见原因是浏览器正在占用 cookie 数据库，或所选浏览器没有可用登录状态。`,
      steps: [
        `确认 ${browser} 已登录对应平台。`,
        "关闭浏览器窗口后再试一次，或切换到另一个已登录浏览器。",
        "如果是公开视频，可以先关闭“使用浏览器登录状态”再识别。",
      ],
      action: "switch_browser",
      detail: raw,
    };
  }
  if (raw.includes("403") || lower.includes("forbidden") || lower.includes("sign in") || lower.includes("login")) {
    return {
      kind: "login_required",
      title: "可能需要登录状态",
      summary: "平台拒绝了当前请求，常见原因是登录状态、会员权限、年龄限制或风控校验。",
      steps: ["确认浏览器已登录该平台。", "启用浏览器登录状态，必要时切换浏览器。", "重新识别或下载这个链接。"],
      action: nodes.cookiesInput.checked ? "switch_browser" : "enable_cookies",
      detail: raw,
    };
  }
  if (lower.includes("timed out") || lower.includes("timeout") || raw.includes("超时")) {
    return {
      kind: "network_error",
      title: "网络连接不稳定",
      summary: "视频源响应太慢或连接被中断。",
      steps: ["确认浏览器能正常打开该视频页面。", "稍后重新识别或下载。"],
      action: "try_again",
      detail: raw,
    };
  }
  return {
    kind: "generic_error",
    title: "没有完成这次操作",
    summary: "当前错误无法自动判断原因，可以先确认链接是否可在浏览器打开。",
    steps: ["确认链接完整。", "需要登录的平台先启用浏览器登录状态。", "如果反复失败，更新下载组件后重试。"],
    action: "try_again",
    detail: raw,
  };
}

function diagnosisTemplate(diagnosis, detail = "") {
  const info = diagnosis || fallbackDiagnosis(detail);
  const steps = Array.isArray(info.steps) ? info.steps : [];
  const label = actionLabel(info.action);
  return `
    <div class="diagnosis-card" data-kind="${escapeAttr(info.kind || "generic_error")}">
      <div class="diagnosis-title">
        ${icon(info.kind === "login_recommended" || info.kind === "login_required" ? "user" : "alert-triangle")}
        <strong>${escapeHtml(info.title || "需要处理后重试")}</strong>
      </div>
      <p>${escapeHtml(info.summary || "")}</p>
      ${
        steps.length
          ? `<ol>${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>`
          : ""
      }
      ${
        label
          ? `<button class="diagnosis-action" type="button" data-diagnosis-action="${escapeAttr(info.action)}">${icon(actionIconName(info.action))}<span>${escapeHtml(label)}</span></button>`
          : ""
      }
    </div>
  `;
}

function clientGuidance() {
  const url = nodes.urlInput.value.trim();
  if (!url) return null;
  const platform = detectPlatform(url);
  if (["Bilibili", "YouTube", "Douyin"].includes(platform) && !nodes.cookiesInput.checked) {
    return {
      kind: "login_recommended",
      title: `${platform} 可能需要登录状态`,
      summary: "如果后续识别或下载失败，先启用已登录浏览器通常是最快的恢复路径。",
      steps: ["先直接识别公开视频。", "遇到 403、会员或风控提示时，再启用浏览器登录状态。"],
      action: "enable_cookies",
    };
  }
  if (nodes.playlistInput.checked) {
    return {
      kind: "playlist_notice",
      title: "合集下载会花更久",
      summary: "合集里任意一个视频受限，都可能让任务失败。",
      steps: ["如果合集失败，先关闭合集选项验证单个视频。"],
      action: "try_again",
    };
  }
  if (nodes.subtitleInput.checked) {
    return {
      kind: "subtitle_notice",
      title: "字幕取决于平台提供情况",
      summary: "有些视频没有字幕，或平台不允许读取自动字幕。",
      steps: ["如果视频能下载但字幕失败，可以先关闭字幕选项。"],
      action: "try_again",
    };
  }
  return null;
}

function renderGuidance(guidance = null) {
  const info = guidance || clientGuidance();
  if (!info) {
    nodes.guidancePanel.hidden = true;
    nodes.guidancePanel.innerHTML = "";
    return;
  }
  nodes.guidancePanel.hidden = false;
  nodes.guidancePanel.innerHTML = diagnosisTemplate(info);
  bindDiagnosisActions(nodes.guidancePanel);
}

function renderError(error) {
  const info = error.diagnosis || fallbackDiagnosis(error.message);
  nodes.previewCard.innerHTML = `
    <div class="error-state">
      <p class="eyebrow">Needs Attention</p>
      <h2>${escapeHtml(info.title)}</h2>
      <p>${escapeHtml(info.summary)}</p>
      ${diagnosisTemplate(info, error.message)}
      <details class="error-detail">
        <summary>技术详情</summary>
        <code>${escapeHtml(error.message)}</code>
      </details>
    </div>
  `;
  bindDiagnosisActions(nodes.previewCard);
  renderFormatEmpty("等待成功识别", "解决上方问题后，保存规格会显示在这里。");
  nodes.downloadButton.disabled = true;
}

function handleDiagnosisAction(action) {
  if (action === "enable_cookies") {
    setAdvancedOpen(true);
    nodes.cookiesInput.checked = true;
    setBrowserPickerEnabled();
    nodes.browserPickerButton.focus();
    renderGuidance();
    toast("已启用浏览器登录状态，请确认浏览器已登录对应平台", "success");
    return;
  }
  if (action === "switch_browser") {
    setAdvancedOpen(true);
    nodes.cookiesInput.checked = true;
    setBrowserPickerEnabled();
    openBrowserMenu();
    return;
  }
  if (action === "check_output_dir") {
    setAdvancedOpen(true);
    nodes.outputInput.focus();
    nodes.outputInput.select();
    toast("请换到一个可写的保存位置后再试", "error");
    return;
  }
  if (action === "update_components") {
    setStatus("请按 README 的“下载组件”步骤更新 yt-dlp 和 ffmpeg，然后重启本工具。", "info");
    toast("更新方法已显示在 README 的下载组件章节", "neutral");
    return;
  }
  if (action === "try_again") {
    nodes.inspectButton.focus();
    setStatus("检查设置后，再点击“识别视频”或“开始下载”。", "info");
  }
}

function bindDiagnosisActions(root) {
  root.querySelectorAll("[data-diagnosis-action]").forEach((button) => {
    button.addEventListener("click", () => handleDiagnosisAction(button.dataset.diagnosisAction));
  });
}

async function inspectVideo(event) {
  event.preventDefault();
  const url = nodes.urlInput.value.trim();
  if (!url) return;

  state.inspected = null;
  nodes.downloadButton.disabled = true;
  setDownloadLabel("开始下载");
  nodes.platformLabel.textContent = detectPlatform(url);
  renderGuidance(null);
  renderLoadingPreview();
  renderFormatEmpty("正在读取规格", "这通常需要几秒钟，复杂页面可能更久。");
  setStatus("正在识别视频源", "info");
  setBusy(true);
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
    renderGuidance(video.guidance);
    nodes.downloadButton.disabled = false;
    setStatus("视频已识别，可以选择保存规格", "success");
  } catch (error) {
    renderError(error);
    renderGuidance(error.diagnosis);
    setStatus("识别失败，需要处理后重试", "error");
  } finally {
    setBusy(false);
  }
}

async function startDownload() {
  const url = nodes.urlInput.value.trim();
  if (!url) return toast("请输入视频链接", "error");

  nodes.downloadButton.disabled = true;
  setDownloadLabel("加入任务中");
  setStatus("正在加入下载任务", "info");
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
    toast("已加入下载任务", "success");
  } catch (error) {
    renderGuidance(error.diagnosis);
    toast(error.message, "error");
  } finally {
    nodes.downloadButton.disabled = false;
    setDownloadLabel("开始下载");
  }
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    nodes.outputInput.value = health.downloadDir;
    updateOutputSummary();
    if (health.ytDlp && health.ffmpeg) {
      nodes.healthBadge.className = "health ready";
      nodes.healthBadge.textContent = `组件就绪 · yt-dlp ${health.ytDlp}`;
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

function isActiveJob(job) {
  return job.status === "queued" || job.status === "running" || job.status === "error";
}

function renderJobs(jobs) {
  if (!jobs.length) {
    nodes.queueSummary.textContent = "暂无进行中的下载";
    nodes.jobList.innerHTML = `<div class="queue-empty">还没有下载任务</div>`;
    return;
  }

  const activeJobs = jobs.filter(isActiveJob);
  const completedJobs = jobs.filter((job) => !isActiveJob(job));
  nodes.queueSummary.textContent = activeJobs.length
    ? `${activeJobs.length} 个任务需要关注`
    : "暂无进行中的下载";

  const parts = [];
  if (activeJobs.length) {
    parts.push(...activeJobs.map((job) => jobTemplate(job)));
  } else {
    parts.push(`<div class="queue-empty compact">当前没有正在下载的任务</div>`);
  }

  if (completedJobs.length) {
    parts.push(`
      <details class="history-group">
        <summary>最近完成 ${completedJobs.length}</summary>
        <div class="history-list">
          ${completedJobs.slice(0, 5).map((job) => jobTemplate(job, true)).join("")}
        </div>
      </details>
    `);
  }

  nodes.jobList.innerHTML = parts.join("");
  nodes.jobList.querySelectorAll("[data-cancel]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.getAttribute("data-cancel");
      await api(`/api/jobs/${id}/cancel`, { method: "POST", body: "{}" }).catch((error) =>
        toast(error.message, "error"),
      );
      refreshJobs();
    });
  });
  bindDiagnosisActions(nodes.jobList);
}

function jobTemplate(job, isMuted = false) {
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
    <article class="job-card ${escapeAttr(job.status)} ${isMuted ? "muted" : ""}">
      <div class="job-title">
        <strong>${escapeHtml(job.title || "视频")}</strong>
        <span class="status-pill ${escapeAttr(job.status)}">${icon(statusIconName(job.status))}<span>${escapeHtml(status)}</span></span>
      </div>
      <div
        class="progress-track"
        role="progressbar"
        aria-label="下载进度"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow="${pct.toFixed(0)}"
      >
        <div class="progress-fill" style="width: ${pct}%"></div>
      </div>
      <div class="job-meta">
        <span>${pct.toFixed(pct >= 99 ? 0 : 1)}%</span>
        ${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
      ${job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ""}
      ${job.diagnosis ? `<div class="job-diagnosis">${diagnosisTemplate(job.diagnosis, job.error)}</div>` : ""}
      ${
        canCancel
          ? `<button class="cancel-button" data-cancel="${escapeAttr(job.id)}">${icon("x-circle")}<span>取消任务</span></button>`
          : ""
      }
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
    toast(error.message, "error"),
  );
});
nodes.advancedToggle.addEventListener("click", () => {
  setAdvancedOpen(nodes.advancedPanel.hidden);
});
nodes.outputInput.addEventListener("input", updateOutputSummary);
nodes.urlInput.addEventListener("input", () => {
  nodes.platformLabel.textContent = detectPlatform(nodes.urlInput.value);
  renderGuidance();
});
nodes.browserPickerButton.addEventListener("click", () => {
  if (nodes.browserPickerButton.disabled) return;
  const shouldOpen = nodes.browserPickerMenu.hidden;
  if (shouldOpen) openBrowserMenu();
  else closeBrowserMenu();
});
nodes.browserPickerButton.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openBrowserMenu();
  }
});
nodes.browserPickerMenu.querySelectorAll("[data-browser]").forEach((option) => {
  option.addEventListener("click", () => {
    updateBrowserPicker(option.dataset.browser);
    closeBrowserMenu();
    nodes.browserPickerButton.focus();
  });
  option.addEventListener("keydown", (event) => {
    const options = [...nodes.browserPickerMenu.querySelectorAll("[data-browser]")];
    const index = options.indexOf(option);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      options[(index + 1) % options.length].focus();
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      options[(index - 1 + options.length) % options.length].focus();
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      updateBrowserPicker(option.dataset.browser);
      closeBrowserMenu();
      nodes.browserPickerButton.focus();
    }
  });
});
document.addEventListener("click", (event) => {
  if (!nodes.browserPicker.contains(event.target)) closeBrowserMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeBrowserMenu();
    nodes.browserPickerButton.focus();
  }
});
nodes.cookiesInput.addEventListener("change", () => {
  setBrowserPickerEnabled();
  renderGuidance();
});
nodes.playlistInput.addEventListener("change", renderGuidance);
nodes.subtitleInput.addEventListener("change", renderGuidance);
updateBrowserPicker(nodes.cookieBrowserInput.value);
setBrowserPickerEnabled();
setAdvancedOpen(false);
renderGuidance();

loadHealth();
refreshJobs();
state.jobsTimer = window.setInterval(refreshJobs, 1200);
