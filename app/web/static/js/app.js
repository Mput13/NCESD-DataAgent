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

seedConversation();
bindComposer();
bindFilters();

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
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      sendMessage();
    }
  });
  sendBtn.addEventListener("click", sendMessage);
  $$(".sugg").forEach((button) => {
    button.addEventListener("click", () => {
      composer.value = button.textContent.replace(/^[^\p{L}\p{N}]+/u, "");
      composer.focus();
      composer.dispatchEvent(new Event("input"));
    });
  });
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

  const typing = buildTypingMessage();
  thread.appendChild(typing);
  setBusy(true);
  scrollToBottom();

  try {
    const isContinuation = latestWorkflow?.pendingClarification;
    const response = await postJson(isContinuation ? "/api/continue" : "/api/query", {
      ...(isContinuation
        ? { run_id: latestWorkflow.runId, answer: text }
        : { query: text }),
      local_mode: false,
    });
    typing.remove();
    renderWorkflowResponse(response);
  } catch (error) {
    typing.remove();
    thread.appendChild(
      buildAssistantMessage({
        role: "Error",
        message: `Ошибка запроса: ${error.message || error}`,
      }),
    );
  } finally {
    setBusy(false);
    scrollToBottom();
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
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

function renderWorkflowResponse(response) {
  latestWorkflow = {
    runId: response.run_id,
    pendingClarification: response.final_outcome === "needs_clarification",
  };
  $(".run-id").textContent = response.run_id || "run";
  $(".run-stage").textContent = response.final_outcome || "ready";
  thread.appendChild(buildAssistantMessage(workflowViewModel(response)));
  syncArtifacts(response);
  scrollToBottom();
}

function workflowViewModel(response) {
  const blocks = [];
  const questions = response.clarification_questions || [];
  const datasets = response.dataset_artifacts || [];
  const selectedSources = response.selected_sources || [];

  if (questions.length) {
    blocks.push(card("Нужно уточнение", "Ответьте следующим сообщением", list(questions)));
  }
  if (response.answer_blocks?.length) {
    blocks.push(answerBlocksCard(response.answer_blocks));
  }
  if (datasets.length) {
    blocks.push(datasetSummaryCard(datasets));
    blocks.push(...datasets.map(datasetPreviewCard).filter(Boolean));
  }
  if (selectedSources.length) {
    blocks.push(sourcesStrip(selectedSources.slice(0, 6)));
  }

  return {
    role: response.final_outcome || "Result",
    meta: response.run_id || "",
    message: response.message || "Готово.",
    blocks: blocks.join(""),
  };
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

function buildAssistantMessage({ role, meta = "", message, blocks = "" }) {
  const el = document.createElement("div");
  el.className = "msg ai fade-in";
  el.innerHTML = `
    ${aiAvatar()}
    <div class="msg-body">
      <div class="msg-meta">
        <b>DataAgent</b>
        <span class="role-tag">${escapeHtml(role)}</span>
        ${meta ? `<span>·</span><span>${escapeHtml(meta)}</span>` : ""}
      </div>
      <div class="msg-text">${escapeHtml(message)}</div>
      ${blocks}
      <div class="action-bar">
        <button class="act-btn" type="button">Полезно <span class="count">0</span></button>
        <button class="act-btn" type="button">Нужна правка</button>
      </div>
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
  if (!records.length) return "";
  const rows = records.map((record) => [
    record.geo_name || record.geo_id || "",
    record.period || "",
    record.value ?? "",
    record.unit || "",
    (record.quality_flags || []).join(", "),
  ]);
  return card(
    "Строки датасета",
    dataset.artifact_id || dataset.source_id || "",
    table(["География", "Период", "Значение", "Ед.", "Качество"], rows),
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
      ${sources
        .map(
          (source, index) => `
            <a href="${escapeHtml(source.provenance_url || source.url || "#")}" class="source-pill" target="_blank" rel="noreferrer">
              <span class="src-num">${index + 1}</span>
              <span>${escapeHtml(source.title || source.name || source.source_id || source.id || "source")}</span>
              <span class="src-host">${escapeHtml(source.source_family || hostOf(source.provenance_url || source.url || ""))}</span>
            </a>`,
        )
        .join("")}
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

function syncArtifacts(response) {
  artifacts = [];
  (response.dataset_artifacts || []).forEach((dataset) => {
    artifacts.push({
      kind: "table",
      kindLabel: "DATA",
      name: dataset.artifact_id || dataset.csv_path || "dataset",
      size: `${dataset.rows ?? 0} rows`,
      format: dataset.csv_path ? "csv" : dataset.parquet_path ? "parquet" : "records",
      time: "now",
      thumb: `<div class="thumb-table"><div class="row head"><span>Dataset</span><span>Rows</span><span>Status</span></div><div class="row"><span>artifact</span><span>${dataset.rows ?? 0}</span><span>${escapeHtml(dataset.status || "")}</span></div></div>`,
    });
  });
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
      (artifact) => `
        <div class="art-card fade-in">
          <div class="art-card-thumb ${artifact.kind}">
            <span class="badge-pin">${escapeHtml(artifact.kindLabel)}</span>
            ${artifact.thumb}
          </div>
          <div class="art-card-body">
            <div class="art-card-name">${escapeHtml(artifact.name)}</div>
            <div class="art-card-meta"><span>${escapeHtml(artifact.size)}</span><span class="dot-sep"></span><span>${escapeHtml(artifact.format)}</span></div>
          </div>
          <div class="art-card-foot"><span class="art-card-time">${escapeHtml(artifact.time)}</span></div>
        </div>`,
    )
    .join("");
}

function setBusy(isBusy) {
  sendBtn.disabled = isBusy;
  composer.disabled = isBusy;
  const stage = $(".run-stage");
  if (stage) stage.textContent = isBusy ? "Pipeline running" : "Pipeline ready";
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
