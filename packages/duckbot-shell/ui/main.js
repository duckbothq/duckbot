// The window's script.
//
// It calls four commands and renders their results. It holds no policy of its own: what
// is sensitive, what gets replaced and what may be sent are decided in Python, where
// they are tested. A rule implemented here as well would be a second, untested copy that
// drifts.
//
// Note what this file never receives: the mapping between placeholders and real values.
// A redaction comes back as a handle. The values stay in the sidecar.

const { invoke } = window.__TAURI__.core;

const status = document.getElementById("status");
const input = document.getElementById("input");
const output = document.getElementById("output");
const note = document.getElementById("note");
const outputSection = document.getElementById("output-section");
const classifyButton = document.getElementById("classify");
const redactButton = document.getElementById("redact");

function setStatus(text, state) {
  status.textContent = text;
  if (state) {
    status.dataset.state = state;
  } else {
    delete status.dataset.state;
  }
}

function setBusy(busy) {
  classifyButton.disabled = busy;
  redactButton.disabled = busy;
}

async function start() {
  setBusy(true);
  try {
    const health = await invoke("health");
    setStatus(`本機服務已啟動（protocol ${health.protocol_version}）。冇任何資料離開呢部機。`);
  } catch (error) {
    setStatus(`啟動唔到本機服務：${error}`, "error");
    return;
  }
  setBusy(false);
}

classifyButton.addEventListener("click", async () => {
  setBusy(true);
  try {
    const result = await invoke("classify", { text: input.value });
    const kinds = result.entities.map((e) => e.type);
    const summary = kinds.length
      ? `${kinds.length} 項：${[...new Set(kinds)].join("、")}`
      : "冇偵測到敏感資料";
    outputSection.hidden = false;
    output.textContent = input.value;
    note.textContent = `敏感程度 ${result.sensitivity}，${summary}。`;
  } catch (error) {
    note.textContent = String(error);
  } finally {
    setBusy(false);
  }
});

redactButton.addEventListener("click", async () => {
  setBusy(true);
  try {
    const result = await invoke("redact", { text: input.value });
    outputSection.hidden = false;
    output.textContent = result.redacted_text;
    note.textContent =
      `敏感程度 ${result.sensitivity}，已遮蔽 ${result.tokens.length} 個值。` +
      "真實數值留喺本機，呢個視窗只係攞到一個 handle。";
  } catch (error) {
    note.textContent = String(error);
  } finally {
    setBusy(false);
  }
});

start();
