"use strict";
// Renders FloatModel.snapshot(); every decision about what is allowed is made
// in Python (result_format.py).

const stage = $("stage"), code = $("code"), primary = $("primary");
const FORMAT_LABELS = { preview: "预览", latex: "LaTeX", markdown: "Markdown" };
let current = null;
let renderedPreview = null;
let sourceOpen = false;
let loadedSourceRev = -1;
let copiedTimer = 0;

function setMessage(text, withBar) {
  renderedPreview = null;
  stage.className = "stage message";
  stage.textContent = text;
  if (withBar) {
    const bar = document.createElement("div");
    bar.className = "loading-bar";
    bar.appendChild(document.createElement("span"));
    stage.appendChild(bar);
  }
}

function renderStage(s) {
  if (s.state === "empty") return setMessage("截取公式或文字\n识别结果会显示在这里");
  if (s.state === "loading") return setMessage("正在识别…", true);
  if (s.state === "error") return setMessage("原图已保留，可直接重试");
  if (!s.preview.content) return setMessage("此区域没有可识别的文字");
  const key = `${s.preview.is_math}:${s.preview.content}`;
  if (key === renderedPreview) return;
  renderedPreview = key;
  stage.className = s.preview.is_math ? "stage" : "stage prose";
  renderMath(stage, s.preview.content, s.preview.is_math);
}

function renderFormats(s) {
  const box = $("formats");
  box.textContent = "";
  s.formats.forEach((key) => {
    const button = document.createElement("button");
    button.textContent = FORMAT_LABELS[key];
    button.classList.toggle("on", key === s.format);
    button.setAttribute("aria-pressed", key === s.format);
    button.onclick = () => api("float_format", key).catch(showError);
    box.appendChild(button);
  });
  $("formatRow").hidden = s.formats.length === 0;
  const styles = $("latexStyles");
  styles.hidden = !s.formats.includes("latex");
  styles.querySelectorAll("button").forEach((b) => {
    const on = Number(b.dataset.style) === s.latex_style;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on);
  });
}

function renderSource(s) {
  const button = $("sourceBtn");
  button.disabled = !s.has_source;
  if (!s.has_source) sourceOpen = false;
  button.setAttribute("aria-pressed", sourceOpen);
  $("source").hidden = !sourceOpen;
  if (sourceOpen && loadedSourceRev !== s.source_rev) {
    loadedSourceRev = s.source_rev;
    api("float_source").then((url) => { $("sourceImg").src = url; }).catch(showError);
  }
}

function render(s) {
  // "Copied" belongs to the text it was said about, not to the next result.
  if (current && (current.state !== s.state || !samePreview(current, s))) {
    clearTimeout(copiedTimer);
    copiedTimer = 0;
  }
  current = s;
  renderStage(s);
  const showCode = s.state === "result" && s.format !== "preview";
  stage.hidden = showCode;
  code.hidden = !showCode;
  if (showCode) code.textContent = s.code;
  renderFormats(s);
  renderSource(s);
  const warning = $("warning");
  warning.hidden = !s.warning;
  warning.textContent = s.warning;
  warning.classList.toggle("bad", s.warning_is_error);
  if (!copiedTimer) primary.textContent = s.primary.label;
  primary.disabled = !s.primary.enabled;
  $("meta").textContent = s.meta;
  const recapture = $("recapture");
  recapture.style.visibility = s.can_recapture ? "visible" : "hidden";
  recapture.title = s.recapture_hint;
  const provider = $("provider");
  provider.innerHTML = iconSvg(s.provider.key === "llm" ? "sparkles" : "math-function");
  provider.appendChild(document.createTextNode(s.provider.label));
  provider.title = `下一次截图使用 ${s.provider.title}，点击切换`;
  provider.disabled = !s.provider.enabled;
  $("pdfLabel").textContent = s.task_count ? `PDF · ${s.task_count}` : "PDF";
}

function samePreview(a, b) {
  return JSON.stringify(a.preview) === JSON.stringify(b.preview);
}

function copyPrimary() {
  api("float_primary").then((reply) => {
    if (!reply.copied) return;
    clearTimeout(copiedTimer);
    primary.textContent = "已复制到剪贴板";
    copiedTimer = setTimeout(() => {
      copiedTimer = 0;
      if (current) primary.textContent = current.primary.label;
    }, 2400);
  }).catch(showError);
}

primary.onclick = copyPrimary;
$("recapture").onclick = () => api("float_recapture").catch(showError);
$("provider").onclick = () => api("float_toggle_provider").catch(showError);
$("sourceBtn").onclick = () => { sourceOpen = !sourceOpen; if (current) renderSource(current); };
$("latexStyles").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) api("float_latex_style", Number(button.dataset.style)).catch(showError);
});
document.querySelectorAll("[data-open]").forEach((b) => {
  b.onclick = () => api("open_tool", b.dataset.open).catch(showError);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !document.querySelector(".dialog-scrim")) api("float_hide");
  if (event.ctrlKey && event.shiftKey && event.code === "KeyC") {
    event.preventDefault();
    if (current && current.state === "result") copyPrimary();
  }
});

on("float", render);
connect(() => api("float_state").then(render).catch(showError));
