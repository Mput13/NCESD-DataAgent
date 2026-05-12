const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const thread = $("#thread");
const chatScroll = $("#chatScroll");
const composer = $("#composerInput");
const sendBtn = $("#sendBtn");
const artListEl = $("#artList");
const artSubEl = $("#artifactsSub");

let latestWorkflow = null;
let artifacts = [];
let artifactFilter = "all";
let activeAbortController = null;

seedConversation();
bindComposer();
bindFilters();
bindHeaderActions();

function seedConversation() {
  thread.appendChild(
    buildAssistantMessage({
      role: "Workspace",
      message:
        "Готов к анализу. Задайте экономический вопрос, а я покажу ответ, источники, артефакты и trace выполнения.",
    }),
  );
  paintArtifacts();
}

function bindComposer() {
  composer.addEventListener("input", () => {
    composer.style.height = "auto";
    composer.style.height = `${Math.min(composer.scrollHeight, 200)}px`;
  });
  composer.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  sendBtn.onclick = sendMessage;
  $$(".sugg").forEach((button) => {
    button.addEventListener("click", () => {
      composer.value = button.textContent.replace(/^[^\p{L}\p{N}]+/u, "");
      composer.focus();
      composer.dispatchEvent(new Event("input"));
    });
  });
}

function bindHeaderActions() {
  const newBtn = $("#newAnalysisBtn");
  if (newBtn) newBtn.addEventListener("click", () => location.reload());

  const shareBtn = $("#shareBtn");
  if (shareBtn) {
    shareBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(location.href).then(() => {
        shareBtn.textContent = "Скопировано!";
        setTimeout(() => (shareBtn.textContent = "Share"), 1500);
      }).catch(() => {
        prompt("Ссылка для копирования:", location.href);
      });
    });
  }

  const exportBtn = $("#exportBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      const msgs = $$(".msg").map((el) => el.innerText).join("\n\n---\n\n");
      const blob = new Blob([msgs], { type: "text/plain" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `dataagent-export-${Date.now()}.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }
}

function bindFilters() {
  $$(".art-filter").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".art-filter").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      artifactFilter = button.dataset.filter || "all";
      paintArtifacts();
    });
  });
}

async function sendMessage() {
  const text = composer.value.trim();
  if (!text) return;

  thread.appendChild(buildUserMessage(text));
  composer.value = "";
  composer.style.height = "auto";

  activeAbortController = new AbortController();
  setBusy(true);
  scrollToBottom();

  const isContinuation = latestWorkflow?.pendingClarification;

  // Clarification uses old blocking path; fresh queries use SSE stream
  if (isContinuation) {
    const typing = buildTypingMessage();
    thread.appendChild(typing);
    try {
      const response = await postJson(
        "/api/continue",
        { run_id: latestWorkflow.runId, answer: text, local_mode: false },
        activeAbortController.signal,
      );
      typing.remove();
      renderWorkflowResponse(response);
    } catch (error) {
      typing.remove();
      _handleSendError(error);
    } finally {
      activeAbortController = null;
      setBusy(false);
      scrollToBottom();
    }
    return;
  }

  // SSE streaming path
  const thinkingEl = buildThinkingMessage();
  thread.appendChild(thinkingEl);
  scrollToBottom();

  try {
    await streamQuery(text, thinkingEl, activeAbortController.signal);
  } catch (error) {
    thinkingEl.remove();
    _handleSendError(error);
  } finally {
    activeAbortController = null;
    setBusy(false);
    scrollToBottom();
  }
}

function _handleSendError(error) {
  if (error.name === "AbortError") {
    thread.appendChild(buildAssistantMessage({ role: "", message: "Запрос остановлен." }));
  } else {
    thread.appendChild(buildAssistantMessage({ role: "Error", message: `Ошибка: ${error.message || error}` }));
  }
}

function stopMessage() {
  if (activeAbortController) activeAbortController.abort();
}

// ---- SSE streaming ----

async function streamQuery(query, thinkingEl, signal) {
  const res = await fetch("/api/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, local_mode: false }),
    signal,
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(txt || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  // Accumulated trace events for the final trace card
  const allTraceEvents = [];

  let gotDone = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // Parse SSE frames (may contain multiple)
    const frames = buf.split("\n\n");
    buf = frames.pop(); // last partial frame stays in buffer

    for (const frame of frames) {
      if (!frame.trim()) continue;
      let eventType = "message";
      let dataLine = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        if (line.startsWith("data: "))  dataLine  = line.slice(6);
      }
      if (!dataLine) continue;
      let payload;
      try { payload = JSON.parse(dataLine); } catch { continue; }

      if (eventType === "step") {
        (payload.new_trace_events || []).forEach((e) => allTraceEvents.push(e));
        updateThinkingMessage(thinkingEl, payload, allTraceEvents);
        scrollToBottom();
      } else if (eventType === "done") {
        gotDone = true;
        thinkingEl.remove();
        renderWorkflowResponse(payload, allTraceEvents);
        return;
      } else if (eventType === "error") {
        throw new Error(payload.message || "stream error");
      }
    }
  }

  // Stream ended without a done event
  if (!gotDone) {
    throw new Error("Соединение прервано до получения ответа.");
  }
}

async function postJson(url, payload, signal) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  const raw = await response.text();
  const data = raw ? parseJson(raw) : {};
  if (!response.ok) {
    throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  }
  return data;
}

function parseJson(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return { error: raw };
  }
}

// Agent step labels shown in streaming thinking bubble
const AGENT_LABELS = {
  supervisor:           "Супервизор",
  intent_analyst:       "Анализатор намерений",
  research_designer:    "Дизайнер исследования",
  source_scouts:        "Разведчики источников",
  coverage_schema:      "Покрытие и схема",
  extraction_planner:   "Планировщик извлечения",
  deterministic_tools:  "Детерминированные инструменты",
  finalization_pending: "Завершение",
  finalization:         "Критик + Нарратор",
};

function buildThinkingMessage() {
  const el = document.createElement("div");
  el.className = "msg ai fade-in";
  el.innerHTML = `
    ${aiAvatar()}
    <div class="msg-body">
      <div class="msg-meta"><b>DataAgent</b><span class="role-tag">Думает</span></div>
      <div class="thinking-stream" id="thinkingStream">
        <div class="thinking-step active" id="thinkingCurrent">
          <span class="thinking-dot"></span>
          <span class="thinking-text">Запрос получен, начинаю анализ...</span>
        </div>
        <div class="thinking-steps-done" id="thinkingDone"></div>
      </div>
    </div>
  `;
  return el;
}

function updateThinkingMessage(el, stepPayload, allTraceEvents) {
  const currentEl = el.querySelector("#thinkingCurrent .thinking-text");
  const doneEl = el.querySelector("#thinkingDone");
  if (!currentEl || !doneEl) return;

  const node = stepPayload.node || "";
  const label = AGENT_LABELS[node] || node;
  const description = stepPayload.description || label;

  // Move previous current to done list
  const prevText = currentEl.textContent;
  if (prevText && prevText !== "Запрос получен, начинаю анализ...") {
    const doneItem = document.createElement("div");
    doneItem.className = "thinking-step done";
    doneItem.innerHTML = `<span class="thinking-check">✓</span><span class="thinking-text">${escapeHtml(prevText)}</span>`;
    doneEl.insertBefore(doneItem, doneEl.firstChild);
  }

  // Show new current step
  currentEl.textContent = description;

  // Append any new trace events as sub-details
  const newEvents = stepPayload.new_trace_events || [];
  newEvents.forEach((evt) => {
    const decision = evt.decision || "";
    // Filter out internal/technical decisions from user view
    if (!decision || decision === "ok" || decision === "finalization_pending") return;
    const item = document.createElement("div");
    item.className = "thinking-detail fade-in";
    item.textContent = _humanizeDecision(label, decision, evt);
    doneEl.insertBefore(item, doneEl.firstChild);
  });
}

function _humanizeDecision(agentLabel, decision, evt) {
  const map = {
    "research":             "→ выбран маршрут: полное исследование",
    "direct":               "→ выбран маршрут: прямой поиск",
    "no_data":              "→ запрос на данные вне области охвата",
    "gated":                "→ LLM недоступен, запрос остановлен",
    "triage_llm_failed_using_research_default": "→ таймаут LLM, запрос остановлен",
    "not_found":            "→ данные не найдены в источниках",
    "needs_user_clarification": "→ требуется уточнение от пользователя",
    "skipped":              "→ шаг пропущен",
    "clarification_merged": "→ уточнение пользователя учтено",
  };
  if (map[decision]) return `${agentLabel}: ${map[decision]}`;
  // Format artifact IDs friendlier
  if (decision.startsWith("extraction-plan-")) return `${agentLabel}: → план извлечения создан`;
  return `${agentLabel}: ${decision}`;
}

function renderWorkflowResponse(response, streamedTraceEvents) {
  latestWorkflow = {
    runId: response.run_id,
    pendingClarification: response.final_outcome === "needs_clarification",
  };
  $(".run-id").textContent = response.run_id || "run";
  // Prefer streamed trace events (already shown live); fall back to response events
  const traceEvents = (streamedTraceEvents && streamedTraceEvents.length)
    ? streamedTraceEvents
    : (response.trace_events || []);
  const vm = workflowViewModel({ ...response, trace_events: traceEvents });
  vm.outcome = response.final_outcome || "";
  thread.appendChild(buildAssistantMessage(vm));
  syncArtifacts(response);
  scrollToBottom();
}

function workflowViewModel(response) {
  const traceBlocks = [];
  const contentBlocks = [];
  const outcome = response.final_outcome;
  const questions = response.clarification_questions || [];
  const datasets = response.dataset_artifacts || [];
  const selectedSources = response.selected_sources || [];

  // Trace always comes first (above the answer)
  if (response.trace_events?.length) {
    traceBlocks.push(traceCard(response.trace_events));
  }

  if (outcome === "needs_clarification") {
    if (questions.length) {
      contentBlocks.push(card("Нужно уточнение", "Ответьте следующим сообщением", list(questions)));
    }
  } else if (outcome === "not_found") {
    if (selectedSources.length) {
      contentBlocks.push(sourcesStrip(selectedSources.slice(0, 6)));
    }
  } else if (outcome === "passed") {
    if (response.answer_blocks?.length) {
      contentBlocks.push(answerBlocksCard(response.answer_blocks));
    }
    const inlineChart = buildInlineChartCard(response);
    if (inlineChart) contentBlocks.push(inlineChart);
    if (datasets.length) {
      contentBlocks.push(datasetSummaryCard(datasets));
      contentBlocks.push(...datasets.map(datasetPreviewCard).filter(Boolean));
    }
    if (selectedSources.length) {
      contentBlocks.push(sourcesStrip(selectedSources.slice(0, 6)));
    }
  } else {
    if (response.answer_blocks?.length) {
      contentBlocks.push(answerBlocksCard(response.answer_blocks));
    }
  }

  return {
    role: outcomeLabel(outcome),
    meta: "",
    message: response.message || "Готово.",
    trace: traceBlocks.join(""),
    blocks: contentBlocks.join(""),
  };
}

function outcomeLabel(outcome) {
  return { passed: "Ответ", needs_clarification: "Уточнение" }[outcome] || "";
}

function traceCard(events) {
  const id = `trace-${Math.random().toString(36).slice(2)}`;
  const rows = events.map((event) => {
    const step = escapeHtml(event.state || "");
    const agent = escapeHtml(event.agent || "");
    const decision = escapeHtml(event.decision || "—");
    const summary = escapeHtml(event.input_summary || event.output_artifact || "");
    const warnings = (event.warnings || [])
      .filter((w) => !isInternalWarning(w))
      .map((w) => `<br><span class="trace-warn">⚠ ${escapeHtml(w)}</span>`)
      .join("");
    return `<tr>
      <td><span class="trace-step">${step}</span></td>
      <td>${agent}</td>
      <td><span class="trace-decision">${decision}</span></td>
      <td class="trace-summary">${summary}${warnings}</td>
    </tr>`;
  });

  const tableHtml = `
    <div class="table-wrap">
      <table class="data-table trace-table">
        <thead><tr><th>Шаг</th><th>Агент</th><th>Решение</th><th>Детали</th></tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    </div>`;

  return `
    <div class="trace-card" id="${id}">
      <div class="trace-card-head">
        <span>Путь размышлений · ${events.length} шагов</span>
        <button class="chip-btn ghost trace-hide-btn" type="button" onclick="
          var c=document.getElementById('${id}');
          var t=c.querySelector('.trace-card-body');
          var b=c.querySelector('.trace-hide-btn');
          if(t.style.display==='none'){t.style.display='';b.textContent='Скрыть';}
          else{t.style.display='none';b.textContent='Показать';}
        ">Скрыть</button>
      </div>
      <div class="trace-card-body">${tableHtml}</div>
    </div>`;
}

function isInternalWarning(w) {
  if (!w) return false;
  const lower = String(w).toLowerCase();
  return lower.includes("fedstat_parquet_not_found")
    || lower.includes("local fedstat parquet not found")
    || lower.includes("gated")
    || lower.includes("fedstat parquet");
}

function buildUserMessage(text) {
  const el = document.createElement("div");
  el.className = "msg user fade-in";
  el.innerHTML = `
    <div class="avatar user">Вы</div>
    <div class="msg-body">
      <div class="msg-meta"><b>Вы</b><span>·</span><span>сейчас</span></div>
      <div class="msg-text">${escapeHtml(text)}</div>
    </div>
  `;
  return el;
}

function buildAssistantMessage({ role, meta = "", message, trace = "", blocks = "", outcome = "" }) {
  const el = document.createElement("div");
  el.className = "msg ai fade-in";
  el.innerHTML = `
    ${aiAvatar()}
    <div class="msg-body">
      <div class="msg-meta">
        <b>DataAgent</b>
        ${role ? `<span class="role-tag" data-outcome="${escapeHtml(outcome)}">${escapeHtml(role)}</span>` : ""}
      </div>
      ${trace}
      <div class="msg-text">${escapeHtml(message)}</div>
      ${blocks}
    </div>
  `;
  return el;
}

function buildTypingMessage() {
  const el = document.createElement("div");
  el.className = "msg ai fade-in";
  el.innerHTML = `
    ${aiAvatar()}
    <div class="msg-body">
      <div class="msg-meta"><b>DataAgent</b><span class="role-tag">Pipeline</span></div>
      <div class="msg-text"><div class="typing"><span></span><span></span><span></span></div></div>
    </div>
  `;
  return el;
}

function aiAvatar() {
  return `
    <div class="avatar ai" aria-label="DataAgent">
      <svg viewBox="0 0 24 24" fill="none">
        <circle cx="7" cy="7" r="2.4" fill="#2684FF"/>
        <circle cx="17" cy="7" r="2.4" fill="#FFFFFF"/>
        <circle cx="12" cy="17" r="2.4" fill="#B6FF00"/>
        <path d="M7 7L12 17L17 7L7 7Z" stroke="#FFFFFF" stroke-width="1.2" stroke-linejoin="round" opacity=".5"/>
      </svg>
    </div>`;
}

function datasetSummaryCard(datasets) {
  const totalRows = datasets.reduce((sum, dataset) => sum + Number(dataset.rows || 0), 0);
  const items = datasets.map((dataset) => {
    const columns = dataset.columns?.length ? `, колонок: ${dataset.columns.length}` : "";
    return `${dataset.artifact_id || "dataset"}: ${dataset.rows ?? 0} строк${columns}`;
  });
  return card("Данные результата", `${datasets.length} artifact(s) · ${totalRows} строк`, list(items), "table");
}

function datasetPreviewCard(dataset) {
  const records = (dataset.records || []).slice(0, 5);
  if (!records.length && !dataset.csv_path) return "";
  const rows = records.map((record) => [
    record.geo_name || record.geo_id || "",
    record.period || "",
    record.value ?? "",
    record.unit || "",
    (record.quality_flags || []).join(", "),
  ]);
  const downloadBtn = dataset.csv_path
    ? `<a href="/api/download?path=${encodeURIComponent(dataset.csv_path)}" download style="display:inline-block;margin-top:8px;padding:4px 12px;background:#2563eb;color:#fff;border-radius:4px;text-decoration:none;font-size:12px;">⬇ Скачать CSV (${dataset.rows} строк)</a>`
    : "";
  return card(
    "Строки датасета",
    dataset.artifact_id || dataset.source_id || "",
    table(["География", "Период", "Значение", "Ед.", "Качество"], rows) + downloadBtn,
    "table",
  );
}

function answerBlocksCard(blocks) {
  const html = blocks
    .map((block) => {
      if (block.type === "summary" && block.text) {
        return `<p>${escapeHtml(block.text)}</p>`;
      }
      if (block.type === "methodology" && block.text) {
        return `<p><strong>Методология:</strong> ${escapeHtml(block.text)}</p>`;
      }
      if (block.type === "how_found" && block.text) {
        return `<p><strong>Как найдено:</strong> ${escapeHtml(block.text)}</p>`;
      }
      if (block.type === "limitations" && block.items?.length) {
        return `<p><strong>Ограничения:</strong></p>${list(block.items)}`;
      }
      if (block.type === "not_found") {
        return `<p>${escapeHtml(block.summary || "Данные не найдены")}</p>`;
      }
      if (block.type === "clarification_request" && block.questions?.length) {
        return list(block.questions);
      }
      return "";
    })
    .filter(Boolean)
    .join("");
  return html ? card("Ответ", "Сводка, методология и ограничения", `<div class="answer-blocks">${html}</div>`, "doc") : "";
}

function sourcesStrip(sources) {
  return `
    <div class="sources-strip">
      <span class="sources-label">Источники</span>
      <div class="sources-pills">
        ${sources.map((source, index) => `
          <a href="${escapeHtml(source.provenance_url || source.url || "#")}" class="source-pill" target="_blank" rel="noreferrer">
            <span class="src-num">${index + 1}</span>
            <span>${escapeHtml(source.title || source.name || source.source_id || source.id || "source")}</span>
            <span class="src-host">${escapeHtml(source.source_family || hostOf(source.provenance_url || source.url || ""))}</span>
          </a>`).join("")}
      </div>
    </div>`;
}

function card(title, subtitle, body, kind = "doc") {
  const iconClass = kind === "code" ? "lime" : kind === "table" ? "" : "peach";
  return `
    <div class="artifact ${kind === "code" ? "code-card" : ""}">
      <div class="artifact-head">
        <div class="art-title">
          <span class="art-ico ${iconClass}">${kind === "code" ? "&lt;/&gt;" : kind === "table" ? "#" : "?"}</span>
          <div>
            <div>${escapeHtml(title)}</div>
            <div class="art-sub">${escapeHtml(subtitle || "")}</div>
          </div>
        </div>
      </div>
      ${body}
    </div>`;
}

function list(items) {
  return `<div class="table-wrap"><table class="data-table"><tbody>${items
    .map((item) => `<tr><td>${escapeHtml(item)}</td></tr>`)
    .join("")}</tbody></table></div>`;
}

function table(headers, rows) {
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows
            .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
            .join("")}
        </tbody>
      </table>
    </div>`;
}

// ---- Inline chart card ----

function _chartSeriesFromDataset(dataset) {
  const records = dataset.records || [];
  if (!records.length) return null;

  // Label column: period or year
  const labelKey = records[0].period !== undefined ? "period"
    : records[0].year  !== undefined ? "year"
    : null;

  // Value column: value, val, or first numeric field
  const numericKey = (() => {
    for (const key of ["value", "val"]) {
      if (records[0][key] !== undefined) return key;
    }
    for (const key of Object.keys(records[0])) {
      if (typeof records[0][key] === "number") return key;
    }
    return null;
  })();

  if (!numericKey) return null;

  const labels = records.map((r) => String(r[labelKey] ?? ""));
  const values = records.map((r) => Number(r[numericKey]));
  if (values.some((v) => isNaN(v))) return null;

  return { labels, values };
}

function _groupedSeries(dataset) {
  // Returns array of { geo, labels, values }
  const records = dataset.records || [];
  if (!records.length) return [];

  const geoKey = records[0].geo_id !== undefined ? "geo_id"
    : records[0].country_id !== undefined ? "country_id"
    : null;
  if (!geoKey) return [];

  const labelKey = records[0].period !== undefined ? "period"
    : records[0].year  !== undefined ? "year"
    : null;

  const numericKey = (() => {
    for (const key of ["value", "val"]) {
      if (records[0][key] !== undefined) return key;
    }
    for (const key of Object.keys(records[0])) {
      if (typeof records[0][key] === "number") return key;
    }
    return null;
  })();
  if (!numericKey) return [];

  const groups = {};
  records.forEach((r) => {
    const geo = String(r[geoKey] ?? "");
    if (!groups[geo]) groups[geo] = [];
    groups[geo].push(r);
  });

  return Object.entries(groups).map(([geo, recs]) => ({
    geo,
    labels: recs.map((r) => String(r[labelKey] ?? "")),
    values: recs.map((r) => Number(r[numericKey])),
  })).filter((s) => !s.values.some((v) => isNaN(v)));
}

function buildInlineChartCard(response) {
  const vis = response.visualization;
  if (!vis || vis.status !== "ok") return null;
  if (!vis.chart_type || vis.chart_type === "table") return null;

  const datasets = response.dataset_artifacts || [];
  const dataset = datasets.find((d) => d.artifact_id === vis.dataset_artifact_id)
    || datasets.find((d) => d.records?.length);
  if (!dataset || !dataset.records?.length) return null;

  const chartType = vis.chart_type; // "line" | "grouped_line" | "bar"
  const title = dataset.records[0]?.indicator_name || "График";

  let svgHtml = "";

  if (chartType === "grouped_line") {
    const series = _groupedSeries(dataset);
    if (!series.length) {
      // fall back to single series
      const s = _chartSeriesFromDataset(dataset);
      if (!s) return null;
      svgHtml = renderTrendChart(s.values, s.labels);
    } else {
      // Render one trend chart per series, stacked
      svgHtml = series.map((s) =>
        `<div class="inline-chart-series-label">${escapeHtml(s.geo)}</div>${renderTrendChart(s.values, s.labels)}`
      ).join("");
    }
  } else if (chartType === "bar") {
    const s = _chartSeriesFromDataset(dataset);
    if (!s) return null;
    svgHtml = renderBarChart(s.values, s.labels);
  } else {
    // line or anything else
    const s = _chartSeriesFromDataset(dataset);
    if (!s) return null;
    svgHtml = renderTrendChart(s.values, s.labels);
  }

  // Use a unique ID so the expand button can reference the SVG content
  const cardId = `inline-chart-${Math.random().toString(36).slice(2)}`;

  return `
    <div class="artifact inline-chart-card" id="${cardId}">
      <div class="artifact-head">
        <div class="art-title">
          <span class="art-ico">&vltri;</span>
          <div>
            <div>${escapeHtml(title)}</div>
            <div class="art-sub">${escapeHtml(chartType)}</div>
          </div>
        </div>
        <button class="chip-btn ghost" type="button" title="Развернуть"
          onclick="(function(){
            var dlg=document.getElementById('chart-dialog');
            var src=document.getElementById('${cardId}').querySelector('.inline-chart-body').innerHTML;
            dlg.querySelector('.chart-dialog-inner').innerHTML=src;
            dlg.showModal();
          })()">&#x2197;</button>
      </div>
      <div class="inline-chart-body">${svgHtml}</div>
    </div>`;
}

function closeChartDialog() {
  const dlg = document.getElementById("chart-dialog");
  if (dlg) dlg.close();
}

function syncArtifacts(response) {
  artifacts = [];

  // Chart artifact from visualization spec
  const vis = response.visualization;
  if (vis && vis.status === "ok" && vis.chart_type && vis.chart_type !== "table") {
    const chartTypeLabels = { line: "График", grouped_line: "График (сравнение)", bar: "Диаграмма" };
    const chartLabel = chartTypeLabels[vis.chart_type] || "График";
    const records = _visRecords(vis);
    artifacts.push({
      kind: "chart",
      kindLabel: chartLabel,
      name: _visTitle(response.dataset_artifacts, vis),
      size: `${records.length} точек`,
      format: vis.chart_type,
      time: "сейчас",
      thumb: _buildMiniChart(records),
      records,
      vis,
    });
  }

  // Table artifacts from dataset_artifacts
  (response.dataset_artifacts || []).forEach((dataset) => {
    if (!dataset.records?.length && !dataset.rows) return;
    const records = (dataset.records || []).slice(0, 20);
    const sourceName = dataset.source_id || dataset.artifact_id || "dataset";
    const indicatorName = records[0]?.indicator_name || "";
    const name = indicatorName
      ? `${indicatorName.slice(0, 40)}`
      : sourceName.replace(/^dataset-/, "Данные ");
    artifacts.push({
      kind: "table",
      kindLabel: "Таблица",
      name,
      size: `${dataset.rows ?? records.length} строк`,
      format: dataset.csv_path ? "CSV" : dataset.parquet_path ? "Parquet" : "JSON",
      time: "сейчас",
      thumb: _buildMiniTable(records),
      dataset,
    });
  });

  // Document artifact — answer blocks summary
  if (response.answer_blocks?.length) {
    const summary = response.answer_blocks.find((b) => b.type === "summary");
    if (summary?.text) {
      artifacts.push({
        kind: "doc",
        kindLabel: "Документ",
        name: "Сводка ответа",
        size: `${response.answer_blocks.length} блок(ов)`,
        format: "Текст",
        time: "сейчас",
        thumb: `<div class="thumb-doc">${escapeHtml(summary.text.slice(0, 120))}...</div>`,
      });
    }
  }

  paintArtifacts();
}

function paintArtifacts() {
  const visible = artifactFilter === "all" ? artifacts : artifacts.filter((artifact) => artifact.kind === artifactFilter);
  artSubEl.textContent = `${artifacts.length} artifacts`;
  if (!artifacts.length) {
    artListEl.innerHTML = `
      <div class="art-empty">
        <div class="art-empty-ico">#</div>
        <div class="art-empty-title">Здесь появятся артефакты</div>
        <div class="art-empty-text">Таблицы, скрипты и документы из ответа будут собираться сюда.</div>
      </div>`;
    return;
  }
  artListEl.innerHTML = visible
    .map(
      (artifact) => {
        const csvPath = artifact.dataset?.csv_path;
        const scriptPath = artifact.script?.script_path;
        const dlHref = csvPath
          ? `/api/download?path=${encodeURIComponent(csvPath)}`
          : scriptPath
          ? `/api/download?path=${encodeURIComponent(scriptPath)}`
          : null;
        const dlBtn = dlHref
          ? `<a href="${dlHref}" download class="art-dl-btn">⬇ Скачать</a>`
          : "";
        return `
        <div class="art-card fade-in">
          <div class="art-card-thumb ${artifact.kind}">
            <span class="badge-pin">${escapeHtml(artifact.kindLabel)}</span>
            ${artifact.thumb}
          </div>
          <div class="art-card-body">
            <div class="art-card-name">${escapeHtml(artifact.name)}</div>
            <div class="art-card-meta"><span>${escapeHtml(artifact.size)}</span><span class="dot-sep"></span><span>${escapeHtml(artifact.format)}</span></div>
            ${dlBtn}
          </div>
          <div class="art-card-foot"><span class="art-card-time">${escapeHtml(artifact.time)}</span></div>
        </div>`;
      }
    )
    .join("");
}

function _visRecords(vis) {
  try {
    const datasets = vis.encoding?.spec?.datasets || {};
    const key = Object.keys(datasets)[0];
    return key ? datasets[key] : [];
  } catch { return []; }
}

function _visTitle(datasets, vis) {
  const ds = (datasets || []).find((d) => d.artifact_id === vis.dataset_artifact_id);
  const records = _visRecords(vis);
  const name = records[0]?.indicator_name || ds?.source_id || "Данные";
  return name.slice(0, 50);
}

function _buildMiniChart(records) {
  const vals = records.map((r) => Number(r.value)).filter((v) => !isNaN(v) && v !== null);
  if (!vals.length) return `<div class="thumb-chart-empty">нет данных</div>`;
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const h = 48, w = 120;
  const pts = vals.slice(0, 20).map((v, i) => {
    const x = (i / Math.max(vals.length - 1, 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="display:block">
    <polyline points="${pts}" fill="none" stroke="#2684FF" stroke-width="2" stroke-linejoin="round"/>
    <polyline points="0,${h} ${pts} ${w},${h}" fill="rgba(38,132,255,.12)" stroke="none"/>
  </svg>`;
}

function _buildMiniTable(records) {
  if (!records.length) return "";
  const cols = ["geo_name", "period", "value", "unit"].filter((k) => records[0]?.[k] !== undefined);
  const colLabels = { geo_name: "Регион", period: "Период", value: "Значение", unit: "Ед." };
  const head = cols.map((c) => escapeHtml(colLabels[c] || c)).join("</span><span>");
  const rows = records.slice(0, 4).map((r) =>
    `<div class="mt-row">${cols.map((c) => `<span>${escapeHtml(String(r[c] ?? ""))}</span>`).join("")}</div>`
  ).join("");
  return `<div class="mini-table">
    <div class="mt-row mt-head"><span>${head}</span></div>
    ${rows}
  </div>`;
}

function setBusy(isBusy) {
  composer.disabled = isBusy;
  if (isBusy) {
    sendBtn.innerHTML = `<svg viewBox="0 0 20 20" width="14" height="14"><rect x="5" y="5" width="10" height="10" rx="2" fill="currentColor"/></svg>`;
    sendBtn.classList.add("stop-mode");
    sendBtn.onclick = (e) => { e.preventDefault(); stopMessage(); };
  } else {
    sendBtn.innerHTML = `<svg viewBox="0 0 20 20" width="16" height="16"><path d="M3 10l14-6-6 14-2-6-6-2Z" fill="currentColor"/></svg>`;
    sendBtn.classList.remove("stop-mode");
    sendBtn.onclick = sendMessage;
  }
}

function hostOf(rawUrl) {
  try {
    return rawUrl ? new URL(rawUrl).host : "";
  } catch {
    return "";
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatScroll.scrollTop = chatScroll.scrollHeight;
  });
}
