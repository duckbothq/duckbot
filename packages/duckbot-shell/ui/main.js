const { invoke } = window.__TAURI__.core;

const byId = (id) => document.getElementById(id);
const status = byId("status");
let activePreview = null;
let pendingApproval = null;
let busy = false;

async function rpc(method, params = {}) {
  return invoke("rpc", { method, params });
}

function setStatus(message, kind = "") {
  status.textContent = message;
  status.dataset.state = kind;
}

function errorMessage(error) {
  return String(error || "未知錯誤 / Unknown error");
}

function syncActionButtons() {
  byId("execute").disabled =
    busy || !activePreview || activePreview.state === "blocked" || pendingApproval !== null;
  byId("approve").disabled = busy || pendingApproval === null;
  byId("refuse").disabled = busy || pendingApproval === null;
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll("button, input, textarea, select").forEach((element) => {
    element.disabled = busy;
  });
  if (!busy) syncActionButtons();
}

function money(value) {
  return `${value.currency} ${value.amount}`;
}

function showPage(name) {
  document.querySelectorAll(".page").forEach((page) => page.classList.remove("active"));
  document.querySelectorAll(".nav").forEach((button) => button.classList.remove("active"));
  byId(`page-${name}`).classList.add("active");
  document.querySelector(`.nav[data-page="${name}"]`).classList.add("active");
  if (name === "history") refreshHistory();
  if (name === "settings") loadSettings();
}

document.querySelectorAll(".nav").forEach((button) => {
  button.addEventListener("click", () => showPage(button.dataset.page));
});

function renderPreview(preview) {
  activePreview = preview;
  pendingApproval = null;
  byId("preview").hidden = false;
  byId("result").hidden = true;
  byId("approval").hidden = true;
  byId("destination").textContent = preview.destination_is_local
    ? `${preview.destination}（只在本機 / local only）`
    : preview.destination;
  byId("sensitivity").textContent = preview.sensitivity;
  byId("estimated-cost").textContent = money(preview.estimated_cost);
  byId("policy-badge").textContent = preview.policy_action;
  byId("policy-badge").dataset.state = preview.state === "blocked" ? "blocked" : "allowed";
  byId("policy-note").textContent = preview.policy_justification;
  byId("outbound").textContent = preview.destination_is_local
    ? "沒有內容離開此電腦。 / No content leaves this computer."
    : preview.outbound_text || "政策不允許傳送。 / Policy does not allow sending.";
  const redactions = byId("redactions");
  redactions.replaceChildren();
  if (!preview.redactions.length) {
    redactions.textContent = "沒有偵測到需取代的資料 / No replacements detected";
  } else {
    preview.redactions.forEach((item) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${item.type} → ${item.token}`;
      redactions.appendChild(chip);
    });
  }
  syncActionButtons();
  byId("preview").scrollIntoView({ behavior: "smooth", block: "start" });
}

byId("prepare").addEventListener("click", async () => {
  const instruction = byId("instruction").value.trim();
  if (!instruction) {
    setStatus("請先輸入指示。 / Enter an instruction first.", "error");
    return;
  }
  activePreview = null;
  pendingApproval = null;
  byId("preview").hidden = true;
  byId("approval").hidden = true;
  byId("result").hidden = true;
  setBusy(true);
  setStatus("正在本機分類及遮蔽資料… / Classifying and redacting locally…");
  try {
    const preview = await rpc("task_prepare", {
      instruction,
      requester: "desktop-user",
      risk_class: byId("risk-class").value,
      action_description: byId("action-description").value.trim() || null,
      context_path: byId("context-file").value || null,
    });
    renderPreview(preview);
    setStatus("預覽已準備；尚未呼叫模型。 / Preview ready; no model called yet.", "ok");
  } catch (error) {
    setStatus(errorMessage(error), "error");
  } finally {
    setBusy(false);
  }
});

function renderOutcome(outcome) {
  if (outcome.kind === "approval_required") {
    pendingApproval = outcome.approval;
    byId("approval").hidden = false;
    byId("approval-action").textContent = `${outcome.approval.risk_class}: ${outcome.approval.action_description}`;
    byId("approval-cost").textContent = `預計模型成本 / Estimated model cost: ${money(outcome.preview.estimated_cost)}`;
    setStatus("工作正等候人工批准。 / Task is waiting for human approval.", "warning");
    return;
  }
  if (outcome.kind === "cancelled") {
    activePreview = null;
    pendingApproval = null;
    byId("approval").hidden = true;
    setStatus("工作已拒絕及取消。 / Task refused and cancelled.", "warning");
    return;
  }
  activePreview = null;
  pendingApproval = null;
  byId("approval").hidden = true;
  byId("result").hidden = false;
  byId("result-text").textContent = outcome.text;
  byId("result-meta").textContent = `${outcome.provider}/${outcome.model} · ${money(outcome.cost)}${outcome.cost_is_complete ? "" : "（最低估算 / floor）"}`;
  setStatus("工作已完成。 / Task completed.", "ok");
  byId("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

byId("execute").addEventListener("click", async () => {
  if (!activePreview) return;
  setBusy(true);
  setStatus("正在執行工作… / Running task…");
  try {
    renderOutcome(await rpc("task_execute", { task_id: activePreview.task_id }));
  } catch (error) {
    setStatus(errorMessage(error), "error");
  } finally {
    setBusy(false);
  }
});

async function decide(approved) {
  if (!pendingApproval || !activePreview) return;
  setBusy(true);
  try {
    renderOutcome(
      await rpc("approval_decide", {
        task_id: activePreview.task_id,
        approval_id: pendingApproval.id,
        approved,
        decided_by: "desktop-user",
      }),
    );
    pendingApproval = null;
  } catch (error) {
    setStatus(errorMessage(error), "error");
  } finally {
    setBusy(false);
  }
}

byId("approve").addEventListener("click", () => decide(true));
byId("refuse").addEventListener("click", () => decide(false));

async function loadFiles() {
  try {
    const result = await rpc("connector_list");
    const select = byId("context-file");
    const selected = select.value;
    select.replaceChildren(new Option("不使用文件 / No file", ""));
    result.files.forEach((file) => select.add(new Option(file, file)));
    select.value = result.files.includes(selected) ? selected : "";
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

function addListItem(parent, title, detail) {
  const item = document.createElement("div");
  item.className = "list-item";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const text = document.createElement("span");
  text.textContent = detail;
  item.append(heading, text);
  parent.appendChild(item);
}

async function refreshHistory() {
  try {
    const [tasks, audit] = await Promise.all([rpc("tasks_list"), rpc("audit_list")]);
    const taskList = byId("task-list");
    taskList.replaceChildren();
    tasks.tasks.forEach((task) => addListItem(taskList, task.goal, `${task.state} · ${money(task.total_cost)} · ${task.model_calls} call(s)`));
    if (!tasks.tasks.length) taskList.textContent = "尚未有工作 / No tasks yet";
    const auditList = byId("audit-list");
    auditList.replaceChildren();
    audit.events.slice().reverse().forEach((event) => addListItem(auditList, `#${event.sequence} ${event.action}`, `${event.result}${event.target ? ` · ${event.target}` : ""}${event.destination ? ` · ${event.destination}` : ""}`));
    byId("audit-state").textContent = audit.verified ? "完整 / Verified" : "驗證失敗 / Verification failed";
    byId("audit-state").dataset.state = audit.verified ? "allowed" : "blocked";
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

byId("refresh-history").addEventListener("click", refreshHistory);

const settingFields = {
  provider: "provider",
  provider_model: "provider-model",
  hosted_endpoint: "hosted-endpoint",
  local_endpoint: "local-endpoint",
  local_model: "local-model",
  input_per_mtok: "input-price",
  output_per_mtok: "output-price",
  price_source: "price-source",
  price_checked_on: "price-date",
  per_task_budget_usd: "task-budget",
  monthly_budget_usd: "monthly-budget",
  max_context_tokens: "context-tokens",
  reserve_reply_tokens: "reply-tokens",
  connector_folder: "connector-folder",
  connector_encoding: "connector-encoding",
};

async function loadSettings() {
  try {
    const settings = await rpc("settings_get");
    Object.entries(settingFields).forEach(([key, id]) => { byId(id).value = settings[key] || ""; });
    byId("secret-state").textContent = settings.secret_storage_available
      ? `${settings.has_api_key ? "已安全儲存金鑰" : "未儲存金鑰"} / ${settings.secret_storage_backend}`
      : "安全金鑰儲存不可用；不會以明文儲存。 / Secure key storage unavailable; plaintext fallback is disabled.";
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

byId("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const settings = {};
  Object.entries(settingFields).forEach(([key, id]) => { settings[key] = byId(id).value.trim(); });
  const apiKey = byId("api-key").value;
  setBusy(true);
  try {
    await rpc("settings_update", { settings, api_key: apiKey || null });
    byId("api-key").value = "";
    setStatus("設定已儲存。 / Settings saved.", "ok");
    await Promise.all([loadSettings(), loadFiles()]);
  } catch (error) {
    setStatus(errorMessage(error), "error");
  } finally {
    setBusy(false);
  }
});

byId("delete-key").addEventListener("click", async () => {
  setBusy(true);
  try {
    await rpc("settings_update", { settings: {}, delete_api_key: true });
    await loadSettings();
    setStatus("已刪除金鑰。 / Saved key deleted.", "ok");
  } catch (error) {
    setStatus(errorMessage(error), "error");
  } finally {
    setBusy(false);
  }
});

async function start() {
  setBusy(true);
  try {
    const health = await invoke("health");
    setStatus(`本機服務已啟動（protocol ${health.protocol_version}）。 / Local service ready.`, "ok");
    await Promise.all([loadSettings(), loadFiles()]);
  } catch (error) {
    setStatus(`無法啟動本機服務 / Could not start local service: ${errorMessage(error)}`, "error");
  } finally {
    setBusy(false);
  }
}

start();
