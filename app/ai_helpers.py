from __future__ import annotations

import json
import os
import re

from app.config import load_settings


def _get_groq_api_key() -> str:
    settings = load_settings()
    key = str(settings.get("groq_api_key", "") or "").strip()
    if key:
        return key

    return os.getenv("GROQ_API_KEY", "").strip()


def ai_available() -> bool:
    return bool(_get_groq_api_key())


def _require_key():
    api_key = _get_groq_api_key()
    if not api_key:
        raise RuntimeError("Groq API key is not configured. Add it in Settings.")
    return api_key


def _extract_json_object(text: str) -> dict:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("AI response did not contain valid JSON.")


def _call_groq(prompt: str, temperature: float = 0.2) -> str:
    api_key = _require_key()

    try:
        from groq import Groq
    except Exception as e:
        raise RuntimeError(f"Groq package is not installed or failed to import: {e}")

    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        messages=[
            {"role": "system", "content": "You are a precise IT ticketing assistant."},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content or ""


def ai_correct_text(text: str) -> str:
    prompt = (
        "Clean up the following technician note. "
        "Fix grammar, spelling, clarity, and formatting, but keep the meaning unchanged.\n\n"
        f"{text}"
    )
    return _call_groq(prompt, temperature=0.1).strip()


def ai_extract_ticket(raw_text: str) -> dict:
    prompt = f"""
Extract ticket fields from the text below.

Return ONLY valid JSON in this exact structure:
{{
  "name": "",
  "phone": "",
  "email": "",
  "device": "",
  "issue": "",
  "probable_cause": ""
}}

If a field is unknown, use an empty string.

Text:
{raw_text}
""".strip()

    content = _call_groq(prompt, temperature=0.1)
    data = _extract_json_object(content)

    return {
        "name": str(data.get("name", "") or ""),
        "phone": str(data.get("phone", "") or ""),
        "email": str(data.get("email", "") or ""),
        "device": str(data.get("device", "") or ""),
        "issue": str(data.get("issue", "") or ""),
        "probable_cause": str(data.get("probable_cause", "") or ""),
    }


def ai_summarize_ticket(ticket: dict) -> dict:
    notes_text = []
    for note in ticket.get("notes", []):
        content = str(note.get("content", "") or "").strip()
        if content.startswith("[TICKETIT_META]"):
            continue
        notes_text.append(content)

    prompt = f"""
Summarize this IT support ticket.

Return ONLY valid JSON in this exact structure:
{{
  "problem": "",
  "diagnosis": "",
  "actions_taken": "",
  "current_status": "",
  "customer_summary": ""
}}

Ticket:
{json.dumps(ticket, indent=2, ensure_ascii=False)}

Visible Notes:
{json.dumps(notes_text, indent=2, ensure_ascii=False)}
""".strip()

    content = _call_groq(prompt, temperature=0.2)
    data = _extract_json_object(content)

    return {
        "problem": str(data.get("problem", "") or ""),
        "diagnosis": str(data.get("diagnosis", "") or ""),
        "actions_taken": str(data.get("actions_taken", "") or ""),
        "current_status": str(data.get("current_status", "") or ""),
        "customer_summary": str(data.get("customer_summary", "") or ""),
    }