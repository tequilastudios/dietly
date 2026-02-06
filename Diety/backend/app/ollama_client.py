import base64
import json
import re

import httpx

from .config import settings


class OllamaServiceError(Exception):
    pass


VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack", "other"}
MEAL_TYPE_ALIASES = {
    "breakfast": "breakfast",
    "colazione": "breakfast",
    "lunch": "lunch",
    "pranzo": "lunch",
    "dinner": "dinner",
    "cena": "dinner",
    "snack": "snack",
    "spuntino": "snack",
    "merenda": "snack",
    "other": "other",
    "altro": "other",
}
LANGUAGE_LABELS = {
    "it": "italiano",
    "en": "inglese",
    "es": "spagnolo",
    "fr": "francese",
    "de": "tedesco",
}
MAX_REASONING_CYCLES = 4


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False

    return default


def _resolve_preference_str(preferences: dict | None, key: str, default: str) -> str:
    if preferences and preferences.get(key):
        return str(preferences[key]).strip()
    return default


def _resolve_preference_float(
    preferences: dict | None,
    key: str,
    default: float | None = None,
) -> float | None:
    if not preferences or preferences.get(key) is None:
        return default
    value = _safe_float(preferences.get(key))
    return value


def _resolve_preference_int(preferences: dict | None, key: str, default: int) -> int:
    if not preferences or preferences.get(key) is None:
        return default
    try:
        return int(preferences.get(key))
    except (TypeError, ValueError):
        return default


def _resolve_preference_bool(preferences: dict | None, key: str, default: bool) -> bool:
    if not preferences or preferences.get(key) is None:
        return default
    return _safe_bool(preferences.get(key), default)


def _resolve_language_label(preferences: dict | None) -> str:
    if preferences and preferences.get("response_language"):
        value = str(preferences.get("response_language")).strip().lower()
        return LANGUAGE_LABELS.get(value, value)
    return "italiano"


def _prefix_prompt(prompt: str, preferences: dict | None, json_mode: bool = False) -> str:
    system_prompt = _resolve_preference_str(preferences, "system_prompt", "")
    language = _resolve_language_label(preferences)
    if json_mode:
        language_note = f"Le stringhe del JSON devono essere in {language}."
    else:
        language_note = f"Rispondi in {language}."

    composed = f"{prompt}\n{language_note}"
    if system_prompt:
        composed = f"{system_prompt}\n\n{composed}"
    return composed


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _normalize_meal_type(value: object) -> str | None:
    if value is None:
        return None

    candidate = _normalize_key(str(value))
    if not candidate:
        return None

    if candidate in VALID_MEAL_TYPES:
        return candidate

    return MEAL_TYPE_ALIASES.get(candidate)


def _infer_meal_type_from_text(food_name: str, notes: str) -> str:
    text = f"{food_name} {notes}".lower()
    normalized = _normalize_key(text)

    if any(word in normalized for word in ("colazione", "breakfast", "cappuccino", "cornetto", "cereali")):
        return "breakfast"
    if any(word in normalized for word in ("pranzo", "lunch", "primo", "secondo", "pasta", "riso")):
        return "lunch"
    if any(word in normalized for word in ("cena", "dinner", "zuppa", "pesce", "carne")):
        return "dinner"
    if any(word in normalized for word in ("snack", "spuntino", "merenda", "barretta", "frutta", "yogurt")):
        return "snack"

    return "other"


def _safe_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        match = re.search(r"-?\d+(?:\.\d+)?", normalized)
        if match:
            try:
                return round(float(match.group(0)), 2)
            except ValueError:
                return 0.0

    if isinstance(value, dict):
        for key in ("value", "amount", "total", "estimate"):
            if key in value:
                nested = _safe_float(value.get(key))
                if nested:
                    return nested

    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _extract_json_block(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise OllamaServiceError("Risposta AI non in formato JSON")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise OllamaServiceError("Impossibile leggere il JSON restituito da Ollama") from exc


def _find_value_by_keys(payload: object, valid_keys: set[str]) -> object | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _normalize_key(key) in valid_keys:
                return value

        for value in payload.values():
            nested = _find_value_by_keys(value, valid_keys)
            if nested is not None:
                return nested

    if isinstance(payload, list):
        for item in payload:
            nested = _find_value_by_keys(item, valid_keys)
            if nested is not None:
                return nested

    return None


def _safe_text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text if text else fallback


def _extract_analysis_fields(parsed: dict) -> dict:
    calories_keys = {
        "calories",
        "calorie",
        "kcal",
        "energy",
        "kilocalories",
        "totalcalories",
        "energia",
    }
    proteins_keys = {
        "proteins",
        "protein",
        "proteing",
        "proteinsg",
        "proteine",
        "proteinigrams",
    }
    carbs_keys = {
        "carbs",
        "carbohydrates",
        "carbohydrate",
        "carbohydratesg",
        "carbsg",
        "carboidrati",
        "carboidrato",
    }
    fats_keys = {
        "fats",
        "fat",
        "fatsg",
        "fatg",
        "grassi",
        "grasso",
        "lipids",
        "lipid",
    }
    food_name_keys = {"foodname", "dishname", "name", "mealname", "piatto", "cibo"}
    notes_keys = {"notes", "description", "details", "osservazioni", "descrizione"}
    confidence_keys = {"confidence", "score", "certainty", "accuracylevel", "reliability"}
    meal_type_keys = {"mealtype", "tipopasto", "mealcategory", "category", "categoria"}

    food_name = _safe_text(_find_value_by_keys(parsed, food_name_keys), fallback="Pasto rilevato")
    notes = _safe_text(_find_value_by_keys(parsed, notes_keys), fallback="")
    meal_type = _normalize_meal_type(_find_value_by_keys(parsed, meal_type_keys))

    return {
        "meal_type": meal_type,
        "food_name": food_name,
        "calories": _safe_float(_find_value_by_keys(parsed, calories_keys)),
        "proteins": _safe_float(_find_value_by_keys(parsed, proteins_keys)),
        "carbs": _safe_float(_find_value_by_keys(parsed, carbs_keys)),
        "fats": _safe_float(_find_value_by_keys(parsed, fats_keys)),
        "notes": notes,
        "confidence": min(max(_safe_float(_find_value_by_keys(parsed, confidence_keys)), 0.0), 1.0),
    }


async def _generate(payload: dict, base_url: str | None = None, timeout: int | None = None) -> str:
    target_base_url = (base_url or settings.ollama_base_url).rstrip("/")
    target_timeout = timeout or settings.ollama_timeout
    try:
        async with httpx.AsyncClient(timeout=target_timeout) as client:
            response = await client.post(f"{target_base_url}/api/generate", json=payload)
            response.raise_for_status()
            raw = response.json()
    except httpx.HTTPError as exc:
        raise OllamaServiceError(
            "Ollama non raggiungibile. Verifica che il servizio sia in esecuzione in locale."
        ) from exc

    output = raw.get("response", "")
    if not output:
        raise OllamaServiceError("Ollama ha restituito una risposta vuota")
    return output.strip()


async def _generate_text(
    prompt: str,
    preferences: dict | None = None,
    cycles: int | None = None,
) -> str:
    text_model = _resolve_preference_str(preferences, "text_model", settings.ollama_text_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)

    cycle_count = cycles if cycles is not None else _resolve_preference_int(preferences, "reasoning_cycles", 1)
    cycle_count = max(1, min(cycle_count, MAX_REASONING_CYCLES))

    base_prompt = _prefix_prompt(prompt, preferences)

    request_payload = {
        "model": text_model,
        "prompt": base_prompt,
        "stream": False,
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    response = await _generate(request_payload, base_url=ollama_base_url, timeout=timeout_seconds)

    if cycle_count <= 1:
        return response

    system_prompt = _resolve_preference_str(preferences, "system_prompt", "")
    language = _resolve_language_label(preferences)

    for _ in range(1, cycle_count):
        refine_prompt = (
            f"Rivedi e migliora la risposta seguente mantenendo chiarezza e coerenza. "
            f"Rispondi solo con la versione finale in {language}.\n\nRISPOSTA:\n{response}"
        )
        if system_prompt:
            refine_prompt = f"{system_prompt}\n\n{refine_prompt}"
        request_payload["prompt"] = refine_prompt
        response = await _generate(request_payload, base_url=ollama_base_url, timeout=timeout_seconds)

    return response


async def _estimate_macros_from_text(
    food_name: str,
    notes: str,
    hint: str = "",
    preferences: dict | None = None,
) -> dict:
    text_model = _resolve_preference_str(preferences, "text_model", settings.ollama_text_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)

    prompt = (
        "Stima il tipo pasto e i macronutrienti del pasto descritto e rispondi SOLO in JSON con: "
        "meal_type (breakfast|lunch|dinner|snack|other), calories (number), proteins (number), "
        "carbs (number), fats (number). "
        "Usa numeri puri senza unita e non usare null. "
        f"Pasto: {food_name}. Descrizione: {notes or 'non disponibile'}."
    )
    if hint.strip():
        prompt += f" Contesto utente: {hint.strip()}."

    request_payload = {
        "model": text_model,
        "prompt": _prefix_prompt(prompt, preferences, json_mode=True),
        "stream": False,
        "format": "json",
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    raw_response = await _generate(
        request_payload,
        base_url=ollama_base_url,
        timeout=timeout_seconds,
    )
    parsed = _extract_json_block(raw_response)
    extracted = _extract_analysis_fields(parsed)
    return {
        "meal_type": extracted["meal_type"],
        "calories": extracted["calories"],
        "proteins": extracted["proteins"],
        "carbs": extracted["carbs"],
        "fats": extracted["fats"],
    }


async def analyze_food_image(
    image_bytes: bytes,
    hint: str = "",
    preferences: dict | None = None,
) -> dict:
    vision_model = _resolve_preference_str(preferences, "vision_model", settings.ollama_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)
    macro_fallback_enabled = _resolve_preference_bool(preferences, "macro_fallback_enabled", default=True)
    meal_type_autodetect_enabled = _resolve_preference_bool(
        preferences,
        "meal_type_autodetect_enabled",
        default=True,
    )

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Analizza il cibo nella foto e rispondi SOLO in JSON con questi campi: "
        "meal_type (breakfast|lunch|dinner|snack|other), food_name (string), "
        "calories (number), proteins (number), carbs (number), fats (number), "
        "notes (string), confidence (number 0-1). "
        "Stima i macro totali della porzione visibile. "
        "Usa numeri puri senza unita (esempio calories: 540, proteins: 22.5)."
    )

    if hint.strip():
        prompt += f" Contesto utente: {hint.strip()}"

    request_payload = {
        "model": vision_model,
        "prompt": _prefix_prompt(prompt, preferences, json_mode=True),
        "images": [encoded_image],
        "stream": False,
        "format": "json",
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    raw_response = await _generate(
        request_payload,
        base_url=ollama_base_url,
        timeout=timeout_seconds,
    )

    parsed = _extract_json_block(raw_response)
    extracted = _extract_analysis_fields(parsed)

    macros_sum = extracted["calories"] + extracted["proteins"] + extracted["carbs"] + extracted["fats"]
    needs_fallback = macro_fallback_enabled and (macros_sum == 0 or extracted["meal_type"] is None)
    fallback_used = False
    if needs_fallback:
        try:
            fallback_macros = await _estimate_macros_from_text(
                food_name=extracted["food_name"],
                notes=extracted["notes"],
                hint=hint,
                preferences=preferences,
            )
            fallback_sum = (
                fallback_macros["calories"]
                + fallback_macros["proteins"]
                + fallback_macros["carbs"]
                + fallback_macros["fats"]
            )
            if fallback_sum > 0:
                extracted.update(fallback_macros)
                fallback_used = True
                if extracted["confidence"] == 0:
                    extracted["confidence"] = 0.45
            elif fallback_macros.get("meal_type") and extracted["meal_type"] is None:
                extracted["meal_type"] = fallback_macros["meal_type"]
        except Exception:
            # Non blocchiamo il flusso se la stima fallback non riesce.
            pass

    if meal_type_autodetect_enabled:
        extracted["meal_type"] = extracted["meal_type"] or _infer_meal_type_from_text(
            extracted["food_name"],
            extracted["notes"],
        )
    else:
        extracted["meal_type"] = extracted["meal_type"] or "other"

    return {
        "meal_type": extracted["meal_type"],
        "food_name": extracted["food_name"],
        "calories": extracted["calories"],
        "proteins": extracted["proteins"],
        "carbs": extracted["carbs"],
        "fats": extracted["fats"],
        "notes": extracted["notes"],
        "confidence": extracted["confidence"],
        "raw": raw_response,
        "fallback_used": fallback_used,
    }


async def estimate_manual_meal_from_items(
    items: list[dict],
    hint: str = "",
    meal_type: str | None = None,
    preferences: dict | None = None,
) -> dict:
    if not items:
        raise OllamaServiceError("Nessun ingrediente fornito per la stima manuale.")

    text_model = _resolve_preference_str(preferences, "text_model", settings.ollama_text_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)

    ingredient_lines = []
    short_names = []
    for item in items[:20]:
        name = _safe_text(item.get("name"))
        quantity = _safe_text(item.get("quantity"))
        if not name:
            continue
        short_names.append(name)
        ingredient_lines.append(f"- {name}" + (f" ({quantity})" if quantity else ""))

    if not ingredient_lines:
        raise OllamaServiceError("Inserisci almeno un ingrediente valido.")

    meal_hint = f"Tipo pasto suggerito: {meal_type}." if meal_type else ""
    note_hint = f"Dettagli utente: {hint.strip()}" if hint and hint.strip() else ""
    ingredient_text = "; ".join(ingredient_lines)
    prompt = (
        "Stima i macronutrienti totali di un pasto composto da piu ingredienti e rispondi SOLO in JSON con: "
        "food_name (string), calories (number), proteins (number), carbs (number), fats (number), "
        "notes (string), confidence (number 0-1). "
        "Usa numeri puri senza unita.\n"
        f"{meal_hint}\n{note_hint}\n"
        f"Ingredienti:\n{chr(10).join(ingredient_lines)}"
    )

    request_payload = {
        "model": text_model,
        "prompt": _prefix_prompt(prompt, preferences, json_mode=True),
        "stream": False,
        "format": "json",
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    raw_response = await _generate(
        request_payload,
        base_url=ollama_base_url,
        timeout=timeout_seconds,
    )

    extracted = None
    try:
        parsed = _extract_json_block(raw_response)
        extracted = _extract_analysis_fields(parsed)
    except OllamaServiceError:
        extracted = None

    default_name = "Pasto composito"
    if short_names:
        default_name = ", ".join(short_names[:3])
        if len(short_names) > 3:
            default_name += " + altri"

    if extracted is None:
        try:
            fallback = await _estimate_macros_from_text(
                food_name=default_name,
                notes=f"Ingredienti: {ingredient_text}",
                hint=hint,
                preferences=preferences,
            )
            calories = fallback["calories"]
            proteins = fallback["proteins"]
            carbs = fallback["carbs"]
            fats = fallback["fats"]
            confidence = 0.42
        except Exception:
            item_count = max(len(ingredient_lines), 1)
            calories = round(110.0 * item_count, 2)
            proteins = round(4.0 * item_count, 2)
            carbs = round(12.0 * item_count, 2)
            fats = round(4.0 * item_count, 2)
            confidence = 0.2
        return {
            "food_name": default_name,
            "calories": calories,
            "proteins": proteins,
            "carbs": carbs,
            "fats": fats,
            "notes": f"Stima fallback su ingredienti: {ingredient_text}",
            "confidence": confidence,
            "raw": raw_response,
        }

    return {
        "food_name": extracted["food_name"] or default_name,
        "calories": extracted["calories"],
        "proteins": extracted["proteins"],
        "carbs": extracted["carbs"],
        "fats": extracted["fats"],
        "notes": extracted["notes"] or f"Stima su {len(ingredient_lines)} ingredienti.",
        "confidence": extracted["confidence"] if extracted["confidence"] > 0 else 0.55,
        "raw": raw_response,
    }


async def generate_daily_advice(payload: dict, preferences: dict | None = None) -> str:
    profile = payload.get("user_profile", {}) if isinstance(payload, dict) else {}
    goals = profile.get("goals") or (preferences or {}).get("goals")
    dietary_preferences = profile.get("dietary_preferences") or (preferences or {}).get("dietary_preferences")
    allergies = profile.get("allergies") or (preferences or {}).get("allergies")

    context_bits = []
    if goals:
        context_bits.append(f"Obiettivi utente: {goals}")
    if dietary_preferences:
        context_bits.append(f"Preferenze alimentari: {dietary_preferences}")
    if allergies:
        context_bits.append(f"Allergie/intolleranze: {allergies}")

    personal_context = " | ".join(context_bits) if context_bits else "Nessun contesto aggiuntivo"

    prompt = (
        "Sei un nutrizionista virtuale. Crea un breve resoconto della giornata "
        "con 3 consigli pratici e realistici. Personalizza i consigli in base a obiettivi e "
        "preferenze dell'utente quando disponibili. Rispondi in testo semplice, massimo 7 righe. "
        f"Contesto utente: {personal_context}. "
        f"Dati giornata: {json.dumps(payload, ensure_ascii=False)}"
    )
    return await _generate_text(prompt, preferences)


async def generate_daily_needs(payload: dict, preferences: dict | None = None) -> dict | None:
    prompt = (
        "Calcola il fabbisogno giornaliero di una persona in base ai dati forniti. "
        "Rispondi SOLO in JSON con: calories (number), proteins (number), carbs (number), fats (number), "
        "note (string). Usa numeri puri senza unita. "
        f"Dati: {json.dumps(payload, ensure_ascii=False)}"
    )

    text_model = _resolve_preference_str(preferences, "text_model", settings.ollama_text_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)

    request_payload = {
        "model": text_model,
        "prompt": _prefix_prompt(prompt, preferences, json_mode=True),
        "stream": False,
        "format": "json",
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    raw_response = await _generate(request_payload, base_url=ollama_base_url, timeout=timeout_seconds)
    parsed = _extract_json_block(raw_response)

    return {
        "needs": {
            "calories": _safe_float(parsed.get("calories")),
            "proteins": _safe_float(parsed.get("proteins")),
            "carbs": _safe_float(parsed.get("carbs")),
            "fats": _safe_float(parsed.get("fats")),
        },
        "note": _safe_text(parsed.get("note"), fallback="Stima calcolata automaticamente dall'AI."),
    }


async def generate_timeline_guidance(payload: dict, preferences: dict | None = None) -> str:
    prompt = (
        "Genera un breve consiglio (1-2 frasi) su come bilanciare i macro per il resto della giornata. "
        f"Dati: {json.dumps(payload, ensure_ascii=False)}"
    )
    return await _generate_text(prompt, preferences)


async def generate_smart_routine(payload: dict, preferences: dict | None = None) -> dict | None:
    prompt = (
        "Ottimizza una routine alimentare giornaliera. Rispondi SOLO in JSON con eventuali campi: "
        "breakfast_time, lunch_time, dinner_time, day_end_time (HH:MM), "
        "calorie_target, protein_target, carbs_target, fats_target (numeri). "
        "Includi una nota sintetica nel campo note. "
        f"Dati: {json.dumps(payload, ensure_ascii=False)}"
    )

    text_model = _resolve_preference_str(preferences, "text_model", settings.ollama_text_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)

    request_payload = {
        "model": text_model,
        "prompt": _prefix_prompt(prompt, preferences, json_mode=True),
        "stream": False,
        "format": "json",
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    raw_response = await _generate(request_payload, base_url=ollama_base_url, timeout=timeout_seconds)
    parsed = _extract_json_block(raw_response)

    return {
        "breakfast_time": _safe_text(parsed.get("breakfast_time")),
        "lunch_time": _safe_text(parsed.get("lunch_time")),
        "dinner_time": _safe_text(parsed.get("dinner_time")),
        "day_end_time": _safe_text(parsed.get("day_end_time")),
        "calorie_target": _safe_float(parsed.get("calorie_target")),
        "protein_target": _safe_float(parsed.get("protein_target")),
        "carbs_target": _safe_float(parsed.get("carbs_target")),
        "fats_target": _safe_float(parsed.get("fats_target")),
        "note": _safe_text(parsed.get("note")),
        "raw": raw_response,
    }


async def analyze_body_photo(
    image_bytes: bytes,
    kind: str,
    preferences: dict | None = None,
) -> dict:
    vision_model = _resolve_preference_str(preferences, "vision_model", settings.ollama_model)
    ollama_base_url = _resolve_preference_str(preferences, "ollama_base_url", settings.ollama_base_url)
    timeout_seconds = _resolve_preference_int(preferences, "timeout_seconds", settings.ollama_timeout)
    temperature = _resolve_preference_float(preferences, "temperature", default=None)

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Analizza la foto del corpo umano e fornisci una stima qualitativa della composizione corporea. "
        "Rispondi SOLO in JSON con: summary (string), body_fat_estimate (string), muscle_tone (string), "
        "posture (string), notes (string), confidence (number 0-1). "
        f"Tipo foto: {kind}."
    )

    request_payload = {
        "model": vision_model,
        "prompt": _prefix_prompt(prompt, preferences, json_mode=True),
        "images": [encoded_image],
        "stream": False,
        "format": "json",
    }
    if temperature is not None:
        request_payload["options"] = {"temperature": temperature}

    raw_response = await _generate(
        request_payload,
        base_url=ollama_base_url,
        timeout=timeout_seconds,
    )
    parsed = _extract_json_block(raw_response)

    return {
        "summary": _safe_text(parsed.get("summary"), fallback="Analisi corporea disponibile."),
        "body_fat_estimate": _safe_text(parsed.get("body_fat_estimate"), fallback="n/d"),
        "muscle_tone": _safe_text(parsed.get("muscle_tone"), fallback="n/d"),
        "posture": _safe_text(parsed.get("posture"), fallback="n/d"),
        "notes": _safe_text(parsed.get("notes"), fallback=""),
        "confidence": min(max(_safe_float(parsed.get("confidence")), 0.0), 1.0),
        "raw": raw_response,
    }


async def compare_body_photos(payload: dict, preferences: dict | None = None) -> str:
    prompt = (
        "Confronta due foto corpo e descrivi progressi o peggioramenti in modo professionale. "
        "Rispondi in un paragrafo conciso. "
        f"Dati confronto: {json.dumps(payload, ensure_ascii=False)}"
    )
    return await _generate_text(prompt, preferences)


async def generate_chat_response(payload: dict, preferences: dict | None = None) -> str:
    prompt = (
        "Sei DietlyBot, assistente nutrizionale. Rispondi in modo professionale, empatico e pratico. "
        "Usa frasi chiare e consigli realistici. "
        f"Dati utente: {json.dumps(payload, ensure_ascii=False)}"
    )
    return await _generate_text(prompt, preferences)
