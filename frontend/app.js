const STORAGE_KEY = "ticket_triage_session_history_v1";
const MAX_HISTORY_ITEMS = 10;
const CORE_TRUNCATE_LIMIT = 4000;
const API_MAX_LIMIT = 10000;

const form = document.getElementById("triage-form");
const messageInput = document.getElementById("message-input");
const charCounter = document.getElementById("char-counter");
const triageBtn = document.getElementById("triage-btn");
const loadingState = document.getElementById("loading-state");
const errorState = document.getElementById("error-state");
const errorMessage = document.getElementById("error-message");
const resultCard = document.getElementById("result-card");
const resCategory = document.getElementById("res-category");
const resPriority = document.getElementById("res-priority");
const resReview = document.getElementById("res-review");
const resConfidence = document.getElementById("res-confidence");
const resVersion = document.getElementById("res-version");
const resWarning = document.getElementById("res-warning");
const resSummary = document.getElementById("res-summary");
const resReply = document.getElementById("res-reply");
const copyBtn = document.getElementById("copy-btn");
const historyList = document.getElementById("history-list");
const historyEmpty = document.getElementById("history-empty");
const historyCount = document.getElementById("history-count");

let isLoading = false;
let sessionHistory = loadSessionHistory();
let activeHistoryIndex = -1;

function loadSessionHistory() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.slice(0, MAX_HISTORY_ITEMS) : [];
  } catch {
    return [];
  }
}

function saveSessionHistory() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(sessionHistory));
  } catch {
    // Ignore storage quota errors in restricted browser modes
  }
}

function updateInputControls() {
  const length = messageInput.value.length;
  const isEmpty = messageInput.value.trim().length === 0;

  charCounter.textContent = `${length.toLocaleString()} / 10,000 characters`;
  charCounter.classList.remove("warn", "over");

  if (length > API_MAX_LIMIT) {
    charCounter.classList.add("over");
  } else if (length > CORE_TRUNCATE_LIMIT) {
    charCounter.classList.add("warn");
  }

  triageBtn.disabled = isEmpty || isLoading;
}

function setLoading(loading) {
  isLoading = loading;
  updateInputControls();
  loadingState.classList.toggle("hidden", !loading);
  if (loading) {
    errorState.classList.add("hidden");
  }
}

function showError(plainMessage) {
  errorMessage.textContent = plainMessage;
  errorState.classList.remove("hidden");
  resultCard.classList.add("hidden");
}

function mapApiError(status, payload) {
  if (status === 422) {
    const detailText = JSON.stringify(payload || "").toLowerCase();
    if (detailText.includes("empty")) {
      return "Message is empty. Please enter a support message.";
    }
    if (detailText.includes("10000") || detailText.includes("maximum")) {
      return "Message is too long (maximum 10,000 characters).";
    }
    return "Invalid message format. Please check your input and try again.";
  }
  if (status === 502) {
    return "Service unavailable, try again.";
  }
  return "Something went wrong while processing your request. Please try again.";
}

function renderResultCard(result) {
  errorState.classList.add("hidden");
  resultCard.classList.remove("hidden");

  resCategory.textContent = result.category.replace("_", " ");

  resPriority.textContent = result.priority;
  resPriority.className = `badge badge-priority priority-${result.priority}`;

  resReview.classList.toggle("hidden", !result.needs_review);

  const confidencePct = Math.round(result.confidence * 100);
  resConfidence.textContent = `Confidence: ${confidencePct}%`;
  resVersion.textContent = `Prompt ${result.prompt_version}`;

  if (result.warning) {
    resWarning.textContent = `Notice: ${result.warning}`;
    resWarning.classList.remove("hidden");
  } else {
    resWarning.classList.add("hidden");
  }

  resSummary.textContent = result.summary;
  resReply.textContent = result.reply_draft;
  copyBtn.textContent = "Copy reply";
}

function renderHistory() {
  historyCount.textContent = `${sessionHistory.length} / ${MAX_HISTORY_ITEMS}`;
  historyList.innerHTML = "";

  if (sessionHistory.length === 0) {
    historyEmpty.classList.remove("hidden");
    return;
  }

  historyEmpty.classList.add("hidden");

  sessionHistory.forEach((entry, index) => {
    const item = document.createElement("li");
    item.className = "history-item";
    if (index === activeHistoryIndex) {
      item.classList.add("active");
    }

    const topRow = document.createElement("div");
    topRow.className = "history-item-top";

    const catSpan = document.createElement("span");
    catSpan.textContent = entry.result.category.replace("_", " ");

    const prioSpan = document.createElement("span");
    prioSpan.textContent = entry.result.priority;

    topRow.appendChild(catSpan);
    topRow.appendChild(prioSpan);

    const summaryDiv = document.createElement("div");
    summaryDiv.className = "history-item-summary";
    summaryDiv.textContent = entry.result.summary;

    item.appendChild(topRow);
    item.appendChild(summaryDiv);

    item.addEventListener("click", () => {
      activeHistoryIndex = index;
      messageInput.value = entry.message;
      updateInputControls();
      renderResultCard(entry.result);
      renderHistory();
    });

    historyList.appendChild(item);
  });
}

async function handleTriageSubmit(event) {
  event.preventDefault();
  const rawMessage = messageInput.value;
  if (!rawMessage.trim() || isLoading) {
    return;
  }

  setLoading(true);

  try {
    const response = await fetch("/api/v1/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: rawMessage }),
    });

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      showError(mapApiError(response.status, data));
      return;
    }

    sessionHistory.unshift({
      message: rawMessage,
      result: data,
      timestamp: new Date().toISOString(),
    });
    sessionHistory = sessionHistory.slice(0, MAX_HISTORY_ITEMS);
    activeHistoryIndex = 0;

    saveSessionHistory();
    renderResultCard(data);
    renderHistory();
  } catch {
    showError("Network error: unable to reach the triage server.");
  } finally {
    setLoading(false);
  }
}

copyBtn.addEventListener("click", async () => {
  const replyText = resReply.textContent;
  if (!replyText) return;

  try {
    await navigator.clipboard.writeText(replyText);
    copyBtn.textContent = "Copied!";
    setTimeout(() => {
      copyBtn.textContent = "Copy reply";
    }, 1800);
  } catch {
    copyBtn.textContent = "Copy failed";
  }
});

messageInput.addEventListener("input", updateInputControls);
form.addEventListener("submit", handleTriageSubmit);

updateInputControls();
renderHistory();
