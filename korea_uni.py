from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
from openai import OpenAI

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
LOG = logging.getLogger("korea_uni")

BASE_URL = "https://info.korea.ac.kr/info/board/"
TIMEZONE = ZoneInfo("Asia/Seoul")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
LOOKBACK_DAYS = 7

SENDER_KEY = "1763d8030dde5f5f369ea0a088598c2fb4c792ab"
SECRET_KEY = "PuyyHGNZ"
APP_KEY = "LROcHEW7abBbFhzc"
TEMPLATE_CODE = "send-article"
PROFILE_PATH = os.getenv("PROFILE_PATH", "user_profile.json")
ALIGNMENT_THRESHOLD = int(os.getenv("ALIGNMENT_THRESHOLD", "65"))
OPENAI_MODEL = "gpt-5-nano-2025-08-07"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

RECIPIENTS = [
    {"name": "고려대 학부생 김수겸", "contact": "01068584123"},
    {"name": "고려대 학부생 고연오", "contact": "01026570090"},
]

BOARDS = [
    {"name": "학부공지", "category": "notice_under"},
    {"name": "학부장학", "category": "scholarship_under"},
    {"name": "정보대소식", "category": "news"},
    {"name": "취업정보", "category": "course_job"},
    {"name": "프로그램", "category": "course_program"},
    {"name": "인턴십", "category": "course_intern"},
    {"name": "공모전", "category": "course_competition"},
]

session = requests.Session()
profile_cache: Any | None = None
openai_client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as exc:  # pragma: no cover
        LOG.warning("Failed to init OpenAI client: %s", exc)
        openai_client = None
else:
    LOG.warning("OPENAI_API_KEY not set; alignment scoring disabled")


def load_profile() -> Any:
    global profile_cache
    if profile_cache is not None:
        return profile_cache
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as profile_file:
            profile_cache = json.load(profile_file)
            LOG.info("Loaded profile from %s", PROFILE_PATH)
    except FileNotFoundError:
        LOG.warning("Profile file %s not found; skipping alignment scoring", PROFILE_PATH)
    except json.JSONDecodeError as exc:
        LOG.error("Invalid profile JSON: %s", exc)
    return profile_cache


def score_notice(profile: dict[str, Any], notice_title: str, notice_link: str) -> tuple[bool, str]:
    if not profile:
        return False, "no-profile"
    if not openai_client:
        return False, "openai-disabled"
    profile_block = profile if isinstance(profile, str) else json.dumps(profile, ensure_ascii=False)
    user_prompt = f"""
Candidate profile text:
{profile_block}

Notice title: {notice_title}
Notice link: {notice_link}

Does this notice strongly align with the candidate’s interests and background? Reply with exactly YES or NO.
"""
    try:
        chat_api = getattr(getattr(openai_client, "chat", None), "completions", None)
        if not chat_api:
            LOG.error("OpenAI client missing chat.completions API")
            return False, "openai-unsupported"
        resp = chat_api.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": "You are an alignment checker. Respond only YES or NO."},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content if resp.choices else ""
        text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content) if isinstance(content, list) else (content or "")
        answer = text.strip().upper()
        return answer.startswith("YES"), answer or "no-answer"
    except Exception as exc:  # pragma: no cover
        LOG.error("OpenAI scoring failed: %s", exc)
        return False, "openai-error"


def send_kakao(contact: str, template_code: str, template_param: dict) -> dict[str, Any]:
    payload = {
        "senderKey": SENDER_KEY,
        "templateCode": template_code,
        "recipientList": [{"recipientNo": contact, "templateParameter": template_param}],
    }
    headers = {
        "X-Secret-Key": SECRET_KEY,
        "Content-Type": "application/json;charset=UTF-8",
    }
    url = f"https://api-alimtalk.cloud.toast.com/alimtalk/v2.2/appkeys/{APP_KEY}/messages"
    resp = session.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        LOG.error("Kakao send failed (%s) %s", resp.status_code, resp.text)
        resp.raise_for_status()
    LOG.info("Kakao send ok for %s", contact)
    if resp.headers.get("Content-Type", "").startswith("application/json"):
        return resp.json()
    return {"status": resp.status_code}


def fetch_board(board: dict[str, str]) -> tuple[str, str]:
    page_url = f"{BASE_URL}{board['category']}.do"
    resp = session.get(page_url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return page_url, resp.text


def parse_posts(html: str, base_url: str) -> list[dict[str, str]]:
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
        posts.append({"title": title, "link": urljoin(base_url, href)})
    return posts


def evaluate_posts(board_name: str, posts: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    profile = load_profile()
    aligned: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    for post in posts:
        post_copy = dict(post)
        decision, rationale = score_notice(profile, post_copy["title"], post_copy["link"])
        post_copy["reason"] = rationale
        post_copy["aligned"] = decision
        evaluated.append(post_copy)
        LOG.info(
            "[%s] %s -> %s (aligned=%s)",
            board_name,
            post_copy["title"],
            rationale,
            decision,
        )
        if decision:
            aligned.append(post_copy)
    return aligned, evaluated


def notify(board: dict[str, str], posts: list[dict[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for post in posts:
        title_prefix = "[적합]" if post.get("aligned") else ""
        title = f"{title_prefix} 고려대 정보대 공지 ({board['name']})\n\n{post['title']}"
        for target in RECIPIENTS:
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


def process_board(board: dict[str, str]) -> dict[str, Any]:
    try:
        page_url, html = fetch_board(board)
        posts = parse_posts(html, page_url)
        aligned_posts, evaluated_posts = evaluate_posts(board["name"], posts)
    except Exception as exc:
        LOG.exception("Board fetch error for %s: %s", board["name"], exc)
        return {"board": board["name"], "error": str(exc), "posts": [], "sent": [], "evaluated": []}
    sent = notify(board, aligned_posts)
    return {"board": board["name"], "posts": aligned_posts, "sent": sent, "evaluated": evaluated_posts}


def crawl() -> dict[str, Any]:
    report = []
    for board in BOARDS:
        report.append(process_board(board))
    total_posts = sum(len(entry["posts"]) for entry in report)
    return {"totalPosts": total_posts, "boards": report}


def lambda_handler(event: dict[str, Any] | None = None, context: Any | None = None) -> dict[str, Any]:
    LOG.info("Lambda trigger: %s", json.dumps(event or {}))
    return crawl()


if __name__ == "__main__":
    print(json.dumps(crawl(), ensure_ascii=False, indent=2))