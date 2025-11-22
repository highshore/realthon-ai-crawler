from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
LOG = logging.getLogger("firecrawl_fallback")

FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v2/scrape")
FIRECRAWL_API_KEY = os.getenv(
    "FIRECRAWL_API_KEY",
    "fc-336503610b404829953273c9397bba11",
)

OPENAI_MODEL = "gpt-5-nano-2025-08-07"
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "90"))

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))

SENDER_KEY = "1763d8030dde5f5f369ea0a088598c2fb4c792ab"
SECRET_KEY = "PuyyHGNZ"
APP_KEY = "LROcHEW7abBbFhzc"
TEMPLATE_CODE = "send-article"

RECIPIENTS_DEFAULT = [
    {"name": "고려대 학부생 김수겸", "contact": "01068584123"},
    {"name": "고려대 학부생 고연오", "contact": "01026570090"},
]

session = requests.Session()
if not OPENAI_API_KEY:
    LOG.warning("OPENAI_API_KEY missing; fallback alignment disabled")


def scrape_markdown(url: str) -> str:
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"url": url, "formats": ["markdown"]}
    resp = session.post(FIRECRAWL_API_URL, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        LOG.error("Firecrawl scrape failed (%s): %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
    data = resp.json()
    markdown = (((data.get("data") or {}) if data else {}).get("markdown")) if data else None
    if not markdown:
        raise RuntimeError("Firecrawl returned no markdown")
    return markdown


def extract_posts(markdown: str) -> list[dict[str, str]]:
    if not OPENAI_API_KEY:
        return []
    system_prompt = (
        "You are a parser that extracts postings from markdown. "
        "Return JSON array objects with 'title' and 'link'. "
        "Ignore duplicates and skip entries without URLs."
    )
    user_prompt = (
        "Extract posting title and link pairs from the markdown below.\n"
        "Respond with JSON only.\n\n"
        f"{markdown}"
    )
    try:
        resp = session.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=OPENAI_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        LOG.error("OpenAI extraction failed: %s", exc)
        return []
    except ValueError:
        LOG.error("OpenAI extraction invalid JSON")
        return []

    content = ""
    for choice in data.get("choices", []):
        message = choice.get("message") or {}
        if message.get("content"):
            content = message["content"]
            break
    if not content:
        return []
    try:
        posts = json.loads(content)
        if isinstance(posts, list):
            cleaned = []
            for item in posts:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "").strip()
                link = (item.get("link") or "").strip()
                if title and link:
                    cleaned.append({"title": title, "link": link})
            return cleaned
    except json.JSONDecodeError:
        LOG.error("OpenAI extraction response not JSON: %s", content[:200])
    return []


def score_notice(profile_text: str, title: str, link: str) -> tuple[bool, str]:
    if not profile_text:
        return False, "no-profile"
    if not OPENAI_API_KEY:
        return False, "openai-disabled"
    prompt = f"""
Candidate profile text:
{profile_text}

Posting title: {title}
Posting link: {link}

Does this posting strongly align with the candidate’s interests? Reply with exactly YES or NO.
"""
    try:
        resp = session.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "Respond only YES or NO."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=OPENAI_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        body = exc.response.text if getattr(exc, "response", None) else ""
        code = exc.response.status_code if getattr(exc, "response", None) else "no-status"
        LOG.error("OpenAI scoring failed (%s): %s", code, body[:300])
        return False, "openai-error"
    except requests.RequestException as exc:
        LOG.error("OpenAI scoring failed: %s", exc)
        return False, "openai-error"
    except ValueError:
        LOG.error("OpenAI scoring invalid JSON")
        return False, "openai-invalid-response"

    answer = ""
    for choice in data.get("choices", []):
        msg = choice.get("message") or {}
        if msg.get("content"):
            answer = msg["content"]
            break
    text = (answer or "").strip().upper()
    if text.startswith("YES"):
        return True, text or "YES"
    if text.startswith("NO"):
        return False, text or "NO"
    LOG.warning("OpenAI scoring unexpected answer: %s", text)
    return False, text or "no-answer"


def send_kakao(contact: str, template_code: str, params: dict[str, str]) -> dict[str, Any]:
    payload = {
        "senderKey": SENDER_KEY,
        "templateCode": template_code,
        "recipientList": [{"recipientNo": contact, "templateParameter": params}],
    }
    headers = {"X-Secret-Key": SECRET_KEY, "Content-Type": "application/json;charset=UTF-8"}
    url = f"https://api-alimtalk.cloud.toast.com/alimtalk/v2.2/appkeys/{APP_KEY}/messages"
    resp = session.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        LOG.error("Kakao send failed (%s) %s", resp.status_code, resp.text)
        resp.raise_for_status()
    if resp.headers.get("Content-Type", "").startswith("application/json"):
        return resp.json()
    return {"status": resp.status_code}


def notify(posts: list[dict[str, Any]], recipients: list[dict[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for post in posts:
        title = f"[Firecrawl] {post['title']}"
        for target in recipients:
            params = {
                "korean-title": title,
                "customer-name": target["name"],
                "article-link": post["link"],
            }
            try:
                data = send_kakao(target["contact"], TEMPLATE_CODE, params)
                results.append({"title": post["title"], "recipient": target["contact"], "status": data})
            except Exception as exc:  # pragma: no cover
                LOG.exception("Kakao send error: %s", exc)
                results.append({"title": post["title"], "recipient": target["contact"], "error": str(exc)})
    return results


def run(event: dict[str, Any] | None = None, context: Any | None = None) -> dict[str, Any]:
    payload = event or {}
    url = payload.get("url")
    if not url:
        raise ValueError("url is required for Firecrawl fallback")
    profile_text = payload.get("user_profile")
    if not profile_text:
        raise ValueError("user_profile is required")
    recipients = payload.get("recipients")
    recipients = recipients if isinstance(recipients, list) and recipients else RECIPIENTS_DEFAULT

    markdown = scrape_markdown(url)
    posts = extract_posts(markdown)
    LOG.info("Firecrawl extracted %s candidate posts from %s", len(posts), url)
    aligned_posts: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    for post in posts:
        entry = dict(post)
        decision, reason = score_notice(profile_text, entry["title"], entry["link"])
        entry["aligned"] = decision
        entry["reason"] = reason
        evaluated.append(entry)
        if decision:
            aligned_posts.append(entry)
    sent = notify(aligned_posts, recipients)
    return {
        "source": "firecrawl_fallback",
        "url": url,
        "count": len(evaluated),
        "aligned": len(aligned_posts),
        "posts": evaluated,
        "sent": sent,
    }


if __name__ == "__main__":
    demo_profile = os.getenv(
        "FIRECRAWL_PROFILE",
        "Demo profile: generalist student exploring all opportunities.",
    )
    print(run({"url": "https://firecrawl.dev", "user_profile": demo_profile}))

