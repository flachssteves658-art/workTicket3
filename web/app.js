const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const MAX_BATCH_FILES = 20;
const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".bmp", ".webp"]);
const STRUCTURE_EXTENSIONS = new Set([...IMAGE_EXTENSIONS, ".pdf"]);

const state = {
  activeMode: "structure",
  structureFiles: [],
  visionFiles: [],
  batchJobs: [],
  activeJobId: null,
  isRunning: false,
  lastText: "{}",
  timeline: new Map(),
  runClock: null,
  assetResult: null,
  streamOptions: [],
};

const metricEls = {
  upload: $("#metricUpload"),
  ocr: $("#metricOcr"),
  firstToken: $("#metricFirstToken"),
  llm: $("#metricLlm"),
  total: $("#metricTotal"),
};

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("toast--show");
  window.setTimeout(() => toast.classList.remove("toast--show"), 2400);
}

function setStatus(message) {
  $("#status").textContent = message;
}

function setResult(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  state.lastText = text;
  $("#result").textContent = text || "{}";
}

function normalizeName(value) {
  return String(value || "").toUpperCase().replace(/[\s:：,，。;；()（）\-_/]/g, "");
}

function extractAssetMatch(value) {
  if (!value || typeof value !== "object") return null;
  if (value.asset_matching) return value.asset_matching;
  if (value.ticket_record?.asset_matching) return value.ticket_record.asset_matching;
  if (Array.isArray(value.camera_matches)) return value;
  return null;
}

function displayField(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join("；");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value || "").trim();
}

function extractWorkArea(value) {
  const text = displayField(value);
  return text ? text.split(/[：:]/, 1)[0].trim() : "";
}

function extractWorkLocation(data) {
  if (!data || typeof data !== "object") return "";
  const taskGroups = [data.work_tasks, data["工作任务"]];
  const locations = taskGroups
    .flatMap((tasks) => Array.isArray(tasks) ? tasks : (tasks ? [tasks] : []))
    .map((task) => extractWorkArea(
      task?.location_and_equipment
        || task?.work_location
        || task?.["工作地点或地段"]
        || task?.["工作地点或设备"]
        || task?.["工作地点及设备双重名称"],
    ))
    .filter(Boolean);
  if (locations.length) return [...new Set(locations)].join("；");
  return displayField(data.work_location || data["工作地点或地段"] || data["工作地点"]);
}

function renderAssetMatches(value) {
  const panel = $("#assetPanel");
  const list = $("#cameraMatchList");
  const match = extractAssetMatch(value);
  if (!match) {
    state.assetResult = null;
    panel.hidden = true;
    list.innerHTML = "";
    $("#recognizedWorkLocation").textContent = "--";
    $("#matchedCameraIps").textContent = "--";
    return;
  }

  const ticketNo = match.ticket_no || value?.ticket_no || value?.ticket_id || "";
  const cameras = Array.isArray(match.camera_matches) ? match.camera_matches : [];
  const equipment = Array.isArray(match.equipment_matches) ? match.equipment_matches : [];
  state.assetResult = { ticketNo, match, cameras };
  panel.hidden = false;
  const workLocation = displayField(match.work_location)
    || extractWorkLocation(value?.structured_data)
    || extractWorkLocation(value?.ticket_record?.structured_data);
  const cameraIps = [...new Set(cameras.map((camera) => camera.ip_address).filter(Boolean))];
  $("#recognizedWorkLocation").textContent = workLocation || "未识别到工作地点";
  $("#matchedCameraIps").textContent = cameraIps.length
    ? cameraIps.join("、")
    : "匹配结果中尚未填写IP";
  $("#assetMatchSummary").textContent = match.status === "database_unavailable"
    ? "数据库连接失败"
    : `设备 ${equipment.length} 条 · 摄像头候选 ${cameras.length} 个`;
  $("#assetMessage").textContent = match.message
    || (cameras.length
      ? "先核对候选摄像头；自动匹配项已默认勾选。"
      : "没有匹配到摄像头，请检查台账、站点名称和工作地点。 ");
  list.innerHTML = "";

  cameras.forEach((camera) => {
    const row = document.createElement("article");
    row.className = "camera-match";
    row.dataset.cameraId = camera.camera_id || "";
    row.dataset.stationName = camera.station_name || match.station_name || "";
    row.dataset.decision = camera.decision || "candidate";

    const identity = document.createElement("label");
    identity.className = "camera-match__identity";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "camera-match__check";
    checkbox.checked = Boolean(camera.confirmed) || camera.decision === "auto_matched";
    const identityText = document.createElement("span");
    const identityTitle = document.createElement("strong");
    identityTitle.textContent = `${camera.camera_id || "未编号"} · ${camera.ip_address || "IP未填写"} · ${Math.round(Number(camera.confidence || 0) * 100)}%`;
    const identityMeta = document.createElement("small");
    identityMeta.textContent = camera.decision === "auto_matched" ? "自动匹配" : "需要人工确认";
    identityText.append(identityTitle, identityMeta);
    identity.append(checkbox, identityText);

    const detail = document.createElement("div");
    detail.className = "camera-match__detail";
    const location = document.createElement("strong");
    location.textContent = `安装位置：${camera.install_location || "未填写"}`;
    const reasons = document.createElement("small");
    reasons.textContent = Array.isArray(camera.reasons) && camera.reasons.length
      ? camera.reasons.join("；")
      : `站点：${camera.station_name || match.station_name || "未知"}`;
    const monitorArea = document.createElement("small");
    monitorArea.textContent = `监控区域：${camera.monitor_area || "未填写"}`;
    detail.append(location, monitorArea, reasons);

    const select = document.createElement("select");
    select.className = "camera-match__stream";
    select.dataset.currentStreamId = camera.stream_config_id || "";
    const placeholder = document.createElement("option");
    placeholder.value = camera.stream_config_id ? String(camera.stream_config_id) : "";
    placeholder.textContent = camera.stream_config_id
      ? `当前绑定：视频流 #${camera.stream_config_id}`
      : camera.ip_address
        ? "确认后根据IP自动创建视频流"
        : "IP未填写，无法创建视频流";
    select.appendChild(placeholder);

    row.append(identity, detail, select);
    list.appendChild(row);
  });
}

function integrationToken() {
  return $("#taskToken").value.trim() || $("#catalogToken").value.trim();
}

async function responseJson(resp, fallback) {
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : JSON.stringify(data.detail || data || fallback);
    throw new Error(detail || fallback);
  }
  return data;
}

async function loadStreamOptionsForMatches() {
  const token = integrationToken();
  if (!token) {
    showToast("请输入集成令牌");
    return;
  }
  const button = $("#loadStreamsBtn");
  button.disabled = true;
  try {
    const resp = await fetch("/api/v1/stream-options", {
      headers: { "X-Integration-Token": token },
    });
    const data = await responseJson(resp, "加载视频流失败");
    state.streamOptions = Array.isArray(data.streams) ? data.streams : [];

    $$(".camera-match").forEach((row) => {
      const select = row.querySelector(".camera-match__stream");
      const currentId = String(select.dataset.currentStreamId || "");
      const cameraStation = normalizeName(row.dataset.stationName);
      select.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "不绑定视频流";
      select.appendChild(empty);
      let sameStationCount = 0;
      state.streamOptions.forEach((stream) => {
        const option = document.createElement("option");
        option.value = String(stream.stream_config_id);
        const sameStation = cameraStation === normalizeName(stream.station_name);
        if (sameStation) sameStationCount += 1;
        option.disabled = !sameStation && option.value !== currentId;
        option.textContent = `${stream.station_name} / ${stream.stream_name} (#${stream.stream_config_id})${sameStation ? "" : " - 站点不一致"}`;
        option.selected = option.value === currentId;
        select.appendChild(option);
      });
      if (!sameStationCount && !currentId) {
        empty.textContent = "无同站点视频流，请先在智能安监中新增";
      }
    });
    $("#assetMessage").textContent = `已加载 ${state.streamOptions.length} 条视频流；只能选择与摄像头同站点的流。`;
  } catch (error) {
    $("#assetMessage").textContent = error instanceof Error ? error.message : String(error);
  } finally {
    button.disabled = false;
  }
}

async function confirmMatchedCameras() {
  const token = integrationToken();
  const ticketNo = state.assetResult?.ticketNo;
  if (!token) {
    showToast("请输入集成令牌");
    return;
  }
  if (!ticketNo) {
    showToast("当前识别结果没有工作票编号");
    return;
  }
  const selectedRows = $$(".camera-match").filter(
    (row) => row.querySelector(".camera-match__check")?.checked,
  );
  if (!selectedRows.length) {
    showToast("请至少勾选一个摄像头");
    return;
  }

  const button = $("#confirmCamerasBtn");
  button.disabled = true;
  try {
    const bindings = selectedRows
      .map((row) => ({
        camera_id: row.dataset.cameraId,
        stream_config_id: Number(row.querySelector(".camera-match__stream")?.value || 0) || null,
      }))
      .filter((binding) => binding.stream_config_id !== null);
    if (bindings.length) {
      const bindResp = await fetch("/api/v1/cameras/bind-streams", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Integration-Token": token,
        },
        body: JSON.stringify({ bindings, allow_station_mismatch: false }),
      });
      await responseJson(bindResp, "摄像头与视频流绑定失败");
    }

    const cameraIds = selectedRows.map((row) => row.dataset.cameraId);
    const resp = await fetch(
      `/api/v1/tickets/${encodeURIComponent(ticketNo)}/confirm-cameras`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Integration-Token": token,
        },
        body: JSON.stringify({ camera_ids: cameraIds }),
      },
    );
    const data = await responseJson(resp, "生成AI检测任务失败");
    const task = data.detection_task || data;
    $("#assetMessage").textContent = `任务 #${task.task_id}：${task.message}`;
    const runnable = task.status === "active" || task.status === "scheduled";
    showToast(
      runnable
        ? "AI检测任务已就绪"
        : task.status === "expired"
          ? "历史任务已保存"
          : "任务已保存，仍需绑定视频流",
    );
  } catch (error) {
    $("#assetMessage").textContent = error instanceof Error ? error.message : String(error);
    showToast("生成AI检测任务失败");
  } finally {
    button.disabled = false;
  }
}

async function cancelCurrentDetectionTask() {
  const token = integrationToken();
  const ticketNo = state.assetResult?.ticketNo;
  if (!token || !ticketNo) {
    showToast("需要工作票编号和集成令牌");
    return;
  }
  try {
    const resp = await fetch(
      `/api/v1/tickets/${encodeURIComponent(ticketNo)}/cancel-detection-task`,
      {
        method: "POST",
        headers: { "X-Integration-Token": token },
      },
    );
    const data = await responseJson(resp, "取消任务失败");
    $("#assetMessage").textContent = data.detection_task?.message || "任务已取消";
    showToast("AI检测任务已取消");
  } catch (error) {
    $("#assetMessage").textContent = error instanceof Error ? error.message : String(error);
  }
}

function setRunBadge(text, tone = "idle") {
  const badge = $("#runBadge");
  badge.textContent = text;
  badge.dataset.tone = tone;
}

function formatMs(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const ms = Number(value);
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)} s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(1);
  return `${minutes}m ${seconds}s`;
}

function formatTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatFileSize(bytes) {
  const mb = Number(bytes || 0) / 1024 / 1024;
  if (mb < 0.01) return `${Math.max(1, Math.round(Number(bytes || 0) / 1024))} KB`;
  return `${mb.toFixed(2)} MB`;
}

function resetRun(modeLabel, mode) {
  state.timeline.clear();
  state.runClock = {
    mode,
    startedAt: performance.now(),
    firstEventAt: null,
    ocrDoneAt: null,
    llmStartedAt: null,
    firstTokenAt: null,
    completedAt: null,
  };
  $("#metricUploadLabel").textContent = "文件接收";
  $("#metricOcrLabel").textContent = mode === "vision" ? "图片编码" : "OCR";
  $("#metricFirstTokenLabel").textContent = "首字返回";
  $("#metricLlmLabel").textContent = mode === "vision" ? "模型生成" : "模型生成";
  Object.values(metricEls).forEach((el) => {
    el.textContent = "--";
  });
  $$(".metric").forEach((el) => {
    el.dataset.state = "idle";
  });
  $("#timeline").innerHTML = "";
  $("#endTime").textContent = "结束时间 --";
  setRunBadge(modeLabel, "running");
  setStatus("请求已提交，等待服务端返回步骤事件");
  setResult("");
  renderAssetMatches(null);
}

function setMetric(name, value, stateName = "done") {
  const el = metricEls[name];
  if (!el) return;
  el.textContent = formatMs(value);
  const box = document.querySelector(`[data-metric="${name}"]`);
  if (box) box.dataset.state = stateName;
}

function setMetricText(name, text, stateName = "idle") {
  const el = metricEls[name];
  if (!el) return;
  el.textContent = text;
  const box = document.querySelector(`[data-metric="${name}"]`);
  if (box) box.dataset.state = stateName;
}

function elapsedSinceRunStart(at = performance.now()) {
  if (!state.runClock) return null;
  return at - state.runClock.startedAt;
}

function ensureFirstEventTiming(now = performance.now()) {
  if (!state.runClock || state.runClock.firstEventAt) return;
  state.runClock.firstEventAt = now;
}

function markOcrDone(now = performance.now()) {
  if (!state.runClock || state.runClock.ocrDoneAt) return;
  state.runClock.ocrDoneAt = now;
  setMetric("ocr", elapsedSinceRunStart(now));
  upsertTimeline("ocr_client", {
    label: "OCR 完成",
    state: "done",
    detail: `前端计时 ${formatMs(elapsedSinceRunStart(now))}`,
  });
}

function markLlmStarted(now = performance.now()) {
  if (!state.runClock || state.runClock.llmStartedAt) return;
  state.runClock.llmStartedAt = now;
  document.querySelector('[data-metric="llm"]').dataset.state = "running";
}

function markFirstToken(now = performance.now()) {
  if (!state.runClock || state.runClock.firstTokenAt) return;
  state.runClock.firstTokenAt = now;
  const base = state.runClock.llmStartedAt || state.runClock.ocrDoneAt || state.runClock.firstEventAt || state.runClock.startedAt;
  setMetric("firstToken", now - base);
  upsertTimeline("first_token_client", {
    label: "首字返回",
    state: "done",
    detail: `前端计时 ${formatMs(now - base)}，累计 ${formatMs(elapsedSinceRunStart(now))}`,
  });
}

function finishClientTiming(now = performance.now()) {
  if (!state.runClock) return;
  state.runClock.completedAt = now;

  if (state.runClock.mode === "vision") {
    if (metricEls.ocr.textContent === "--") {
      setMetricText("ocr", "未返回", "idle");
    }
  } else if (!state.runClock.ocrDoneAt) {
    markOcrDone(state.runClock.llmStartedAt || state.runClock.firstTokenAt || now);
  }

  if (!state.runClock.firstTokenAt && state.runClock.llmStartedAt) {
    markFirstToken(now);
  }

  const llmBase = state.runClock.llmStartedAt || state.runClock.firstTokenAt || state.runClock.ocrDoneAt || state.runClock.firstEventAt || state.runClock.startedAt;
  setMetric("llm", now - llmBase);
  setMetric("total", elapsedSinceRunStart(now));
  $("#endTime").textContent = `结束时间 ${formatTime(new Date().toISOString())}`;
}

function applyClientTimingFromEvent(msg) {
  const now = performance.now();
  ensureFirstEventTiming(now);

  if (
    msg.type === "ocr_complete" ||
    (msg.type === "step_complete" && (msg.step === "ocr" || msg.step === "image_encode"))
  ) {
    markOcrDone(now);
  }

  if (
    msg.type === "step_start" &&
    (msg.step === "llm_stream" || msg.step === "vision_stream" || msg.step === "llm_wait")
  ) {
    markLlmStarted(now);
  }

  if (msg.type === "first_token" || msg.type === "llm_chunk" || msg.type === "chunk") {
    markLlmStarted(state.runClock?.llmStartedAt || state.runClock?.firstEventAt || state.runClock?.startedAt || now);
    markFirstToken(now);
  }

  if (msg.type === "complete" || msg.type === "error") {
    finishClientTiming(now);
  }
}

function upsertTimeline(step, patch) {
  const current = state.timeline.get(step) || {
    step,
    label: step,
    state: "pending",
    detail: "",
  };
  state.timeline.set(step, { ...current, ...patch });
  renderTimeline();
}

function renderTimeline() {
  const timeline = $("#timeline");
  timeline.innerHTML = "";
  for (const item of state.timeline.values()) {
    const li = document.createElement("li");
    li.className = `timeline-item timeline-item--${item.state}`;
    li.innerHTML = `
      <span class="timeline-dot"></span>
      <div>
        <strong>${item.label}</strong>
        <small>${item.detail || ""}</small>
      </div>
    `;
    timeline.appendChild(li);
  }
}

function applyTimingSummary(timing = {}) {
  const has = (key) => Object.prototype.hasOwnProperty.call(timing, key);
  if (has("upload_ms")) setMetric("upload", timing.upload_ms);
  if (has("ocr_ms")) setMetric("ocr", timing.ocr_ms);
  if (has("image_encode_ms")) setMetric("ocr", timing.image_encode_ms);
  if (has("llm_first_token_ms")) {
    setMetric("firstToken", timing.llm_first_token_ms);
  }
  if (has("llm_stream_ms")) setMetric("llm", timing.llm_stream_ms);
  if (has("total_ms")) setMetric("total", timing.total_ms);
  if (timing.request_ended_at) {
    $("#endTime").textContent = `结束时间 ${formatTime(timing.request_ended_at)}`;
  }
}

function handleTimingEvent(msg) {
  if (msg.type === "step_start") {
    upsertTimeline(msg.step, {
      label: msg.label || msg.step,
      state: "running",
      detail: `开始于 ${formatMs(msg.total_elapsed_ms)}`,
    });
    if (msg.step === "ocr" || msg.step === "image_encode") {
      document.querySelector('[data-metric="ocr"]').dataset.state = "running";
    }
    if (msg.step === "llm_stream" || msg.step === "vision_stream" || msg.step === "llm_wait") {
      document.querySelector('[data-metric="llm"]').dataset.state = "running";
      setStatus("已发送给大模型，等待流式输出");
    }
    return;
  }

  if (msg.type === "step_complete") {
    upsertTimeline(msg.step, {
      label: msg.label || msg.step,
      state: "done",
      detail: `耗时 ${formatMs(msg.elapsed_ms)}，累计 ${formatMs(msg.total_elapsed_ms)}`,
    });
    if (msg.step === "upload") setMetric("upload", msg.elapsed_ms);
    if (msg.step === "ocr") {
      setMetric("ocr", msg.elapsed_ms);
      setStatus("OCR 已完成，正在准备大模型流式输出");
    }
    if (msg.step === "image_encode") {
      setMetric("ocr", msg.elapsed_ms);
      setStatus("图片编码完成，正在等待大模型首字返回");
    }
    if (msg.step === "llm_wait") {
      setMetric("firstToken", msg.elapsed_ms);
      setStatus("大模型已返回首字，正在流式输出");
    }
    if (msg.step === "llm_stream" || msg.step === "vision_stream") {
      setMetric("llm", msg.elapsed_ms);
      if (msg.first_token_ms !== null && msg.first_token_ms !== undefined) {
        setMetric("firstToken", msg.first_token_ms);
      }
      setMetric("total", msg.total_elapsed_ms);
    }
    return;
  }

  if (msg.type === "first_token") {
    setMetric("firstToken", msg.elapsed_ms);
    upsertTimeline(`${msg.step}_first_token`, {
      label: msg.label || "首字返回",
      state: "done",
      detail: `耗时 ${formatMs(msg.elapsed_ms)}，累计 ${formatMs(msg.total_elapsed_ms)}`,
    });
    setStatus("大模型已开始流式返回");
  }
}

function parseSSELine(line) {
  if (!line.startsWith("data:")) return null;
  const jsonStr = line.slice(5).trim();
  if (!jsonStr) return null;
  try {
    return JSON.parse(jsonStr);
  } catch {
    return null;
  }
}

async function streamFetch(url, form, onEvent) {
  const resp = await fetch(url, { method: "POST", body: form });
  if (!resp.ok) {
    const data = await resp.json().catch(() => null);
    throw new Error(data?.detail || resp.statusText || "流式请求失败");
  }
  if (!resp.body) {
    throw new Error("当前浏览器不支持流式响应读取");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const msg = parseSSELine(line);
      if (msg) onEvent(msg);
    }
  }

  buffer += decoder.decode();
  for (const line of buffer.split("\n")) {
    const msg = parseSSELine(line);
    if (msg) onEvent(msg);
  }
}

function bindTabs() {
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      state.activeMode = target;
      $$(".tab").forEach((item) => item.classList.toggle("tab--active", item === tab));
      $$(".mode").forEach((mode) => {
        mode.classList.toggle("mode--active", mode.id === `mode-${target}`);
      });
    });
  });
}

function fileExtension(filename) {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : "";
}

function bindDropzone(dropzone, input, nameEl, key, allowedExtensions, emptyLabel) {
  const updateFiles = (fileList) => {
    const selected = Array.from(fileList || []);
    const valid = selected.filter((file) => allowedExtensions.has(fileExtension(file.name)));
    const rejectedCount = selected.length - valid.length;
    const files = valid.slice(0, MAX_BATCH_FILES);

    state[key] = files;
    if (files.length === 0) {
      nameEl.textContent = emptyLabel;
      delete dropzone.dataset.ready;
    } else if (files.length === 1) {
      nameEl.textContent = `${files[0].name} · ${formatFileSize(files[0].size)}`;
      dropzone.dataset.ready = "true";
    } else {
      const totalBytes = files.reduce((total, file) => total + file.size, 0);
      nameEl.textContent = `已选择 ${files.length} 个文件 · 共 ${formatFileSize(totalBytes)}`;
      dropzone.dataset.ready = "true";
    }

    if (valid.length > MAX_BATCH_FILES) {
      showToast(`单次最多处理 ${MAX_BATCH_FILES} 个文件，已保留前 ${MAX_BATCH_FILES} 个`);
    } else if (rejectedCount > 0) {
      showToast(`已忽略 ${rejectedCount} 个不支持的文件`);
    }
  };

  input.addEventListener("change", () => updateFiles(input.files));

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("dropzone--drag");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dropzone--drag");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    updateFiles(event.dataTransfer.files);
  });
}

function batchStatusLabel(status) {
  return {
    queued: "等待中",
    running: "处理中",
    done: "已完成",
    error: "失败",
  }[status] || status;
}

function showBatchJob(job) {
  state.activeJobId = job.id;
  renderBatchJobs();

  if (job.status === "done") {
    setResult(job.result);
    renderAssetMatches(job.result);
  } else if (job.status === "error") {
    setResult({ file: job.file.name, error: job.error });
    renderAssetMatches(null);
  } else if (job.partialOutput) {
    setResult(job.partialOutput);
    renderAssetMatches(null);
  } else {
    setResult({ file: job.file.name, status: batchStatusLabel(job.status) });
    renderAssetMatches(null);
  }
}

function renderBatchJobs() {
  const panel = $("#batchPanel");
  const list = $("#batchList");
  const jobs = state.batchJobs;
  panel.hidden = jobs.length === 0;
  list.innerHTML = "";

  const doneCount = jobs.filter((job) => job.status === "done").length;
  const errorCount = jobs.filter((job) => job.status === "error").length;
  const runningCount = jobs.filter((job) => job.status === "running").length;
  const pendingCount = jobs.length - doneCount - errorCount - runningCount;
  const summary = [`共 ${jobs.length} 个`, `完成 ${doneCount}`];
  if (runningCount) summary.push(`处理中 ${runningCount}`);
  if (pendingCount) summary.push(`等待 ${pendingCount}`);
  if (errorCount) summary.push(`失败 ${errorCount}`);
  $("#batchSummary").textContent = summary.join(" · ");

  jobs.forEach((job) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "batch-item";
    item.dataset.jobId = job.id;
    item.dataset.status = job.status;
    item.classList.toggle("batch-item--active", job.id === state.activeJobId);
    item.setAttribute("aria-pressed", job.id === state.activeJobId ? "true" : "false");
    item.title = job.file.name;

    const meta = document.createElement("span");
    meta.className = "batch-item__meta";
    const name = document.createElement("strong");
    name.textContent = job.file.name;
    const detail = document.createElement("small");
    detail.textContent = `${job.index + 1}/${jobs.length} · ${formatFileSize(job.file.size)}`;
    meta.append(name, detail);

    const status = document.createElement("span");
    status.className = "batch-item__status";
    status.textContent = batchStatusLabel(job.status);
    item.append(meta, status);
    list.appendChild(item);
  });
}

function setBatchControlsDisabled(disabled) {
  state.isRunning = disabled;
  $("#structureStreamBtn").disabled = disabled;
  $("#visionStreamBtn").disabled = disabled;
  $("#structureFile").disabled = disabled;
  $("#visionFile").disabled = disabled;
}

async function processStructureJob(job) {
  const form = new FormData();
  form.append("file", job.file);

  let finalResult = null;
  let receivedComplete = false;
  job.partialOutput = "";

  await streamFetch("/api/recognize-structure-stream", form, (msg) => {
    applyClientTimingFromEvent(msg);
    handleTimingEvent(msg);
    if (msg.timing) job.timing = msg.timing;
    if (msg.type === "ocr_complete") {
      applyTimingSummary(msg.timing);
    }
    if (msg.type === "llm_chunk") {
      job.partialOutput += msg.data;
      if (state.activeJobId === job.id) setResult(job.partialOutput);
    }
    if (msg.type === "complete") {
      receivedComplete = true;
      applyTimingSummary(msg.timing);
      finalResult = msg.ticket_record ?? msg.parsed_json ?? msg.llm_output ?? job.partialOutput;
      if (state.activeJobId === job.id) {
        setResult(finalResult);
        renderAssetMatches(finalResult);
      }
    }
    if (msg.type === "error") {
      applyTimingSummary(msg.timing);
      throw new Error(msg.error || "结构化识别失败");
    }
  });

  if (!receivedComplete) {
    throw new Error("连接已结束，但没有收到完整识别结果");
  }
  return finalResult;
}

async function processVisionJob(job, prompt) {
  const form = new FormData();
  form.append("file", job.file);
  form.append("prompt", prompt);

  let finalResult = null;
  let receivedComplete = false;
  job.partialOutput = "";

  await streamFetch("/api/direct-vision-stream", form, (msg) => {
    applyClientTimingFromEvent(msg);
    handleTimingEvent(msg);
    if (msg.timing) job.timing = msg.timing;
    if (msg.type === "chunk") {
      job.partialOutput += msg.data;
      if (state.activeJobId === job.id) setResult(job.partialOutput);
    }
    if (msg.type === "complete") {
      receivedComplete = true;
      applyTimingSummary(msg.timing);
      finalResult = msg.llm_output || job.partialOutput || "模型没有返回内容";
      if (state.activeJobId === job.id) setResult(finalResult);
    }
    if (msg.type === "error") {
      applyTimingSummary(msg.timing);
      throw new Error(msg.error || "图片识别失败");
    }
  });

  if (!receivedComplete) {
    throw new Error("连接已结束，但没有收到完整识别结果");
  }
  return finalResult;
}

async function runBatch(mode) {
  if (state.isRunning) return;
  const files = mode === "structure" ? state.structureFiles : state.visionFiles;
  if (files.length === 0) {
    showToast(mode === "structure" ? "请先选择工作票文件" : "请先选择图片");
    return;
  }

  const batchId = Date.now().toString(36);
  state.batchJobs = files.map((file, index) => ({
    id: `${batchId}-${index}`,
    index,
    mode,
    file,
    status: "queued",
    result: null,
    error: null,
    partialOutput: "",
    timing: null,
  }));
  state.activeJobId = state.batchJobs[0]?.id || null;
  renderBatchJobs();
  setBatchControlsDisabled(true);

  const prompt = mode === "vision" ? $("#visionPrompt").value.trim() : "";
  let successCount = 0;

  try {
    for (const job of state.batchJobs) {
      job.status = "running";
      state.activeJobId = job.id;
      renderBatchJobs();
      resetRun(`处理中 ${job.index + 1}/${state.batchJobs.length}`, mode);
      setStatus(`正在处理：${job.file.name}`);

      try {
        job.result = mode === "structure"
          ? await processStructureJob(job)
          : await processVisionJob(job, prompt);
        job.status = "done";
        successCount += 1;
      } catch (error) {
        job.status = "error";
        job.error = error instanceof Error ? error.message : String(error);
        setResult({ file: job.file.name, error: job.error });
      }
      renderBatchJobs();
    }
  } finally {
    setBatchControlsDisabled(false);
  }

  const failedCount = state.batchJobs.length - successCount;
  if (failedCount === 0) {
    setRunBadge(`${successCount}/${state.batchJobs.length} 已完成`, "done");
    setStatus(`批量处理完成，共 ${successCount} 个文件`);
  } else {
    setRunBadge(`${successCount}/${state.batchJobs.length} 已完成`, "error");
    setStatus(`批量处理结束：成功 ${successCount} 个，失败 ${failedCount} 个`);
  }
}

async function runStructureStream() {
  await runBatch("structure");
}

async function runVisionStream() {
  await runBatch("vision");
}

function bindActions() {
  $("#structureStreamBtn").addEventListener("click", runStructureStream);
  $("#visionStreamBtn").addEventListener("click", runVisionStream);
  $("#catalogImportBtn").addEventListener("click", importCatalogs);
  $("#loadStreamsBtn").addEventListener("click", loadStreamOptionsForMatches);
  $("#confirmCamerasBtn").addEventListener("click", confirmMatchedCameras);
  $("#cancelTaskBtn").addEventListener("click", cancelCurrentDetectionTask);
  $("#catalogToken").addEventListener("input", (event) => {
    $("#taskToken").value = event.target.value;
  });
  $("#taskToken").addEventListener("input", (event) => {
    $("#catalogToken").value = event.target.value;
  });
  $("#batchList").addEventListener("click", (event) => {
    const item = event.target.closest("[data-job-id]");
    if (!item) return;
    const job = state.batchJobs.find((candidate) => candidate.id === item.dataset.jobId);
    if (job) showBatchJob(job);
  });
  $("#copyBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(state.lastText);
      showToast("结果已复制");
    } catch {
      showToast("复制失败，请手动选择结果");
    }
  });
}

async function refreshCatalogStatus() {
  try {
    const resp = await fetch("/api/catalog/status");
    const data = await resp.json();
    $("#catalogStatus").textContent = data.ready
      ? `目录已就绪：设备 ${data.equipment_count} 条，摄像头 ${data.camera_count} 条${data.imported_at ? `；导入时间 ${formatTime(data.imported_at)}` : ""}`
      : data.message || "尚未导入台账";
  } catch {
    $("#catalogStatus").textContent = "无法读取台账状态";
  }
}

async function importCatalogs() {
  const camera = $("#cameraCatalogFile").files[0];
  const equipment = $("#equipmentCatalogFile").files[0];
  const token = $("#catalogToken").value.trim();
  if (!camera || !equipment) {
    showToast("请选择摄像头清单和设备清单");
    return;
  }
  if (!token) {
    showToast("请输入集成令牌");
    return;
  }
  const button = $("#catalogImportBtn");
  button.disabled = true;
  $("#catalogStatus").textContent = "正在导入并建立目录…";
  const form = new FormData();
  form.append("camera_file", camera);
  form.append("equipment_file", equipment);
  try {
    const resp = await fetch("/api/catalog/import", {
      method: "POST",
      headers: { "X-Integration-Token": token },
      body: form,
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "导入失败");
    $("#catalogStatus").textContent = `导入成功：设备 ${data.equipment_count} 条，摄像头 ${data.camera_count} 条`;
    showToast("台账导入成功，后续识别将自动匹配");
  } catch (error) {
    $("#catalogStatus").textContent = error instanceof Error ? error.message : String(error);
    showToast("台账导入失败");
  } finally {
    button.disabled = false;
  }
}

async function checkHealth() {
  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error("服务异常");
    $("#healthDot").dataset.state = data.llm_configured ? "ok" : "warn";
    $("#healthText").textContent = data.llm_configured ? "服务正常" : "未配置 LLM";
    if (!data.llm_configured) {
      setStatus("服务已启动，但还没有配置 LLM_API_KEY");
    }
  } catch {
    $("#healthDot").dataset.state = "error";
    $("#healthText").textContent = "服务不可用";
    setStatus("正在等待后端服务");
  }
}

bindTabs();
bindDropzone(
  $("#structureDrop"),
  $("#structureFile"),
  $("#structureName"),
  "structureFiles",
  STRUCTURE_EXTENSIONS,
  "JPG / PNG / BMP / WEBP / PDF，最多 20 个",
);
bindDropzone(
  $("#visionDrop"),
  $("#visionFile"),
  $("#visionName"),
  "visionFiles",
  IMAGE_EXTENSIONS,
  "JPG / PNG / BMP / WEBP，最多 20 个",
);
bindActions();
checkHealth();
refreshCatalogStatus();
