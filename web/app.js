const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  activeMode: "structure",
  structureFile: null,
  visionFile: null,
  lastText: "{}",
  timeline: new Map(),
  runClock: null,
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

function bindDropzone(dropzone, input, nameEl, key) {
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (!file) return;
    state[key] = file;
    nameEl.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    dropzone.dataset.ready = "true";
  });

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
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    state[key] = file;
    nameEl.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    dropzone.dataset.ready = "true";
  });
}

async function runStructureStream() {
  if (!state.structureFile) {
    showToast("请先上传工作票文件");
    return;
  }

  const btn = $("#structureStreamBtn");
  btn.disabled = true;
  resetRun("结构化识别中", "structure");

  const form = new FormData();
  form.append("file", state.structureFile);

  let accumulated = "";
  try {
    await streamFetch("/api/recognize-structure-stream", form, (msg) => {
      applyClientTimingFromEvent(msg);
      handleTimingEvent(msg);
      if (msg.type === "ocr_complete") {
        applyTimingSummary(msg.timing);
      }
      if (msg.type === "llm_chunk") {
        accumulated += msg.data;
        setResult(accumulated);
      }
      if (msg.type === "complete") {
        applyTimingSummary(msg.timing);
        setRunBadge("已完成", "done");
        setStatus("流式结构化识别完成");
        setResult(msg.parsed_json || msg.llm_output || accumulated);
      }
      if (msg.type === "error") {
        applyTimingSummary(msg.timing);
        throw new Error(msg.error || "结构化识别失败");
      }
    });
  } catch (error) {
    setRunBadge("失败", "error");
    setStatus("结构化识别失败");
    setResult({ error: error.message });
  } finally {
    btn.disabled = false;
  }
}

async function runVisionStream() {
  if (!state.visionFile) {
    showToast("请先上传图片");
    return;
  }

  const btn = $("#visionStreamBtn");
  btn.disabled = true;
  resetRun("图片识别中", "vision");

  const form = new FormData();
  form.append("file", state.visionFile);
  form.append("prompt", $("#visionPrompt").value.trim());

  let accumulated = "";
  try {
    await streamFetch("/api/direct-vision-stream", form, (msg) => {
      applyClientTimingFromEvent(msg);
      handleTimingEvent(msg);
      if (msg.type === "chunk") {
        accumulated += msg.data;
        setResult(accumulated);
      }
      if (msg.type === "complete") {
        applyTimingSummary(msg.timing);
        setRunBadge("已完成", "done");
        setStatus("流式图片识别完成");
        setResult(msg.llm_output || accumulated || "模型没有返回内容");
      }
      if (msg.type === "error") {
        applyTimingSummary(msg.timing);
        throw new Error(msg.error || "图片识别失败");
      }
    });
  } catch (error) {
    setRunBadge("失败", "error");
    setStatus("图片识别失败");
    setResult({ error: error.message });
  } finally {
    btn.disabled = false;
  }
}

function bindActions() {
  $("#structureStreamBtn").addEventListener("click", runStructureStream);
  $("#visionStreamBtn").addEventListener("click", runVisionStream);
  $("#copyBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(state.lastText);
      showToast("结果已复制");
    } catch {
      showToast("复制失败，请手动选择结果");
    }
  });
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
bindDropzone($("#structureDrop"), $("#structureFile"), $("#structureName"), "structureFile");
bindDropzone($("#visionDrop"), $("#visionFile"), $("#visionName"), "visionFile");
bindActions();
checkHealth();
