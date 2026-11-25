from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from cloud_common import db, setting

BASE = Path(__file__).parent


def seed_questions(client):
    existing = client.table("questions").select("id").limit(1).execute().data
    if existing:
        return
    section = "Imported questions"
    records = []
    for line in (BASE / "questions.txt").read_text(encoding="utf-8-sig").splitlines():
        heading = re.match(r"^\s*[A-Z]\.\s*(.+?)\s*\(\d+\s*[–-]\s*\d+\)\s*$", line)
        if heading:
            section = heading.group(1).strip()
            continue
        item = re.match(r"^\s*(\d+)\s*[.)]\s*(.+?)\s*$", line)
        if item:
            records.append({"sequence_no": int(item.group(1)), "topic": section, "question": item.group(2)})
    if records:
        client.table("questions").upsert(records, on_conflict="sequence_no").execute()


def gemini_json(prompt: str) -> dict:
    key = setting("GEMINI_API_KEY")
    model = setting("GEMINI_MODEL", "gemini-2.5-flash")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY in GitHub Actions secrets. Local Ollama cannot run when your PC is off.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    response = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7, "maxOutputTokens": 6000},
    }, timeout=600)
    response.raise_for_status()
    result = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    result = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", result.strip())
    return json.loads(result)


def draft_prompt(question: str, examples: list[str]) -> str:
    examples_text = "\n\n--- SAMPLE POST ---\n\n".join(examples[:10]) or "No writing samples have been added yet. Use a concise, practical, technically clear voice."
    return f"""Create today's content from this technical interview question: {question}

Write a Substack article in Markdown, about 1,500 words. Use this structure, adapted naturally: open with the main trade-off; state assumptions and constraints; compare multiple approaches; explain a recommended design and why; discuss scaling, failure modes, and operations; show code/architecture only where useful; end with interview framing, a one-line takeaway, and 3-5 FAQs. Be technically careful. Do not invent citations, benchmark numbers, or personal anecdotes.

Then write a LinkedIn version of 120-220 words. Start with a concrete insight or question, offer one useful detail, and invite readers to read the full article. Include the exact placeholder [SUBSTACK_URL] once.

Match the author's writing style from these examples. Infer sentence length, paragraph rhythm, headings, use of questions, vocabulary, and tone. Do not copy any sentence or claim from a sample. Do not claim that these examples are externally available.

STYLE EXAMPLES:
{examples_text}

Return only a JSON object with keys title, subtitle, article, linkedin. The article should target about 1,500 words; the LinkedIn field should be 120-220 words."""


def send_telegram(text: str, url: str) -> None:
    token, chat_id = setting("TELEGRAM_BOT_TOKEN"), setting("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in GitHub Actions secrets.")
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": [[{"text": "Open review and approval", "url": url}]]},
    }, timeout=30)
    response.raise_for_status()


def main():
    client = db()
    seed_questions(client)
    today = datetime.now(ZoneInfo("Asia/Singapore")).date().isoformat()
    existing = client.table("posts").select("id,status").eq("scheduled_date", today).limit(1).execute().data
    if existing:
        row = existing[0]
        if row["status"] == "pending_substack":
            app_url = setting("APP_URL", "").rstrip("/")
            send_telegram(f"Today's content draft is ready for review. Publish the Substack article, then add its URL and approve the LinkedIn post.", f"{app_url}/?draft={row['id']}")
        return

    questions = client.table("questions").select("id,sequence_no,topic,question").order("sequence_no").execute().data
    if not questions:
        raise RuntimeError("No interview questions were found. Add questions in the app or check questions.txt.")
    override = client.table("app_settings").select("value").eq("name", "next_question_id").limit(1).execute().data
    if override and override[0]["value"]:
        selected = next((q for q in questions if str(q["id"]) == override[0]["value"]), None)
    else:
        successful = client.table("posts").select("id").execute().data
        selected = questions[len(successful) % len(questions)]
    if selected is None:
        selected = questions[0]

    examples = client.table("style_examples").select("body").order("created_at", desc=True).limit(10).execute().data
    generated = gemini_json(draft_prompt(selected["question"], [r["body"] for r in examples]))
    article = str(generated.get("article", "")).strip()
    linkedin = str(generated.get("linkedin", "")).strip()
    if len(article.split()) < 1000 or len(linkedin.split()) < 80:
        generated = gemini_json(draft_prompt(selected["question"], [r["body"] for r in examples]) + "\n\nIMPORTANT: Your previous answer was too short. The article must contain at least 1,200 words and the LinkedIn adaptation must be 120-220 words.")
        article = str(generated.get("article", "")).strip()
        linkedin = str(generated.get("linkedin", "")).strip()
    if len(article.split()) < 1000 or len(linkedin.split()) < 80:
        raise RuntimeError("The model returned content that was too short; no draft was saved. Run the workflow again to retry.")

    row = client.table("posts").insert({
        "scheduled_date": today,
        "question_id": selected["id"],
        "question": selected["question"],
        "title": str(generated.get("title") or selected["question"]),
        "article": article,
        "linkedin_text": linkedin,
        "status": "pending_substack",
    }).execute().data[0]
    if override:
        client.table("app_settings").upsert({"name": "next_question_id", "value": ""}).execute()

    app_url = setting("APP_URL", "").rstrip("/")
    if not app_url:
        raise RuntimeError("Set APP_URL in GitHub Actions secrets before enabling the schedule.")
    send_telegram("Today's article and LinkedIn draft are ready. Publish the article on Substack, add its URL, then approve the LinkedIn post.", f"{app_url}/?draft={row['id']}")
    print(f"Generated draft {row['id']} for question #{selected['sequence_no']} on {today}")


if __name__ == "__main__":
    main()
