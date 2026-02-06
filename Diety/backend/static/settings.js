const $ = (id) => document.getElementById(id);

const state = {
  token: localStorage.getItem("dietly_token"),
  user: JSON.parse(localStorage.getItem("dietly_user") || "null"),
  models: [],
};

function showFlash(message, level = "success") {
  const flash = $("flash");
  flash.classList.remove("hidden", "error", "success");
  flash.classList.add(level === "error" ? "error" : "success");
  flash.textContent = message;
  setTimeout(() => flash.classList.add("hidden"), 3500);
}

function logout() {
  localStorage.removeItem("dietly_token");
  localStorage.removeItem("dietly_user");
  window.location.href = "/";
}

async function api(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {
    Authorization: `Bearer ${state.token}`,
  };

  if (!isForm && body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

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
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }

  return response.status === 204 ? null : response.json();
}

function fillForm(data) {
  $("ollamaBaseUrl").value = data.ollama_base_url || "";
  $("visionModel").value = data.vision_model || "";
  $("textModel").value = data.text_model || "";
  $("timeoutSeconds").value = data.timeout_seconds ?? 180;
  $("temperature").value = data.temperature ?? 0.2;
  $("responseLanguage").value = data.response_language || "it";
  $("reasoningCycles").value = data.reasoning_cycles ?? 1;
  $("systemPrompt").value = data.system_prompt ?? "";
  $("ageYears").value = data.age_years ?? "";
  $("sex").value = data.sex ?? "";
  $("heightCm").value = data.height_cm ?? "";
  $("weightKg").value = data.weight_kg ?? "";
  $("targetWeightKg").value = data.target_weight_kg ?? "";
  $("activityLevel").value = data.activity_level ?? "";
  $("goals").value = data.goals ?? "";
  $("dietaryPreferences").value = data.dietary_preferences ?? "";
  $("allergies").value = data.allergies ?? "";
  $("macroFallbackEnabled").checked = Boolean(data.macro_fallback_enabled);
  $("mealTypeAutodetectEnabled").checked = Boolean(data.meal_type_autodetect_enabled);
  $("smartRoutineEnabled").checked = Boolean(data.smart_routine_enabled);
}

function payloadFromForm() {
  const rawBaseUrl = $("ollamaBaseUrl").value.trim();
  return {
    ollama_base_url: rawBaseUrl || null,
    vision_model: $("visionModel").value.trim(),
    text_model: $("textModel").value.trim(),
    timeout_seconds: Number($("timeoutSeconds").value),
    temperature: Number($("temperature").value),
    response_language: $("responseLanguage").value,
    reasoning_cycles: Number($("reasoningCycles").value || 1),
    system_prompt: $("systemPrompt").value.trim() || null,
    age_years: $("ageYears").value ? Number($("ageYears").value) : null,
    sex: $("sex").value.trim() || null,
    height_cm: $("heightCm").value ? Number($("heightCm").value) : null,
    weight_kg: $("weightKg").value ? Number($("weightKg").value) : null,
    target_weight_kg: $("targetWeightKg").value ? Number($("targetWeightKg").value) : null,
    activity_level: $("activityLevel").value || null,
    goals: $("goals").value.trim() || null,
    dietary_preferences: $("dietaryPreferences").value.trim() || null,
    allergies: $("allergies").value.trim() || null,
    macro_fallback_enabled: $("macroFallbackEnabled").checked,
    meal_type_autodetect_enabled: $("mealTypeAutodetectEnabled").checked,
    smart_routine_enabled: $("smartRoutineEnabled").checked,
  };
}

function renderBodyGallery(items) {
  const gallery = $("bodyPhotoGallery");
  if (!gallery) return;
  gallery.innerHTML = "";

  if (!items || !items.length) {
    gallery.innerHTML = '<p class="muted">Nessuna foto caricata al momento.</p>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "photo-card";
    card.innerHTML = `
      <a href="${item.image_url}" target="_blank" rel="noopener">
        <img src="${item.image_url}" alt="Foto corpo ${item.kind}" />
      </a>
      <div class="photo-meta">
        <strong>${item.kind === "front" ? "Fronte intero" : "Retro intero"}</strong>
        <span>${new Date(item.captured_at).toLocaleDateString("it-IT")}</span>
        <span>${item.ai_summary || "Analisi AI in corso o non disponibile."}</span>
      </div>
    `;
    gallery.appendChild(card);
  });
}

async function loadBodyPhotos() {
  const data = await api("/api/body-photos");
  renderBodyGallery(data);
}

async function uploadBodyPhoto(event) {
  event.preventDefault();
  const fileInput = $("bodyPhotoFile");
  const file = fileInput.files?.[0];
  if (!file) {
    showFlash("Seleziona una foto da caricare.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("kind", $("bodyPhotoKind").value);
  formData.append("image", file);

  try {
    await api("/api/body-photos", { method: "POST", body: formData, isForm: true });
    showFlash("Foto caricata con successo.");
    fileInput.value = "";
    await loadBodyPhotos();
  } catch (error) {
    showFlash(error.message, "error");
  }
}

async function compareBodyPhotos() {
  try {
    const kind = $("bodyPhotoKind").value;
    const data = await api(`/api/body-photos/compare?kind=${encodeURIComponent(kind)}`);
    $("bodyCompareOutput").textContent = data.comparison || "Nessun confronto disponibile.";
  } catch (error) {
    showFlash(error.message, "error");
  }
}

function setSelectOptions(selectId, models, currentValue = "") {
  const select = $(selectId);
  if (!select) return;

  const previous = currentValue || select.value || "";
  select.innerHTML = "";

  if (!models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Nessun modello disponibile";
    select.appendChild(option);
    return;
  }

  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    if (model === previous) {
      option.selected = true;
    }
    select.appendChild(option);
  });

  if (!select.value) {
    select.value = models[0];
  }
}

function syncSelectWithInput(inputId, selectId) {
  const input = $(inputId);
  const select = $(selectId);
  if (!input || !select) return;

  const inputValue = input.value.trim();
  const matching = Array.from(select.options).find((option) => option.value === inputValue);
  if (matching) {
    select.value = matching.value;
  }
}

function normalizeBaseUrl(url) {
  const cleaned = (url || "").trim();
  if (!cleaned) return "";
  return cleaned.replace(/\/+$/, "");
}

function pickPreferredModel(models, priorities = []) {
  if (!models.length) return "";
  for (const preferred of priorities) {
    if (models.includes(preferred)) return preferred;
  }
  return models[0];
}

function updateModelsStatus(data) {
  const statusEl = $("modelsStatus");
  if (!statusEl) return;

  const warnings = [];
  if (!data.default_vision_installed) {
    warnings.push(`Modello visione salvato non trovato: ${data.default_vision_model}`);
  }
  if (!data.default_text_installed) {
    warnings.push(`Modello testo salvato non trovato: ${data.default_text_model}`);
  }

  if (warnings.length) {
    statusEl.textContent = `Modelli rilevati: ${data.models.length}. Attenzione: ${warnings.join(" | ")}.`;
    return;
  }

  statusEl.textContent = `Modelli rilevati: ${data.models.length} da ${data.base_url}.`;
}

async function loadInstalledModels({ useCurrentInputBaseUrl = true } = {}) {
  const baseUrl = useCurrentInputBaseUrl ? normalizeBaseUrl($("ollamaBaseUrl").value) : "";
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";

  const data = await api(`/api/settings/models${query}`);
  state.models = data.models || [];

  const visionModels = data.vision_candidates || data.models || [];
  const textModels = data.text_candidates || data.models || [];

  setSelectOptions("visionModelSelect", visionModels, $("visionModel").value.trim());
  setSelectOptions("textModelSelect", textModels, $("textModel").value.trim());
  updateModelsStatus(data);

  if (!data.default_text_installed && (data.text_candidates || []).length) {
    const currentTextModel = $("textModel").value.trim();
    const preferredText = pickPreferredModel(data.text_candidates, [
      "mistral:latest",
      "mistral:instruct",
      "deepseek-r1:32b",
      "gpt-oss:20b",
    ]);
    if (!currentTextModel || currentTextModel === data.default_text_model) {
      $("textModel").value = preferredText;
    }
  }

  if (!data.default_vision_installed && (data.vision_candidates || []).length) {
    const currentVisionModel = $("visionModel").value.trim();
    const preferredVision = pickPreferredModel(data.vision_candidates, ["llava:latest", "deepseek-ocr:latest"]);
    if (!currentVisionModel || currentVisionModel === data.default_vision_model) {
      $("visionModel").value = preferredVision;
    }
  }

  syncSelectWithInput("visionModel", "visionModelSelect");
  syncSelectWithInput("textModel", "textModelSelect");

  if (!baseUrl) {
    $("ollamaBaseUrl").placeholder = data.base_url;
  }
}

async function loadSettings() {
  const data = await api("/api/settings");
  fillForm(data);
}

async function saveSettings(event) {
  event.preventDefault();

  try {
    await api("/api/settings", {
      method: "PUT",
      body: payloadFromForm(),
    });
    showFlash("Impostazioni salvate con successo.");
  } catch (error) {
    showFlash(error.message, "error");
  }
}

function bootstrap() {
  if (!state.token || !state.user) {
    window.location.href = "/";
    return;
  }

  $("settingsWelcome").textContent = `Ciao ${state.user.full_name}, configura i parametri AI di Dietly.`;

  $("settingsLogoutBtn").addEventListener("click", logout);
  $("reloadSettingsBtn").addEventListener("click", async () => {
    try {
      await loadSettings();
      await loadInstalledModels();
      showFlash("Valori ricaricati.");
    } catch (error) {
      showFlash(error.message, "error");
    }
  });

  $("reloadModelsBtn").addEventListener("click", async () => {
    try {
      await loadInstalledModels();
      showFlash("Elenco modelli aggiornato da Ollama.");
    } catch (error) {
      showFlash(error.message, "error");
    }
  });

  $("settingsForm").addEventListener("submit", saveSettings);
  $("bodyPhotoForm").addEventListener("submit", uploadBodyPhoto);
  $("compareBodyBtn").addEventListener("click", compareBodyPhotos);

  $("visionModelSelect").addEventListener("change", (event) => {
    if (event.target.value) {
      $("visionModel").value = event.target.value;
    }
  });

  $("textModelSelect").addEventListener("change", (event) => {
    if (event.target.value) {
      $("textModel").value = event.target.value;
    }
  });

  $("visionModel").addEventListener("blur", () => syncSelectWithInput("visionModel", "visionModelSelect"));
  $("textModel").addEventListener("blur", () => syncSelectWithInput("textModel", "textModelSelect"));

  (async () => {
    try {
      await loadSettings();
      await loadInstalledModels();
      await loadBodyPhotos();
    } catch (error) {
      showFlash(error.message, "error");
    }
  })();
}

bootstrap();
