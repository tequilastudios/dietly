const state = {
  token: localStorage.getItem("dietly_token"),
  user: JSON.parse(localStorage.getItem("dietly_user") || "null"),
  selectedDay: new Date().toISOString().slice(0, 10),
  lastAiAnalysis: null,
  editingMealId: null,
  editingMealSource: "manual",
  aiLoadingCount: 0,
  needs: null,
  water: null,
  mealsSnapshot: null,
  timelineCacheKey: null,
  chatSessions: [],
  activeChatId: null,
  chatPending: false,
  speechRecognizer: null,
  speechListening: false,
  manualEstimateTimer: null,
  manualEstimateRequestId: 0,
  lastManualEstimate: null,
};

const $ = (id) => document.getElementById(id);
const MEAL_TYPE_LABELS = {
  breakfast: "Colazione",
  lunch: "Pranzo",
  dinner: "Cena",
  snack: "Snack",
  other: "Altro",
};

function showFlash(message, level = "info") {
  const flash = $("flash");
  flash.classList.remove("hidden", "error", "success");
  flash.classList.add(level === "error" ? "error" : "success");
  flash.textContent = message;

  setTimeout(() => flash.classList.add("hidden"), 3500);
}

function updateAiIndicator() {
  const pill = $("aiStatusPill");
  if (!pill) return;
  pill.classList.toggle("hidden", state.aiLoadingCount === 0);
}

function startAiTask() {
  state.aiLoadingCount += 1;
  updateAiIndicator();
}

function endAiTask() {
  state.aiLoadingCount = Math.max(0, state.aiLoadingCount - 1);
  updateAiIndicator();
}

function showAiOverlay(message) {
  startAiTask();
  const overlay = $("aiOverlay");
  const text = $("aiOverlayText");
  if (!overlay || !text) return;
  text.textContent = message || "Dietly AI sta elaborando...";
  overlay.classList.remove("hidden");
}

function hideAiOverlay() {
  endAiTask();
  if (state.aiLoadingCount > 0) return;
  const overlay = $("aiOverlay");
  if (overlay) {
    overlay.classList.add("hidden");
  }
}

async function api(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (!isForm && body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(path, {
    method,
    headers,
    body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401) {
    logout();
    throw new Error("Sessione scaduta. Effettua nuovamente il login.");
  }

  if (!response.ok) {
    let detail = "Errore durante la richiesta";
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }

  return response.status === 204 ? null : response.json();
}

function setAuthData(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("dietly_token", token);
  localStorage.setItem("dietly_user", JSON.stringify(user));
}

function clearAuthData() {
  const userId = state.user?.id;
  state.token = null;
  state.user = null;
  state.chatSessions = [];
  state.activeChatId = null;
  state.chatPending = false;
  localStorage.removeItem("dietly_token");
  localStorage.removeItem("dietly_user");
  localStorage.removeItem("dietly_chat_history");
  if (userId) {
    localStorage.removeItem(`dietly_chat_sessions_${userId}`);
    localStorage.removeItem(`dietly_chat_active_${userId}`);
  }
}

function syncNavAuthState(isLogged) {
  const quickSettingsLink = $("quickSettingsLink");

  document.querySelectorAll(".auth-only").forEach((element) => {
    element.classList.toggle("hidden", !isLogged);
  });
  document.querySelectorAll(".guest-only").forEach((element) => {
    element.classList.toggle("hidden", isLogged);
  });
  if (quickSettingsLink) {
    quickSettingsLink.classList.toggle("hidden", !isLogged);
  }
}

function closeMenu() {
  const menu = $("mainMenu");
  const toggleBtn = $("navToggleBtn");
  if (!menu || !toggleBtn) return;

  menu.classList.remove("open");
  toggleBtn.classList.remove("open");
  toggleBtn.setAttribute("aria-expanded", "false");
}

function toggleMenu() {
  const menu = $("mainMenu");
  const toggleBtn = $("navToggleBtn");
  if (!menu || !toggleBtn) return;

  const willOpen = !menu.classList.contains("open");
  menu.classList.toggle("open", willOpen);
  toggleBtn.classList.toggle("open", willOpen);
  toggleBtn.setAttribute("aria-expanded", String(willOpen));
}

function logout() {
  clearAuthData();
  syncNavAuthState(false);
  closeMenu();
  toggleChat(false);
  const landing = $("landingSection");
  if (landing) {
    landing.classList.remove("hidden");
  }
  $("dashboard").classList.add("hidden");
  $("authSection").classList.remove("hidden");
}

function applyAuthState() {
  const isLogged = Boolean(state.token && state.user);
  syncNavAuthState(isLogged);

  const landing = $("landingSection");
  if (landing) {
    landing.classList.toggle("hidden", isLogged);
  }

  if (!isLogged) {
    closeMenu();
    $("dashboard").classList.add("hidden");
    $("authSection").classList.remove("hidden");
    return;
  }

  $("authSection").classList.add("hidden");
  $("dashboard").classList.remove("hidden");
  $("welcomeTitle").textContent = `Ciao ${state.user.full_name}`;
  loadChatHistory();
}

function nowForDatetimeLocal() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function nowForApiDateTime() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return `${now.toISOString().slice(0, 16)}:00`;
}

function toDatetimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}

function resetMealFormToCreate() {
  state.editingMealId = null;
  state.editingMealSource = "manual";
  state.lastAiAnalysis = null;
  state.lastManualEstimate = null;
  state.manualEstimateRequestId = 0;

  $("mealFormTitle").textContent = "Registra pasto";
  $("saveMealBtn").textContent = "Salva pasto";
  $("cancelEditMealBtn").classList.add("hidden");

  $("mealForm").reset();
  $("consumedAt").value = nowForDatetimeLocal();
  resetManualItems();
  setManualEstimateStatus("Aggiungi ingredienti per stima macro automatica.");
}

function valueOrNull(value) {
  if (value === "" || value === null || value === undefined) return null;
  return Number(value);
}

function setManualEstimateStatus(message = "", isError = false) {
  const target = $("manualEstimateStatus");
  if (!target) return;
  target.textContent = message;
  target.style.color = isError ? "var(--danger)" : "";
}

function createMealItemRow(item = {}) {
  const row = document.createElement("div");
  row.className = "meal-item-row";
  row.innerHTML = `
    <label>Ingrediente
      <input class="meal-item-name" type="text" placeholder="Es: pasta, pollo, olio EVO" value="${escapeHtml(item.name || "")}" />
    </label>
    <label>Quantita/porzioni
      <input class="meal-item-qty" type="text" placeholder="Es: 100 g, 1 porzione, 2 cucchiai" value="${escapeHtml(item.quantity || "")}" />
    </label>
    <button class="meal-item-remove" type="button" aria-label="Rimuovi ingrediente">×</button>
  `;

  const nameInput = row.querySelector(".meal-item-name");
  const qtyInput = row.querySelector(".meal-item-qty");
  const removeBtn = row.querySelector(".meal-item-remove");

  const onManualInput = () => {
    if (state.lastAiAnalysis) {
      state.lastAiAnalysis = null;
      setManualEstimateStatus("Modalita manuale ingredienti attivata.");
    }
    scheduleManualEstimate();
  };

  nameInput?.addEventListener("input", onManualInput);
  qtyInput?.addEventListener("input", onManualInput);
  removeBtn?.addEventListener("click", () => {
    row.remove();
    if (!$("mealItemsList")?.children.length) {
      addMealItemRow();
    }
    scheduleManualEstimate();
  });

  return row;
}

function addMealItemRow(item = {}) {
  const list = $("mealItemsList");
  if (!list) return;
  list.appendChild(createMealItemRow(item));
}

function resetManualItems(items = []) {
  const list = $("mealItemsList");
  if (!list) return;
  list.innerHTML = "";
  if (items.length) {
    items.forEach((item) => addMealItemRow(item));
  } else {
    addMealItemRow();
  }
  setManualEstimateStatus("");
}

function collectManualItems() {
  const list = $("mealItemsList");
  if (!list) return [];
  return Array.from(list.querySelectorAll(".meal-item-row"))
    .map((row) => ({
      name: (row.querySelector(".meal-item-name")?.value || "").trim(),
      quantity: (row.querySelector(".meal-item-qty")?.value || "").trim(),
    }))
    .filter((item) => item.name);
}

async function runManualEstimate() {
  if (state.lastAiAnalysis || state.editingMealId) return;
  const items = collectManualItems();
  if (!items.length) {
    state.lastManualEstimate = null;
    setManualEstimateStatus("Aggiungi almeno un ingrediente per avviare la stima.");
    return;
  }

  const requestId = Date.now();
  state.manualEstimateRequestId = requestId;
  setManualEstimateStatus("Stima nutrienti in corso...");
  startAiTask();
  try {
    const result = await api("/api/meals/estimate-manual", {
      method: "POST",
      body: {
        items,
        hint: $("mealNotes").value || null,
        meal_type: $("mealType").value || null,
      },
    });
    if (state.manualEstimateRequestId !== requestId) {
      return;
    }

    state.lastManualEstimate = { ...result, items };
    $("mealCalories").value = result.calories ?? "";
    $("mealProteins").value = result.proteins ?? "";
    $("mealCarbs").value = result.carbs ?? "";
    $("mealFats").value = result.fats ?? "";
    if (!$("foodName").value.trim() || $("foodName").value.trim().toLowerCase() === "pasto composito") {
      $("foodName").value = result.food_name || "Pasto composito";
    }
    if (!$("mealNotes").value.trim() && result.notes) {
      $("mealNotes").value = result.notes;
    }
    const confidence = Math.round((result.confidence || 0) * 100);
    setManualEstimateStatus(`Stima aggiornata automaticamente (${confidence}% confidenza).`);
  } catch (error) {
    if (state.manualEstimateRequestId === requestId) {
      state.lastManualEstimate = null;
      setManualEstimateStatus(error.message || "Errore durante la stima manuale.", true);
    }
  } finally {
    endAiTask();
  }
}

function scheduleManualEstimate() {
  if (state.lastAiAnalysis || state.editingMealId) return;
  if (state.manualEstimateTimer) {
    clearTimeout(state.manualEstimateTimer);
  }
  state.manualEstimateTimer = setTimeout(() => {
    runManualEstimate().catch(() => {
      // error is already handled in runManualEstimate
    });
  }, 650);
}

function formatLocalTime(value) {
  const dt = new Date(value);
  return dt.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

function formatNumber(value) {
  return Number(value || 0).toFixed(1);
}

function normalizeMealType(value) {
  if (!value) return null;
  const normalized = String(value).trim().toLowerCase();
  if (MEAL_TYPE_LABELS[normalized]) return normalized;
  return null;
}

function mealTypeLabel(value) {
  return MEAL_TYPE_LABELS[value] || value || "Altro";
}

function inferMealTypeFromNow() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 11) return "breakfast";
  if (hour >= 11 && hour < 16) return "lunch";
  if (hour >= 16 && hour < 19) return "snack";
  if (hour >= 19 && hour < 23) return "dinner";
  return "other";
}

function applyAnalysisToMealForm(result, hint = "") {
  const detectedMealType = normalizeMealType(result.meal_type) || inferMealTypeFromNow();

  state.lastManualEstimate = null;
  state.manualEstimateRequestId = Date.now();
  $("mealType").value = detectedMealType;
  $("foodName").value = result.food_name || $("foodName").value;
  $("mealCalories").value = result.calories ?? "";
  $("mealProteins").value = result.proteins ?? "";
  $("mealCarbs").value = result.carbs ?? "";
  $("mealFats").value = result.fats ?? "";
  $("consumedAt").value = nowForDatetimeLocal();

  if (result.notes) {
    $("mealNotes").value = result.notes;
  } else if (hint) {
    $("mealNotes").value = hint;
  }

  resetManualItems();
  setManualEstimateStatus("Modalita foto AI attiva: la stima manuale ingredienti e sospesa.");
}

async function handleLogin(event) {
  event.preventDefault();

  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: {
        email: $("loginEmail").value,
        password: $("loginPassword").value,
      },
    });

    setAuthData(data.access_token, data.user);
    applyAuthState();
    await loadDashboard();
    showFlash("Login effettuato con successo.");
  } catch (error) {
    showFlash(error.message, "error");
  }
}

async function handleRegister(event) {
  event.preventDefault();

  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: {
        full_name: $("registerName").value,
        email: $("registerEmail").value,
        password: $("registerPassword").value,
      },
    });

    setAuthData(data.access_token, data.user);
    applyAuthState();
    await loadDashboard();
    showFlash("Account creato con successo.");
  } catch (error) {
    showFlash(error.message, "error");
  }
}

async function loadRoutine() {
  const routine = await api("/api/routine");

  $("breakfastTime").value = routine.breakfast_time?.slice(0, 5) || "08:00";
  $("lunchTime").value = routine.lunch_time?.slice(0, 5) || "13:00";
  $("dinnerTime").value = routine.dinner_time?.slice(0, 5) || "20:00";
  $("dayEndTime").value = routine.day_end_time?.slice(0, 5) || "";

  $("targetCalories").value = routine.calorie_target ?? "";
  $("targetProteins").value = routine.protein_target ?? "";
  $("targetCarbs").value = routine.carbs_target ?? "";
  $("targetFats").value = routine.fats_target ?? "";
}

async function saveRoutine(event) {
  event.preventDefault();

  try {
    const data = await api("/api/routine", {
      method: "PUT",
      body: {
        breakfast_time: $("breakfastTime").value || null,
        lunch_time: $("lunchTime").value || null,
        dinner_time: $("dinnerTime").value || null,
        day_end_time: $("dayEndTime").value || null,
        calorie_target: valueOrNull($("targetCalories").value),
        protein_target: valueOrNull($("targetProteins").value),
        carbs_target: valueOrNull($("targetCarbs").value),
        fats_target: valueOrNull($("targetFats").value),
      },
    });

    if (data?.ai_applied) {
      showFlash(data.ai_note ? `Routine ottimizzata: ${data.ai_note}` : "Routine ottimizzata da Dietly AI.");
    } else {
      showFlash("Routine aggiornata.");
    }
    await loadRoutine();
    await loadNeeds();
    await loadSummary(false);
    await loadTimeline({ force: true });
  } catch (error) {
    showFlash(error.message, "error");
  }
}

async function analyzeImageAndFill({ fileInputId, hintInputId }) {
  const fileInput = $(fileInputId);
  const file = fileInput.files?.[0];
  const hint = ($(hintInputId)?.value || "").trim();

  if (!file) {
    showFlash("Seleziona prima una foto del pasto.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("image", file);
  formData.append("hint", hint);

  if (state.editingMealId) {
    resetMealFormToCreate();
  }

  showAiOverlay("Analisi immagine in corso...");
  try {
    const result = await api("/api/meals/analyze-image", {
      method: "POST",
      body: formData,
      isForm: true,
    });

    state.lastAiAnalysis = result;
    applyAnalysisToMealForm(result, hint);
    $("mealSection").scrollIntoView({ behavior: "smooth", block: "start" });

    const detectedMealType = normalizeMealType(result.meal_type) || inferMealTypeFromNow();
    showFlash(
      `Analisi completata: ${mealTypeLabel(detectedMealType)} rilevato (${Math.round(result.confidence * 100)}% confidenza).`
    );
  } catch (error) {
    showFlash(error.message, "error");
  } finally {
    hideAiOverlay();
  }
}

async function handleQuickCapture(event) {
  event.preventDefault();
  await analyzeImageAndFill({ fileInputId: "quickImage", hintInputId: "quickHint" });
}

async function saveMeal(event) {
  event.preventDefault();

  const consumedAtValue = $("consumedAt").value;
  const consumedAt = consumedAtValue ? `${consumedAtValue}:00` : nowForApiDateTime();
  const isEdit = Boolean(state.editingMealId);
  const endpoint = isEdit ? `/api/meals/${state.editingMealId}` : "/api/meals";
  const method = isEdit ? "PUT" : "POST";
  const aiPayloadData = state.lastAiAnalysis || state.lastManualEstimate;
  const source = aiPayloadData ? "ai" : isEdit ? state.editingMealSource : "manual";

  try {
    await api(endpoint, {
      method,
      body: {
        meal_type: $("mealType").value,
        consumed_at: consumedAt,
        food_name: $("foodName").value,
        calories: valueOrNull($("mealCalories").value) ?? 0,
        proteins: valueOrNull($("mealProteins").value) ?? 0,
        carbs: valueOrNull($("mealCarbs").value) ?? 0,
        fats: valueOrNull($("mealFats").value) ?? 0,
        notes: $("mealNotes").value || null,
        source,
        ai_payload: aiPayloadData ? JSON.stringify(aiPayloadData) : null,
      },
    });

    showFlash(isEdit ? "Pasto aggiornato." : "Pasto registrato.");
    resetMealFormToCreate();

    await loadMeals();
    await loadNeeds();
    await loadSummary(false);
    await loadTimeline({ force: true });
  } catch (error) {
    showFlash(error.message, "error");
  }
}

function startMealEdit(meal) {
  state.editingMealId = meal.id;
  state.editingMealSource = meal.source || "manual";
  state.lastAiAnalysis = null;
  state.lastManualEstimate = null;
  state.manualEstimateRequestId = Date.now();

  $("mealFormTitle").textContent = "Modifica pasto";
  $("saveMealBtn").textContent = "Aggiorna pasto";
  $("cancelEditMealBtn").classList.remove("hidden");

  $("mealType").value = meal.meal_type;
  $("consumedAt").value = toDatetimeLocal(meal.consumed_at);
  $("foodName").value = meal.food_name || "";
  $("mealCalories").value = meal.calories ?? "";
  $("mealProteins").value = meal.proteins ?? "";
  $("mealCarbs").value = meal.carbs ?? "";
  $("mealFats").value = meal.fats ?? "";
  $("mealNotes").value = meal.notes || "";
  resetManualItems();
  setManualEstimateStatus("Modifica aperta: la stima ingredienti automatica e disattivata.");

  $("mealSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteMeal(mealId) {
  const confirmed = window.confirm("Eliminare definitivamente questo pasto dal registro?");
  if (!confirmed) return;

  try {
    await api(`/api/meals/${mealId}`, { method: "DELETE" });
    showFlash("Pasto eliminato.");

    if (state.editingMealId === mealId) {
      resetMealFormToCreate();
    }

    await loadMeals();
    await loadSummary(false);
  } catch (error) {
    showFlash(error.message, "error");
  }
}

function renderTotals(totals) {
  $("totalsBar").innerHTML = `
    <span><strong>${formatNumber(totals.calories)}</strong> kcal</span>
    <span><strong>${formatNumber(totals.proteins)}</strong> g proteine</span>
    <span><strong>${formatNumber(totals.carbs)}</strong> g carboidrati</span>
    <span><strong>${formatNumber(totals.fats)}</strong> g grassi</span>
  `;
}

function renderMeals(meals) {
  const tbody = $("mealsBody");
  tbody.innerHTML = "";

  if (!meals.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty">Nessun pasto registrato in questa data.</td></tr>';
    return;
  }

  meals.forEach((meal) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td data-label="Ora">${formatLocalTime(meal.consumed_at)}</td>
      <td data-label="Tipo">${mealTypeLabel(meal.meal_type)}</td>
      <td data-label="Pasto">${meal.food_name}</td>
      <td data-label="Kcal">${formatNumber(meal.calories)}</td>
      <td data-label="Proteine">${formatNumber(meal.proteins)}</td>
      <td data-label="Carboidrati">${formatNumber(meal.carbs)}</td>
      <td data-label="Grassi">${formatNumber(meal.fats)}</td>
      <td data-label="Fonte">${meal.source}</td>
      <td class="row-actions" data-label="Azioni">
        <button class="table-btn" type="button" data-action="edit" data-id="${meal.id}">Modifica</button>
        <button class="table-btn danger" type="button" data-action="delete" data-id="${meal.id}">Elimina</button>
      </td>
    `;

    row.querySelector('[data-action="edit"]').addEventListener("click", () => startMealEdit(meal));
    row.querySelector('[data-action="delete"]').addEventListener("click", () => deleteMeal(meal.id));
    tbody.appendChild(row);
  });
}

async function loadMeals() {
  const day = state.selectedDay;
  const data = await api(`/api/meals?day=${encodeURIComponent(day)}`);
  renderTotals(data.totals);
  renderMeals(data.meals);
  state.mealsSnapshot = {
    totals: data.totals,
    count: data.meals.length,
    lastAt: data.meals.length ? data.meals[data.meals.length - 1].consumed_at : null,
  };
  return data;
}

function timelineCacheKey(day) {
  const userId = state.user?.id || "guest";
  return `dietly_timeline_${userId}_${day}`;
}

function getCurrentPhaseKey(routine) {
  const times = [routine.breakfast, routine.lunch, routine.dinner, routine.end].filter(Boolean);
  if (!times.length) return "unknown";

  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  let index = 0;
  times.forEach((timeValue, idx) => {
    const [h, m] = timeValue.split(":").map(Number);
    if (Number.isFinite(h) && Number.isFinite(m)) {
      const minutes = h * 60 + m;
      if (nowMinutes >= minutes) {
        index = idx;
      }
    }
  });
  return `phase_${index}`;
}

function buildTimelineSignature() {
  const routine = {
    breakfast: $("breakfastTime").value || "",
    lunch: $("lunchTime").value || "",
    dinner: $("dinnerTime").value || "",
    end: $("dayEndTime").value || "",
  };
  const targets = {
    calories: $("targetCalories").value || "",
    proteins: $("targetProteins").value || "",
    carbs: $("targetCarbs").value || "",
    fats: $("targetFats").value || "",
  };
  const totals = state.mealsSnapshot?.totals || state.needs?.totals || {};
  const mealCount = state.mealsSnapshot?.count || 0;
  const lastMealAt = state.mealsSnapshot?.lastAt || "";
  const needsKey = state.needs?.needs ? JSON.stringify(state.needs.needs) : "";
  const phaseKey = getCurrentPhaseKey(routine);
  return JSON.stringify({
    day: state.selectedDay,
    routine,
    targets,
    totals,
    mealCount,
    lastMealAt,
    needsKey,
    phaseKey,
  });
}

function getCachedTimeline(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setCachedTimeline(key, signature, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ signature, data }));
  } catch {
    // ignore storage errors
  }
}

function chatStorageKey() {
  const userId = state.user?.id || "guest";
  return `dietly_chat_sessions_${userId}`;
}

function activeChatStorageKey() {
  const userId = state.user?.id || "guest";
  return `dietly_chat_active_${userId}`;
}

function sanitizeChatSession(session) {
  return {
    id: String(session.id),
    title: (session.title || "Nuova chat").slice(0, 80),
    updated_at: session.updated_at || new Date().toISOString(),
    messages: Array.isArray(session.messages)
      ? session.messages
          .filter((message) => message && typeof message.content === "string" && message.role)
          .slice(-50)
      : [],
  };
}

function createChatSession(title = "Nuova chat") {
  return sanitizeChatSession({
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    title,
    updated_at: new Date().toISOString(),
    messages: [],
  });
}

function getChatSessionById(sessionId) {
  if (!sessionId) return null;
  return state.chatSessions.find((session) => session.id === sessionId) || null;
}

function getActiveChatSession() {
  if (!state.activeChatId) return null;
  return state.chatSessions.find((session) => session.id === state.activeChatId) || null;
}

function ensureActiveChatSession() {
  if (!state.chatSessions.length) {
    const created = createChatSession();
    state.chatSessions = [created];
    state.activeChatId = created.id;
    return created;
  }
  const current = getActiveChatSession();
  if (current) return current;
  state.activeChatId = state.chatSessions[0].id;
  return state.chatSessions[0];
}

function buildChatTitle(message) {
  const clean = String(message || "").replace(/\s+/g, " ").trim();
  if (!clean) return "Nuova chat";
  return clean.length > 48 ? `${clean.slice(0, 48)}...` : clean;
}

function loadChatHistory() {
  try {
    const rawSessions = localStorage.getItem(chatStorageKey());
    const parsedSessions = rawSessions ? JSON.parse(rawSessions) : [];
    if (Array.isArray(parsedSessions) && parsedSessions.length) {
      state.chatSessions = parsedSessions.map(sanitizeChatSession).slice(-20);
    } else {
      state.chatSessions = [];
    }
  } catch {
    state.chatSessions = [];
  }

  try {
    const migratedRaw = localStorage.getItem("dietly_chat_history");
    const migrated = migratedRaw ? JSON.parse(migratedRaw) : [];
    if (Array.isArray(migrated) && migrated.length && !state.chatSessions.length) {
      const migratedSession = createChatSession("Chat precedente");
      migratedSession.messages = migrated
        .filter((message) => message && typeof message.content === "string" && message.role)
        .map((message) => ({
          role: message.role === "assistant" ? "assistant" : "user",
          content: String(message.content),
        }))
        .slice(-50);
      migratedSession.updated_at = new Date().toISOString();
      state.chatSessions = [sanitizeChatSession(migratedSession)];
      localStorage.removeItem("dietly_chat_history");
    }
  } catch {
    // ignore migration errors
  }

  try {
    const activeId = localStorage.getItem(activeChatStorageKey());
    state.activeChatId = activeId || null;
  } catch {
    state.activeChatId = null;
  }

  ensureActiveChatSession();
  saveChatHistory();
  renderChatSessionSelect();
  renderChatMessages();
  updateMicButton();
}

function saveChatHistory() {
  try {
    state.chatSessions = state.chatSessions.map(sanitizeChatSession).slice(-20);
    localStorage.setItem(chatStorageKey(), JSON.stringify(state.chatSessions));
    if (state.activeChatId) {
      localStorage.setItem(activeChatStorageKey(), state.activeChatId);
    }
  } catch {
    // ignore
  }
}

function renderChatSessionSelect() {
  const select = $("chatSessionSelect");
  if (!select) return;

  const sessions = [...state.chatSessions].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  );

  select.innerHTML = "";
  sessions.forEach((session) => {
    const option = document.createElement("option");
    option.value = session.id;
    const dateLabel = new Date(session.updated_at).toLocaleString("it-IT", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    option.textContent = `${session.title} • ${dateLabel}`;
    option.selected = session.id === state.activeChatId;
    select.appendChild(option);
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatInlineMarkdown(line) {
  let html = escapeHtml(line);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return html;
}

function formatAssistantMessage(text) {
  const lines = String(text || "").replaceAll("\r", "").split("\n");
  const html = [];
  let listOpen = false;

  const closeList = () => {
    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      return;
    }

    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      closeList();
      html.push(`<h4>${formatInlineMarkdown(heading[1])}</h4>`);
      return;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/) || line.match(/^\d+\.\s+(.+)$/);
    if (bullet) {
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li>${formatInlineMarkdown(bullet[1])}</li>`);
      return;
    }

    closeList();
    html.push(`<p>${formatInlineMarkdown(line)}</p>`);
  });

  closeList();
  return html.length ? html.join("") : "<p>Nessuna risposta disponibile.</p>";
}

function renderChatMessages() {
  const container = $("chatMessages");
  if (!container) return;
  container.innerHTML = "";

  const session = ensureActiveChatSession();
  if (!session || !session.messages.length) {
    container.innerHTML = '<div class="chat-message bot">Ciao! Sono DietlyBot. Come posso aiutarti oggi?</div>';
    if (state.chatPending) {
      const pending = document.createElement("div");
      pending.className = "chat-message bot typing";
      pending.innerHTML =
        'DietlyBot sta scrivendo <span class="typing-dots"><span></span><span></span><span></span></span>';
      container.appendChild(pending);
    }
    return;
  }

  session.messages.forEach((msg) => {
    const bubble = document.createElement("div");
    bubble.className = `chat-message ${msg.role === "user" ? "user" : "bot"}`;
    if (msg.role === "assistant") {
      bubble.innerHTML = formatAssistantMessage(msg.content);
    } else {
      bubble.textContent = msg.content;
    }
    container.appendChild(bubble);
  });

  if (state.chatPending) {
    const pending = document.createElement("div");
    pending.className = "chat-message bot typing";
    pending.innerHTML =
      'DietlyBot sta scrivendo <span class="typing-dots"><span></span><span></span><span></span></span>';
    container.appendChild(pending);
  }

  container.scrollTop = container.scrollHeight;
}

function setChatPending(pending) {
  state.chatPending = pending;
  if (pending) {
    stopSpeechRecognition();
  }
  const input = $("chatInput");
  const sendBtn = $("chatSendBtn");
  const newBtn = $("chatNewBtn");
  const sessionSelect = $("chatSessionSelect");
  const micBtn = $("chatMicBtn");
  if (input) input.disabled = pending;
  if (sendBtn) sendBtn.disabled = pending;
  if (newBtn) newBtn.disabled = pending;
  if (sessionSelect) sessionSelect.disabled = pending;
  if (micBtn) micBtn.disabled = pending;
  renderChatMessages();
}

function updateMicButton() {
  const micBtn = $("chatMicBtn");
  if (!micBtn) return;
  micBtn.classList.toggle("listening", state.speechListening);
  micBtn.setAttribute("aria-label", state.speechListening ? "Interrompi dettatura" : "Parla con microfono");
}

function stopSpeechRecognition() {
  if (state.speechRecognizer) {
    try {
      state.speechRecognizer.stop();
    } catch {
      // ignore
    }
  }
}

function toggleSpeechRecognition() {
  if (state.speechListening) {
    stopSpeechRecognition();
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showFlash("Microfono non supportato da questo browser.", "error");
    return;
  }

  const input = $("chatInput");
  if (!input) return;

  const recognizer = new SpeechRecognition();
  recognizer.lang = "it-IT";
  recognizer.interimResults = true;
  recognizer.continuous = false;

  let baseText = input.value ? `${input.value.trim()} ` : "";

  recognizer.onstart = () => {
    state.speechListening = true;
    updateMicButton();
  };

  recognizer.onresult = (event) => {
    let transcript = "";
    for (let idx = event.resultIndex; idx < event.results.length; idx += 1) {
      transcript += event.results[idx][0].transcript || "";
    }
    input.value = `${baseText}${transcript}`.trim();
  };

  recognizer.onerror = () => {
    showFlash("Riconoscimento vocale non disponibile in questo momento.", "error");
  };

  recognizer.onend = () => {
    state.speechListening = false;
    updateMicButton();
  };

  state.speechRecognizer = recognizer;
  recognizer.start();
}

function openNewChatSession() {
  if (state.chatPending) return;
  const session = createChatSession("Nuova chat");
  state.chatSessions.push(session);
  state.activeChatId = session.id;
  saveChatHistory();
  renderChatSessionSelect();
  renderChatMessages();
  $("chatInput")?.focus();
}

function switchChatSession(sessionId) {
  if (!sessionId || state.chatPending) return;
  state.activeChatId = sessionId;
  saveChatHistory();
  renderChatSessionSelect();
  renderChatMessages();
}

function toggleChat(open) {
  const panel = $("chatPanel");
  if (!panel) return;
  panel.classList.toggle("hidden", !open);
  panel.setAttribute("aria-hidden", String(!open));
  if (open) {
    ensureActiveChatSession();
    renderChatSessionSelect();
    renderChatMessages();
    $("chatInput")?.focus();
  } else {
    stopSpeechRecognition();
  }
}

async function sendChatMessage(event) {
  event.preventDefault();
  if (state.chatPending) return;

  const input = $("chatInput");
  const message = (input?.value || "").trim();
  if (!message) return;

  const session = ensureActiveChatSession();
  const activeSessionId = session.id;
  session.messages.push({ role: "user", content: message });
  if (!session.title || session.title === "Nuova chat") {
    session.title = buildChatTitle(message);
  }
  session.updated_at = new Date().toISOString();
  saveChatHistory();
  renderChatSessionSelect();
  renderChatMessages();
  if (input) input.value = "";

  setChatPending(true);
  startAiTask();
  try {
    const sendingSession = getChatSessionById(activeSessionId) || ensureActiveChatSession();
    const history = sendingSession.messages
      .filter((item) => item.role === "assistant" || item.role === "user")
      .slice(-8);

    const response = await api("/api/chat", {
      method: "POST",
      body: {
        message,
        history,
      },
    });

    const targetSession = getChatSessionById(activeSessionId) || ensureActiveChatSession();
    targetSession.messages.push({ role: "assistant", content: response.reply });
    targetSession.updated_at = new Date().toISOString();
    saveChatHistory();
    renderChatSessionSelect();
    renderChatMessages();
  } catch (error) {
    showFlash(error.message, "error");
    const targetSession = getChatSessionById(activeSessionId) || ensureActiveChatSession();
    targetSession.messages.push({
      role: "assistant",
      content: "Non riesco a rispondere ora. Verifica connessione con Ollama e riprova.",
    });
    targetSession.updated_at = new Date().toISOString();
    saveChatHistory();
    renderChatMessages();
  } finally {
    setChatPending(false);
    endAiTask();
  }
}

function ratio(value, target) {
  if (!target || target <= 0) return 0;
  return Math.min(value / target, 1);
}

function setRingProgress(element, value, target) {
  if (!element) return;
  const pct = ratio(value, target);
  const deg = Math.round(pct * 360);
  element.style.background = `conic-gradient(var(--accent) 0deg ${deg}deg, rgba(47, 146, 95, 0.15) ${deg}deg 360deg)`;
  const label = element.querySelector("span");
  if (label) {
    label.textContent = target ? `${Math.round(pct * 100)}%` : "--";
  }
}

function setBarProgress(element, value, target) {
  if (!element) return;
  const pct = ratio(value, target) * 100;
  element.style.width = `${pct}%`;
}

function renderNeeds() {
  const needs = state.needs;
  const water = state.water;
  if (!needs && !water) return;

  const totals = needs?.totals || { calories: 0, proteins: 0, carbs: 0, fats: 0 };
  const targets = needs?.needs || {};

  $("calorieNeed").textContent = targets.calories ? `${formatNumber(targets.calories)} kcal` : "-- kcal";
  $("proteinNeed").textContent = targets.proteins ? `${formatNumber(targets.proteins)} g` : "-- g";
  $("carbNeed").textContent = targets.carbs ? `${formatNumber(targets.carbs)} g` : "-- g";
  $("fatNeed").textContent = targets.fats ? `${formatNumber(targets.fats)} g` : "-- g";

  const waterTarget = needs?.water_ml ?? water?.target_ml;
  const waterTotal = water?.total_ml || 0;
  $("waterNeed").textContent = waterTarget
    ? `${Math.round(waterTotal)} / ${Math.round(waterTarget)} ml`
    : `${Math.round(waterTotal)} ml`;

  setRingProgress($("calorieRing"), totals.calories, targets.calories);
  setBarProgress($("proteinBar"), totals.proteins, targets.proteins);
  setBarProgress($("carbBar"), totals.carbs, targets.carbs);
  setBarProgress($("fatBar"), totals.fats, targets.fats);
  setBarProgress($("waterBar"), waterTotal, waterTarget);

  if (needs?.note) {
    const sourceLabel = needs.source === "ai" ? "AI" : "stima";
    $("needsNote").textContent = `${needs.note} (${sourceLabel}).`;
  } else {
    $("needsNote").textContent = "";
  }
}

function renderTimeline(data) {
  const track = $("timelineTrack");
  if (!track) return;
  track.innerHTML = "";

  if (!data || !data.phases || !data.phases.length) {
    track.innerHTML = '<p class="muted">Imposta la routine per vedere la timeline.</p>';
    return;
  }

  data.phases.forEach((phase) => {
    const step = document.createElement("div");
    step.className = `timeline-step ${phase.status}`;
    step.innerHTML = `
      <span class="timeline-dot"></span>
      <div>
        <strong>${phase.label}</strong>
        <div class="muted">${phase.suggestion || "Bilancia i macro in modo costante."}</div>
      </div>
      <span class="timeline-time">${phase.time}</span>
    `;
    track.appendChild(step);
  });

  $("timelineHint").textContent = data.guidance || "";
}

async function loadNeeds() {
  const day = state.selectedDay;
  startAiTask();
  try {
    const data = await api(`/api/summary/needs?day=${encodeURIComponent(day)}`);
    state.needs = data;
    renderNeeds();
  } finally {
    endAiTask();
  }
}

async function loadWater() {
  const day = state.selectedDay;
  const data = await api(`/api/water?day=${encodeURIComponent(day)}`);
  state.water = data;
  renderNeeds();
}

async function loadTimeline({ force = false } = {}) {
  const day = state.selectedDay;
  const signature = buildTimelineSignature();
  const cacheKey = timelineCacheKey(day);
  const cached = getCachedTimeline(cacheKey);

  if (!signature && cached?.data) {
    renderTimeline(cached.data);
    return;
  }

  if (!force && cached && cached.signature === signature) {
    renderTimeline(cached.data);
    return;
  }

  startAiTask();
  try {
    const data = await api(`/api/summary/timeline?day=${encodeURIComponent(day)}`);
    renderTimeline(data);
    setCachedTimeline(cacheKey, signature, data);
  } catch (error) {
    if (cached?.data) {
      renderTimeline(cached.data);
      return;
    }
    throw error;
  } finally {
    endAiTask();
  }
}

async function addQuickWater() {
  try {
    await api("/api/water", { method: "POST", body: { amount_ml: 250 } });
    showFlash("Aggiunto 1 bicchiere d'acqua (+250 ml).");
    await loadWater();
  } catch (error) {
    showFlash(error.message, "error");
  }
}

function renderSummary(data) {
  const box = $("summaryBox");
  const targets = data.targets || {};

  const targetLine = [
    targets.calories ? `kcal target: ${formatNumber(targets.calories)}` : null,
    targets.proteins ? `P target: ${formatNumber(targets.proteins)}g` : null,
    targets.carbs ? `C target: ${formatNumber(targets.carbs)}g` : null,
    targets.fats ? `F target: ${formatNumber(targets.fats)}g` : null,
  ]
    .filter(Boolean)
    .join(" | ");

  if (!data.is_closed) {
    box.innerHTML = `
      <p><strong>Giornata ancora aperta.</strong> Il riepilogo definitivo viene generato dopo le <strong>${
        data.day_end_time?.slice(0, 5) || "23:00"
      }</strong>.</p>
      <p>Pasti registrati: ${data.meals_count}</p>
      <p>Totali attuali: ${formatNumber(data.totals.calories)} kcal, ${formatNumber(data.totals.proteins)}g P, ${formatNumber(
        data.totals.carbs
      )}g C, ${formatNumber(data.totals.fats)}g F.</p>
      <p>${targetLine || "Nessun target impostato nella routine."}</p>
    `;
    return;
  }

  box.innerHTML = `
    <p><strong>Giornata chiusa.</strong> Totale pasti: ${data.meals_count}.</p>
    <p>Macro finali: ${formatNumber(data.totals.calories)} kcal, ${formatNumber(data.totals.proteins)}g P, ${formatNumber(
      data.totals.carbs
    )}g C, ${formatNumber(data.totals.fats)}g F.</p>
    <p>${targetLine || "Nessun target impostato nella routine."}</p>
    <hr />
    <p>${(data.advice || "Nessun consiglio disponibile").replace(/\n/g, "<br>")}</p>
  `;
}

async function loadSummary(refresh = false) {
  const day = state.selectedDay;
  if (refresh) {
    showAiOverlay("Dietly AI sta rigenerando il riepilogo...");
  }
  try {
    const data = await api(`/api/summary/day?day=${encodeURIComponent(day)}&refresh=${refresh}`);
    renderSummary(data);
  } finally {
    if (refresh) {
      hideAiOverlay();
    }
  }
}

async function refreshDayData() {
  try {
    await loadMeals();
    await loadNeeds();
    await Promise.all([loadSummary(false), loadWater()]);
    await loadTimeline();
  } catch (error) {
    showFlash(error.message, "error");
  }
}

async function loadDashboard() {
  $("filterDay").value = state.selectedDay;
  resetMealFormToCreate();

  await loadRoutine();
  await refreshDayData();
}

function registerEvents() {
  $("loginForm").addEventListener("submit", handleLogin);
  $("registerForm").addEventListener("submit", handleRegister);

  $("navToggleBtn").addEventListener("click", toggleMenu);
  $("navLogoutBtn").addEventListener("click", logout);

  document.querySelectorAll("#mainMenu a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  $("quickCaptureForm").addEventListener("submit", handleQuickCapture);

  $("routineForm").addEventListener("submit", saveRoutine);
  $("mealForm").addEventListener("submit", saveMeal);
  $("cancelEditMealBtn").addEventListener("click", () => {
    resetMealFormToCreate();
    showFlash("Modifica annullata.");
  });
  $("addMealItemBtn")?.addEventListener("click", () => {
    addMealItemRow();
    scheduleManualEstimate();
  });
  $("mealNotes")?.addEventListener("input", scheduleManualEstimate);
  $("mealType")?.addEventListener("change", scheduleManualEstimate);

  $("filterDay").addEventListener("change", async (event) => {
    state.selectedDay = event.target.value;
    await refreshDayData();
  });

  $("refreshDayBtn").addEventListener("click", refreshDayData);
  $("refreshSummaryBtn").addEventListener("click", async () => {
    try {
      await loadSummary(true);
      showFlash("Consigli rigenerati.");
    } catch (error) {
      showFlash(error.message, "error");
    }
  });

  const waterBtn = $("waterQuickBtn");
  if (waterBtn) {
    waterBtn.addEventListener("click", addQuickWater);
  }

  $("chatFabBtn")?.addEventListener("click", () => toggleChat(true));
  $("chatNewBtn")?.addEventListener("click", openNewChatSession);
  $("chatSessionSelect")?.addEventListener("change", (event) => switchChatSession(event.target.value));
  $("chatCloseBtn")?.addEventListener("click", () => toggleChat(false));
  $("chatMicBtn")?.addEventListener("click", toggleSpeechRecognition);
  $("chatPanel")?.addEventListener("click", (event) => {
    if (event.target?.id === "chatPanel") {
      toggleChat(false);
    }
  });
  $("chatForm")?.addEventListener("submit", sendChatMessage);
}

(async function bootstrap() {
  registerEvents();
  applyAuthState();

  if (state.token && state.user) {
    try {
      await loadDashboard();
    } catch (error) {
      showFlash(error.message, "error");
    }
  }
})();
