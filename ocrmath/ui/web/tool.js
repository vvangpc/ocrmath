"use strict";

function make(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function iconButton(iconName, label, onClick, showText = true) {
  const button = make("button", "quiet");
  button.innerHTML = iconSvg(iconName);
  if (showText) button.appendChild(document.createTextNode(label));
  else { button.title = label; button.setAttribute("aria-label", label); }
  button.addEventListener("click", (event) => { event.stopPropagation(); onClick(); });
  return button;
}

const money = (v) => `$${v < .1 ? v.toFixed(3) : v.toFixed(2)}`;
const number = (v) => Number(v || 0).toLocaleString("en-US");

function formatTime(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const clock = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return `今天 ${clock}`;
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${clock}`;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${clock}`;
}

// ---- navigation ------------------------------------------------------------

const loaders = {};
let activePage = "pdf";

function showPage(name) {
  activePage = name;
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `page-${name}`; });
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.classList.toggle("on", b.dataset.page === name);
  });
  if (loaders[name]) loaders[name]();
}

$("tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) showPage(button.dataset.page);
});
$("back").onclick = () => api("back_to_float").catch(showError);
on("page", showPage);

// ---- pdf -------------------------------------------------------------------

let pdfFile = null;
let pdfProvider = "mathpix";
let pdfBusy = false;

function renderPdfOptions() {
  $("drop").hidden = !!pdfFile;
  $("pdfOptions").hidden = !pdfFile;
  if (!pdfFile) return;
  $("pdfName").textContent = pdfFile.name;
  $("pdfPages").textContent = pdfFile.pages ? `${pdfFile.pages} 页` : "页数未知";
  setSeg($("pdfProvider"), pdfProvider);
  $("pdfFormats").hidden = pdfProvider === "llm";
  $("pdfStart").disabled = pdfBusy;
  updateEstimate();
}

function updateEstimate() {
  if (!pdfFile) return;
  api("pdf_estimate", pdfFile.path, pdfProvider, $("pdfRange").value).then((text) => {
    $("pdfEstimate").textContent = text;
    $("pdfError").textContent = "";
  }).catch((error) => {
    $("pdfEstimate").textContent = "";
    $("pdfError").textContent = error.message;
  });
}

function setPdfFile(file) {
  if (!file) return;
  pdfFile = file;
  $("pdfOut").value = file.out_dir;
  $("pdfRange").value = "";
  if (file.formats) {
    document.querySelectorAll("#pdfFormats input[value]").forEach((box) => {
      box.checked = file.formats.includes(box.value);
    });
  }
  if (file.rm_spaces !== null) $("pdfRmSpaces").checked = file.rm_spaces;
  renderPdfOptions();
}

function startPdf(confirmed = false) {
  const params = {
    path: pdfFile.path, provider: pdfProvider,
    page_ranges: $("pdfRange").value, out_dir: $("pdfOut").value,
    rm_spaces: $("pdfRmSpaces").checked,
    formats: [...document.querySelectorAll("#pdfFormats input[value]:checked")].map((c) => c.value),
  };
  api("pdf_start", params, confirmed).then((reply) => {
    if (reply.confirm) {
      dialog({ title: "确认转换", body: reply.confirm, ok: "继续", cancel: "取消" })
        .then((yes) => { if (yes) startPdf(true); });
      return;
    }
    pdfFile = null;
    renderPdfOptions();
  }).catch((error) => { $("pdfError").textContent = error.message; });
}

function stopJob(job) {
  if (job.provider === "llm") { api("pdf_cancel").catch(showError); return; }
  const pages = job.has_range || !job.pages_total ? "按已处理页数" : `按 ${job.pages_total} 页`;
  dialog({
    title: "停止等待这个任务？",
    body: `这里只停止查询进度。Mathpix 可能继续转换，这份文档仍可能${pages}计费。之后可以继续取结果，不用重新上传。`,
    ok: "停止等待", cancel: "继续等待",
  }).then((yes) => { if (yes) api("pdf_cancel").catch(showError); });
}

const logsOpen = new Set();

function renderJob(job) {
  const row = make("div", "job");
  const head = make("div", "job-head");
  const name = make("div", "job-name");
  name.append(job.name, make("span", job.running ? "job-status running" : "job-status", job.status));
  head.appendChild(name);
  const actions = make("div", "group");
  if (job.running) {
    if (job.log.length) {
      actions.appendChild(iconButton("file-text", "详情", () => {
        logsOpen.has(job.id) ? logsOpen.delete(job.id) : logsOpen.add(job.id);
        loaders.pdf();
      }));
    }
    actions.appendChild(job.provider === "llm"
      ? iconButton("player-pause", "暂停", () => stopJob(job))
      : iconButton("player-stop", "停止等待", () => stopJob(job)));
  } else {
    if (job.can_resume) {
      actions.appendChild(iconButton("player-play", job.status === "已完成" ? "补下载" : "继续",
        () => api("pdf_resume", job.id).catch(showError)));
    }
    if (job.can_open) {
      actions.appendChild(iconButton("folder", "打开目录",
        () => api("open_folder", job.out_dir).catch(showError)));
    }
  }
  head.appendChild(actions);
  row.appendChild(head);

  if (job.running && job.page_map.length) {
    const map = make("div", "page-map");
    job.page_map.forEach((done) => map.appendChild(make("span", done ? "done" : "")));
    row.appendChild(map);
    const finished = job.page_map.filter(Boolean).length;
    row.appendChild(make("div", "small", `${finished} / ${job.page_map.length} 页 · ${job.model}`));
  } else if (job.running) {
    const bar = make("div", "progress");
    const fill = make("span");
    fill.style.width = `${job.percent}%`;
    bar.appendChild(fill);
    row.appendChild(bar);
    row.appendChild(make("div", "small", job.pages_total
      ? `${job.pages_done} / ${job.pages_total} 页 · ${job.percent}%` : (job.status_text || "处理中")));
  } else {
    const parts = [];
    if (job.error) parts.push(job.error);
    else {
      if (job.extensions.length) parts.push(job.extensions.join("、"));
      if (job.provider === "llm") parts.push(job.model);
      if (job.pages) parts.push(`${job.pages} 页`);
    }
    if (parts.length) row.appendChild(make("div", "small", parts.join(" · ")));
  }
  if (job.running && logsOpen.has(job.id) && job.log.length) {
    row.appendChild(make("div", "job-log", job.log.join("\n")));
  }
  return row;
}

function renderPdf(state) {
  pdfBusy = state.busy;
  pdfProvider = state.provider;
  renderPdfOptions();
  const list = $("jobs");
  list.textContent = "";
  if (!state.jobs.length) list.appendChild(make("div", "empty", "转换任务会出现在这里"));
  state.jobs.forEach((job) => list.appendChild(renderJob(job)));
}

loaders.pdf = () => api("pdf_state").then(renderPdf).catch(showError);
on("pdf", renderPdf);
on("pdf_selected", setPdfFile);

const pickPdf = () => api("pdf_pick").then(setPdfFile).catch(showError);
$("drop").onclick = pickPdf;
$("drop").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") pickPdf(); });
$("pdfClear").onclick = () => { pdfFile = null; renderPdfOptions(); };
$("pdfRange").oninput = updateEstimate;
$("pdfBrowse").onclick = () => api("pdf_pick_dir", $("pdfOut").value).then((dir) => {
  if (dir) $("pdfOut").value = dir;
}).catch(showError);
$("pdfStart").onclick = () => startPdf();
bindSeg($("pdfProvider"), (value) => {
  pdfProvider = value;
  api("pdf_set_provider", value).catch(showError);
  renderPdfOptions();
});

// ---- history ---------------------------------------------------------------

function renderHistoryRow(row) {
  const item = make("div", "history-row");
  const thumb = make("div", "thumb");
  const img = make("img");
  img.alt = "";
  img.loading = "lazy";
  img.src = row.thumb;
  img.onerror = () => { thumb.innerHTML = iconSvg("photo"); };
  thumb.appendChild(img);
  const body = make("div");
  body.style.minWidth = "0";
  body.appendChild(make("div", "history-text", row.text));
  const meta = [formatTime(row.created_at)];
  if (row.model) meta.push(row.model);
  else if (row.confidence !== null) meta.push(`置信度 ${Math.round(row.confidence * 100)}%`);
  body.appendChild(make("div", "muted", meta.join(" · ")));
  const actions = make("div", "group");
  actions.append(
    iconButton("copy", "复制", () => api("history_copy", row.id).catch(showError), false),
    iconButton("trash", "删除", () => {
      dialog({ title: "确认删除", body: `确定删除这条 ${formatTime(row.created_at)} 的记录吗？`, ok: "删除", cancel: "取消" })
        .then((yes) => { if (yes) api("history_delete", row.id).then(loaders.history).catch(showError); });
    }, false));
  item.append(thumb, body, actions);
  item.onclick = () => api("history_open", row.id).catch(showError);
  return item;
}

loaders.history = () => api("history_list", $("historyQuery").value).then(({ rows, stats }) => {
  const list = $("historyList");
  list.textContent = "";
  if (!rows.length) {
    list.appendChild(make("div", "empty", $("historyQuery").value ? "没有匹配的记录" : "识别过的内容会保存在这里"));
  }
  rows.forEach((row) => list.appendChild(renderHistoryRow(row)));
  $("historyStats").textContent = `共 ${stats.count} 条 · 缓存 ${(stats.cache_bytes / 1048576).toFixed(2)} MB · 清空后费用统计仍保留`;
}).catch(showError);

on("history", () => { if (activePage === "history") loaders.history(); });
let historyTimer = 0;
$("historyQuery").oninput = () => {
  clearTimeout(historyTimer);
  historyTimer = setTimeout(loaders.history, 300);
};
$("historyClear").onclick = () => dialog({
  title: "确认清空缓存", body: "将永久删除所有识别记录和图像缓存，费用统计会保留。", ok: "清空", cancel: "取消",
}).then((yes) => { if (yes) api("history_clear").then(loaders.history).catch(showError); });

// ---- usage -----------------------------------------------------------------

let usagePeriod = "month";

function detailRow(label, amount, cost) {
  const tr = make("tr");
  tr.append(make("td", "", label), make("td", "", amount), make("td", "", money(cost)));
  return tr;
}

function renderUsage(u) {
  $("usageTotal").textContent = money(u.total);
  $("usageCny").textContent = `约 ¥${(u.total * u.rate).toFixed(2)}${u.unpriced ? `，另有 ${number(u.unpriced)} 次未定价请求` : ""}`;
  const requests = u.models.reduce((sum, m) => sum + m.requests, 0);
  $("usageDetail").replaceChildren(
    detailRow("截图识别", `${number(u.mathpix.image_count)} 张`, u.mathpix.image_cost),
    detailRow("PDF 转换", `${number(u.mathpix.pdf_pages)} 页`, u.mathpix.pdf_cost),
    detailRow("大模型", `${number(requests)} 次请求`, u.llm_cost));
  const body = $("usageModels");
  body.textContent = "";
  if (!u.models.length) {
    const tr = make("tr");
    const td = make("td", "", "暂无大模型请求");
    td.colSpan = 6;
    tr.appendChild(td);
    body.appendChild(tr);
  }
  u.models.forEach((m) => {
    const tr = make("tr");
    tr.append(make("td", "", m.model), make("td", "", number(m.requests)),
      make("td", "", number(m.input_tokens)), make("td", "", number(m.cached_tokens)),
      make("td", "", number(m.output_tokens)),
      make("td", "", m.unpriced === m.requests ? "未定价" : money(m.cost_usd)));
    tr.firstChild.title = m.model;
    body.appendChild(tr);
  });
  $("usageNote").textContent = "缓存输入已包含在输入中。费用按请求发生时的单价记录，未定价的请求不计入合计。"
    + (u.unknown ? `有 ${number(u.unknown)} 次响应未返回完整用量。` : "");
  const devices = u.devices;
  $("usageDevices").textContent = `截图 ${number(devices.images)} 次 · PDF ${number(devices.pages)} 页 · 约 ${money(devices.cost)}`;
  $("usageSynced").textContent = u.sync_needs_passphrase ? "同步已暂停，请在设置中填写同步口令"
    : (u.last_synced_at ? `上次同步 ${formatTime(u.last_synced_at)}` : "尚未同步");
  setSyncBusy(u.sync_busy);
}

function setSyncBusy(busy) {
  $("usageSync").disabled = busy;
  $("usageSyncLabel").textContent = busy ? "同步中…" : "立即同步";
}

loaders.usage = () => api("usage_summary", usagePeriod).then(renderUsage).catch(showError);
on("usage", () => { if (activePage === "usage") loaders.usage(); });
on("sync_busy", setSyncBusy);
setSeg($("usagePeriod"), usagePeriod);
bindSeg($("usagePeriod"), (value) => { usagePeriod = value; loaders.usage(); });
$("usageSync").onclick = () => api("sync_now").catch(showError);

// ---- settings --------------------------------------------------------------

let settingsTab = "service";
let imageProvider = "mathpix", pdfSettingProvider = "mathpix";
let defaults = {};

function showSettingsTab(name) {
  settingsTab = name;
  setSeg($("settingsTabs"), name);
  document.querySelectorAll(".settings-tab").forEach((t) => { t.hidden = t.dataset.tab !== name; });
}

function priceCell(row, key) {
  const td = make("td");
  const input = make("input");
  input.dataset.model = row.model;
  input.dataset.key = key;
  input.placeholder = "未定价";
  input.inputMode = "decimal";
  input.value = row[key] === undefined ? "" : row[key];
  td.appendChild(input);
  return td;
}

function fillSettings(s) {
  defaults = s;
  imageProvider = s.image_provider;
  pdfSettingProvider = s.pdf_provider;
  setSeg($("setImage"), imageProvider);
  setSeg($("setPdf"), pdfSettingProvider);
  const values = {
    appId: s.app_id, appKey: s.app_key, llmKey: s.llm_api_key, llmModel: s.llm_model,
    llmUrl: s.llm_base_url, hotkey: s.hotkey, retention: s.cache_retention_days,
    imagePrice: s.image_price_usd, pdfPrice: s.pdf_price_usd, rate: s.usd_cny_rate,
    wdUrl: s.webdav_url, wdUser: s.webdav_user, wdPass: s.webdav_password, wdPhrase: s.sync_passphrase,
    wdPath: s.webdav_path, wdInterval: s.webdav_sync_interval,
  };
  Object.entries(values).forEach(([id, value]) => { $(id).value = value; });
  const rows = $("priceRows");
  rows.textContent = "";
  s.llm_prices.forEach((row) => {
    const tr = make("tr");
    const model = make("td", "", row.model);
    model.title = row.model;
    tr.append(model, priceCell(row, "input"), priceCell(row, "cached"), priceCell(row, "output"));
    rows.appendChild(tr);
  });
  $("wdStatus").textContent = s.last_synced_at ? `上次同步 ${formatTime(s.last_synced_at)}` : "尚未同步";
  $("wdPlaintext").textContent = s.plaintext_left.length
    ? `服务器上还有未能删除的明文旧文件，请手动删除：${s.plaintext_left.join("、")}` : "";
}

function readSettings() {
  const prices = {};
  document.querySelectorAll("#priceRows input").forEach((input) => {
    (prices[input.dataset.model] = prices[input.dataset.model] || { model: input.dataset.model })[input.dataset.key] = input.value;
  });
  return {
    image_provider: imageProvider, pdf_provider: pdfSettingProvider,
    app_id: $("appId").value, app_key: $("appKey").value,
    llm_api_key: $("llmKey").value, llm_model: $("llmModel").value, llm_base_url: $("llmUrl").value,
    llm_prices: Object.values(prices),
    hotkey: $("hotkey").value, cache_retention_days: $("retention").value,
    image_price_usd: $("imagePrice").value, pdf_price_usd: $("pdfPrice").value, usd_cny_rate: $("rate").value,
    webdav_url: $("wdUrl").value, webdav_user: $("wdUser").value, webdav_password: $("wdPass").value,
    sync_passphrase: $("wdPhrase").value,
    webdav_path: $("wdPath").value, webdav_sync_interval: $("wdInterval").value,
  };
}

loaders.settings = () => {
  $("settingsError").textContent = "";
  $("settingsSaved").textContent = "";
  return api("settings_get").then(fillSettings).catch(showError);
};

showSettingsTab(settingsTab);
bindSeg($("settingsTabs"), showSettingsTab);
bindSeg($("setImage"), (value) => { imageProvider = value; });
bindSeg($("setPdf"), (value) => { pdfSettingProvider = value; });

$("settingsSave").onclick = () => {
  $("settingsError").textContent = "";
  api("settings_save", readSettings()).then(() => {
    $("settingsSaved").textContent = "已保存";
    setTimeout(() => { $("settingsSaved").textContent = ""; }, 2400);
    return api("settings_get").then(fillSettings);
  }).catch((error) => { $("settingsError").textContent = error.message; });
};

document.querySelectorAll("[data-reveal]").forEach((button) => {
  button.onclick = () => {
    const input = $(button.dataset.reveal);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.innerHTML = iconSvg(show ? "eye-off" : "eye");
    button.setAttribute("aria-label", show ? "隐藏" : "显示");
  };
});

const HOTKEY_NAMES = { Control: "", Alt: "", Shift: "", Meta: "", " ": "Space", ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right" };
$("hotkey").addEventListener("keydown", (event) => {
  if (event.key === "Tab") return;
  event.preventDefault();
  const key = event.key in HOTKEY_NAMES ? HOTKEY_NAMES[event.key] : event.key;
  if (!key) return;   // modifier alone: wait for the actual key
  const parts = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  if (event.metaKey) parts.push("Meta");
  parts.push(key.length === 1 ? key.toUpperCase() : key);
  $("hotkey").value = parts.join("+");
});
$("hotkeyReset").onclick = () => { $("hotkey").value = defaults.default_hotkey; };
$("pricesReset").onclick = () => {
  $("imagePrice").value = defaults.default_image_price;
  $("pdfPrice").value = defaults.default_pdf_price;
};

$("purgeNow").onclick = () => {
  const days = Number($("retention").value);
  if (!(days > 0)) { $("settingsError").textContent = "请先填入大于 0 的保留天数。"; return; }
  dialog({ title: "确认清理", body: `将删除超过 ${days} 天的历史记录和图像缓存，费用统计会保留。`, ok: "清理", cancel: "取消" })
    .then((yes) => {
      if (!yes) return;
      api("settings_purge", days).then((n) => {
        $("settingsSaved").textContent = `已清理 ${n} 条`;
      }).catch(showError);
    });
};

$("clearCreds").onclick = () => dialog({
  title: "清除已存凭证", body: "将清除本机保存的 Mathpix 和大模型密钥。如果开启了 WebDAV 同步，下次同步可能恢复远端的密钥。", ok: "清除", cancel: "取消",
}).then((yes) => {
  if (yes) api("settings_clear_credentials").then(loaders.settings).catch(showError);
});

$("wdTest").onclick = () => {
  $("wdStatus").textContent = "测试中…";
  api("settings_test_webdav", readSettings()).catch(showError);
};
$("wdSync").onclick = () => {
  $("wdStatus").textContent = "同步中…";
  api("settings_sync", readSettings()).catch((error) => {
    $("wdStatus").textContent = error.message;
  });
};
on("webdav", (result) => {
  if (result.merged) {
    // The merge may have brought newer credentials and prices; keep what the
    // user is typing into the connection fields.
    const connection = ["wdUrl", "wdUser", "wdPass", "wdPhrase", "wdPath", "wdInterval"].map((id) => [id, $(id).value]);
    api("settings_get").then((s) => {
      fillSettings(s);
      connection.forEach(([id, value]) => { $(id).value = value; });
      $("wdStatus").textContent = result.message;
    });
    return;
  }
  $("wdStatus").textContent = result.message;
  if (result.undecryptable) {
    dialog({
      title: "无法解密远端数据",
      body: "同步口令不正确，或远端文件已损坏。如果确认旧口令已经忘记，可以用当前口令覆盖远端。其他设备改用新口令后，会把它们的数据合并回来。",
      ok: "用当前口令覆盖", cancel: "先不动",
    }).then((yes) => {
      if (!yes) return;
      $("wdStatus").textContent = "同步中…";
      api("settings_sync", readSettings(), true).catch(showError);
    });
  }
});

// ---- start -----------------------------------------------------------------

connect(() => api("tool_state").then((state) => showPage(state.page)).catch(showError));
