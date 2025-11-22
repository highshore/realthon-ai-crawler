from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
LOG = logging.getLogger("korea_university")

BASE_URL_DEFAULT = "https://info.korea.ac.kr/info/board/"
TIMEZONE = ZoneInfo("Asia/Seoul")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))

SENDER_KEY = "1763d8030dde5f5f369ea0a088598c2fb4c792ab"
SECRET_KEY = "PuyyHGNZ"
APP_KEY = "LROcHEW7abBbFhzc"
TEMPLATE_CODE = "send-article"
OPENAI_MODEL = "gpt-5-nano-2025-08-07"
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "20"))

RECIPIENTS_DEFAULT = [
    {"name": "고려대 학부생 김수겸", "contact": "01068584123"},
    {"name": "고려대 학부생 고연오", "contact": "01026570090"},
]

BOARDS_DEFAULT = [
    {"name": "학부공지", "category": "notice_under"},
    {"name": "학부장학", "category": "scholarship_under"},
    {"name": "정보대소식", "category": "news"},
    {"name": "취업정보", "category": "course_job"},
    {"name": "프로그램", "category": "course_program"},
    {"name": "인턴십", "category": "course_intern"},
    {"name": "공모전", "category": "course_competition"},
]

if not OPENAI_API_KEY:
    LOG.warning("OPENAI_API_KEY is missing; alignment scoring disabled")

session = requests.Session()


def normalize_base(url: str | None) -> str:
    if not url:
        return BASE_URL_DEFAULT
    trimmed = url.strip()
    if trimmed.endswith(".do"):
        trimmed = trimmed[: trimmed.rfind("/") + 1]
    return f"{trimmed.rstrip('/')}/"


def score_notice(profile_text: str, title: str, link: str) -> tuple[bool, str]:
    if not profile_text:
        return False, "no-profile"
    if not OPENAI_API_KEY:
        return False, "openai-disabled"
    user_prompt = f"""
Candidate profile text:
{profile_text}

Notice title: {title}
Notice link: {link}

Does this notice strongly align with the candidate’s interests and background? Reply with exactly YES or NO.
"""
    try:
        response = session.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are an alignment checker. Respond only YES or NO."},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=OPENAI_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        body = response.text if response is not None else ""
        status = response.status_code if response is not None else "no-status"
        LOG.error("OpenAI scoring failed (%s): %s | %r", status, body[:300], exc)
        return False, "openai-error"
    except requests.RequestException as exc:
        LOG.error("OpenAI scoring failed: %s", exc)
        return False, "openai-error"
    except ValueError:
        LOG.error("OpenAI response not valid JSON")
        return False, "openai-invalid-response"

    answer_text = ""
    for choice in data.get("choices", []):
        message = choice.get("message") or {}
        content = message.get("content")
        if content:
            answer_text = content
            break

    answer = (answer_text or "").strip().upper()
    if answer.startswith("YES"):
        return True, answer or "YES"
    if answer.startswith("NO"):
        return False, answer or "NO"
    LOG.warning("OpenAI response not YES/NO: %s", answer)
    return False, answer or "no-answer"


def send_kakao(contact: str, template_code: str, template_param: dict[str, str]) -> dict[str, Any]:
    payload = {
        "senderKey": SENDER_KEY,
        "templateCode": template_code,
        "recipientList": [{"recipientNo": contact, "templateParameter": template_param}],
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


def fetch_board(base_url: str, board: dict[str, str]) -> tuple[str, str]:
    page_url = f"{base_url}{board['category']}.do"
    resp = session.get(page_url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return page_url, resp.text


def parse_posts(html: str, page_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    today = datetime.now(TIMEZONE).date()
    cutoff = today - timedelta(days=LOOKBACK_DAYS - 1)
    posts: list[dict[str, str]] = []
    for row in soup.select("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        date_text = cells[-1].get_text(strip=True)
        try:
            row_date = datetime.strptime(date_text, "%Y.%m.%d").date()
        except ValueError:
            continue
        if row_date < cutoff:
            continue
        link_tag = row.select_one("a.article-title")
        if not link_tag:
            continue
        href = (link_tag.get("href") or "").replace("amp;", "")
        title = link_tag.get_text(strip=True)
        posts.append({"title": title, "link": urljoin(page_url, href)})
    return posts


def evaluate_posts(profile_text: str, board_name: str, posts: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    aligned: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    for post in posts:
        post_copy = dict(post)
        decision, rationale = score_notice(profile_text, post_copy["title"], post_copy["link"])
        post_copy["reason"] = rationale
        post_copy["aligned"] = decision
        evaluated.append(post_copy)
        if decision:
            aligned.append(post_copy)
    return aligned, evaluated


def notify(board: dict[str, str], posts: list[dict[str, Any]], recipients: list[dict[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for post in posts:
        title_prefix = "[적합]" if post.get("aligned") else ""
        title = f"{title_prefix} 고려대 정보대 공지 ({board['name']})\n\n{post['title']}"
        for target in recipients:
            params = {
                "korean-title": title,
                "customer-name": target["name"],
                "article-link": post["link"],
            }
            try:
                data = send_kakao(target["contact"], TEMPLATE_CODE, params)
                results.append(
                    {
                        "board": board["name"],
                        "title": post["title"],
                        "recipient": target["contact"],
                        "status": data,
                    }
                )
            except Exception as exc:
                LOG.exception("Kakao send error: %s", exc)
                results.append(
                    {
                        "board": board["name"],
                        "title": post["title"],
                        "recipient": target["contact"],
                        "error": str(exc),
                    }
                )
    return results


def process_board(board: dict[str, str], base_url: str, profile_text: str, recipients: list[dict[str, str]]) -> dict[str, Any]:
    try:
        page_url, html = fetch_board(base_url, board)
        posts = parse_posts(html, page_url)
        aligned, evaluated = evaluate_posts(profile_text, board["name"], posts)
    except Exception as exc:
        LOG.exception("Board fetch error for %s: %s", board["name"], exc)
        return {"board": board["name"], "error": str(exc), "posts": [], "sent": [], "evaluated": []}
    sent = notify(board, aligned, recipients)
    return {"board": board["name"], "posts": aligned, "sent": sent, "evaluated": evaluated}


def run(event: dict[str, Any], context: Any | None = None) -> dict[str, Any]:
    payload = event or {}
    profile_text = payload.get("user_profile")
    if not profile_text:
        raise ValueError("user_profile is required")
    base_candidate = payload.get("base_url") or payload.get("url")
    base_url = normalize_base(base_candidate)
    recipients = payload.get("recipients")
    boards = payload.get("boards")
    recipients = recipients if isinstance(recipients, list) and recipients else RECIPIENTS_DEFAULT
    boards = boards if isinstance(boards, list) and boards else BOARDS_DEFAULT
    report = []
    for board in boards:
        report.append(process_board(board, base_url, profile_text, recipients))
    total_posts = sum(len(entry["posts"]) for entry in report)
    return {"totalPosts": total_posts, "boards": report}


if __name__ == "__main__":
    profile_path = os.getenv("PROFILE_PATH", "user_profile.json")
    if os.path.isfile(profile_path):
        with open(profile_path, "r", encoding="utf-8") as profile_file:
            profile_text = profile_file.read()
        print(json.dumps(run({"user_profile": profile_text, "base_url": BASE_URL_DEFAULT}), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("user_profile.json not found")

