"use strict";
// Bridge to Python, formula rendering, icons and dialogs shared by both pages.
// Recognized text is untrusted: it only ever reaches the DOM through
// textContent or MathJax, never innerHTML.

const $ = (id) => document.getElementById(id);
const LOGO_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M16.6 4.3c-1.9-1-3.7-.2-4.1 2.2l-1.8 11c-.4 2.4-2.2 3.2-4.1 2.2"/></svg>';

function iconSvg(name) {
  return '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + ICONS[name] + "</svg>";
}

function decorate(root = document) {
  root.querySelectorAll("[data-logo]").forEach((el) => { el.innerHTML = LOGO_SVG; });
  root.querySelectorAll("[data-icon]").forEach((el) => {
    el.insertAdjacentHTML("afterbegin", iconSvg(el.dataset.icon));
  });
}

// ---- bridge ----------------------------------------------------------------

let bridge = null;
const listeners = {};

function on(name, handler) { (listeners[name] = listeners[name] || []).push(handler); }

function api(name, ...args) {
  return new Promise((resolve, reject) => {
    bridge.invoke(name, JSON.stringify(args), (reply) => {
      const r = JSON.parse(reply);
      if (r.ok) resolve(r.result); else reject(new Error(r.error));
    });
  });
}

function connect(ready) {
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    bridge.pushed.connect((payload) => {
      const { name, data } = JSON.parse(payload);
      (listeners[name] || []).forEach((handler) => handler(data));
    });
    loadMathJax();
    ready();
  });
}

function setSeg(group, value) {
  group.querySelectorAll("button").forEach((b) => {
    const on = b.dataset.value === String(value);
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on);
  });
}

function bindSeg(group, handler) {
  group.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button) { setSeg(group, button.dataset.value); handler(button.dataset.value); }
  });
}

// ---- MathJax ---------------------------------------------------------------

let mathjaxState = "none";   // none | loading | ready
let typesetQueue = Promise.resolve();
let pendingRender = null;

function loadMathJax() {
  if (mathjaxState !== "none") return;
  api("mathjax_url").then((url) => {
    if (!url || mathjaxState !== "none") return;
    mathjaxState = "loading";
    window.MathJax = {
      tex: { inlineMath: [["$", "$"], ["\\(", "\\)"]],
             displayMath: [["$$", "$$"], ["\\[", "\\]"]], processEscapes: true },
      svg: { fontCache: "local" },
      options: { enableMenu: false },
      startup: {
        typeset: false,
        ready() {
          MathJax.startup.defaultReady();
          mathjaxState = "ready";
          if (pendingRender) { const p = pendingRender; pendingRender = null; renderMath(p.el, p.content, p.isMath); }
        },
      },
    };
    const script = document.createElement("script");
    script.src = url;
    document.head.appendChild(script);
  }).catch(() => {});
}
on("mathjax", loadMathJax);

// Shows the source immediately; MathJax replaces it once it has loaded.
function renderMath(el, content, isMath) {
  el.textContent = isMath ? `$$${content}$$` : content;
  if (mathjaxState !== "ready") { pendingRender = { el, content, isMath }; return; }
  pendingRender = null;
  typesetQueue = typesetQueue.then(() => {
    MathJax.typesetClear([el]);
    return MathJax.typesetPromise([el]);
  }).catch((error) => {
    console.warn("typeset failed", error && error.message);
    el.textContent = content;
  });
}

// ---- dialogs ---------------------------------------------------------------

function dialog({ title, body, ok = "确定", cancel = null }) {
  return new Promise((resolve) => {
    const scrim = document.createElement("div");
    scrim.className = "dialog-scrim";
    const box = document.createElement("div");
    box.className = "dialog";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    const heading = document.createElement("div");
    heading.className = "dialog-title";
    heading.textContent = title;
    const text = document.createElement("div");
    text.className = "dialog-body";
    text.textContent = body;
    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    const finish = (value) => { scrim.remove(); resolve(value); };
    if (cancel) {
      const no = document.createElement("button");
      no.className = "quiet";
      no.textContent = cancel;
      no.onclick = () => finish(false);
      actions.appendChild(no);
    }
    const yes = document.createElement("button");
    yes.className = "primary";
    yes.textContent = ok;
    yes.onclick = () => finish(true);
    actions.appendChild(yes);
    box.append(heading, text, actions);
    scrim.appendChild(box);
    document.body.appendChild(scrim);
    yes.focus();
  });
}

const showError = (error) => dialog({ title: "操作没有完成", body: error.message || String(error) });
on("notice", (data) => dialog({ title: data.title, body: data.message }));

decorate();
