# Multi-script Lambda Notice Router

One Lambda container receives a JSON payload, routes it by `url`, and executes the matching crawler script. Each script is responsible for fetching notices, calling OpenAI for profile alignment, and (optionally) delivering Kakao Alimtalk messages.

## Layout

| Path | Purpose |
| --- | --- |
| `app/router.py` | Lambda entrypoint; inspects `event["url"]` and dispatches to the right job. |
| `app/jobs/korea_university.py` | Job implementation for Korea University Informatics boards. |
| `app/jobs/linkareer.py` | Job that scrapes Linkareer intern listings, scores them, and sends Kakao alerts. |
| `app/jobs/ewha_university.py` | Crawls Ewha Womans University notices, aligns, and notifies. |
| `app/jobs/sogang_university.py` | Crawls Sogang University API notices, aligns, and notifies. |
| `app/jobs/firecrawl_fallback.py` | Generic fallback: Firecrawl scrape → OpenAI extraction → alignment → Kakao. |
| `frontend/` | Next.js React frontend for interacting with the crawler. |
| `requirements.txt` | Runtime dependencies (requests, BeautifulSoup, OpenAI). |
| `Dockerfile` | AWS Lambda container image definition (Python 3.11). |
| `.env.local` | Local-only secrets (e.g., `OPENAI_API_KEY`), ignored by git. |

Add new jobs under `app/jobs/` and register them inside `app/router.py` with a matcher function.

## Event contract

Example payload:

```json
{
  "url": "https://info.korea.ac.kr/info/board/notice_under.do",
  "user_profile": "Raw text used for OpenAI alignment",
  "recipients": [
    {"name": "고려대 학부생 김수겸", "contact": "01068584123"}
  ]
}
```

Fields:
- `url` – set it to the concrete board URL (e.g. `.../notice_under.do`). The router strips the suffix and routes anything under `https://info.korea.ac.kr/info/board/` to the KU job.
- `user_profile` – raw text describing the candidate (required).
- `base_url` – optional override. If omitted, the job derives the base from `url`.
- `recipients` / `boards` – optional overrides; defaults mirror the original Apps Script.
- Jobs can accept any additional fields; the router forwards the full payload.

### Linkareer job example

```json
{
  "url": "https://linkareer.com/list/intern?filterBy_activityTypeID=5&filterBy_categoryIDs=58&filterBy_jobTypes=INTERN&filterBy_regionIDs=2&filterBy_status=OPEN&orderBy_direction=DESC&orderBy_field=RECENT&page=1",
  "user_profile": "Demo profile for Linkareer: CS student interested in AI/ML internships.",
  "recipients": [
    {"name": "고려대 학부생 김수겸", "contact": "01068584123"}
  ]
}
```

Router output:

```json
{
  "statusCode": 200,
  "body": {
    "source": "linkareer",
    "count": 20,
    "aligned": 3,
    "listings": [
      {"company": "...", "title": "...", "link": "...", "aligned": true, "reason": "YES"}
    ],
    "sent": [
      {"title": "...", "recipient": "010....", "status": {...}}
    ]
  },
  "script": "linkareer"
}
```

The Linkareer job drives headless Chromium via Selenium inside the Lambda container so that dynamic rows load before OpenAI scoring and Kakao delivery.

### Ewha / Sogang examples

- Ewha: set `url` to any page under `https://www.ewha.ac.kr/` (e.g. `https://www.ewha.ac.kr/ewha/news/notice.do`). The router will invoke `ewha_university.run`.
- Sogang: set `url` to any `https://www.sogang.ac.kr/...` URL to route to `sogang_university.run`.

Both jobs expect the same payload fields (`user_profile`, optional `recipients`) and return `{"count": ...,"aligned": ...,"posts": [...],"sent": [...]}`.

### Firecrawl fallback

If a URL does **not** match any of the explicit routes, the router automatically calls `firecrawl_fallback.run`. It:

1. Uses the Firecrawl API (`FIRECRAWL_API_KEY`) in scrape mode to fetch markdown for the page.
2. Calls OpenAI to extract posting `{title, link}` pairs from the markdown.
3. Runs the usual YES/NO profile alignment and Kakao notifications against the extracted posts.

Set `FIRECRAWL_API_KEY` in your environment (defaults to the provided demo key).

```bash
export FIRECRAWL_API_KEY=fc-...
```

## Frontend

The project includes a Next.js frontend for easy interaction.

1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Open [http://localhost:3000](http://localhost:3000) in your browser.
5. Enter your Lambda Function URL (ensure it supports CORS or use the built-in proxy) and configure your crawl request.

## Local testing

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
python -m app.jobs.korea_university <<'EOF'
{"user_profile": "paste corpus text", "url": "https://info.korea.ac.kr/info/board/"}
EOF
```

For router-level testing:

```bash
python -m app.router <<'EOF'
{"url": "https://info.korea.ac.kr/info/board/","user_profile":"..."}
EOF
```

## OpenAI alignment

- Set `OPENAI_API_KEY` in the Lambda environment (or `.env.local` locally).
- The job asks `gpt-5-nano-2025-08-07` if each notice aligns with the provided profile and expects `YES`/`NO`.
- A `YES` result both returns the notice in the payload and triggers Kakao notifications.
- If the API key is missing, alignment is skipped and notices are treated as non-aligned.

## Lambda deployment (container image)

```bash
docker buildx build --platform linux/amd64 \
  -t 495599734093.dkr.ecr.ap-northeast-2.amazonaws.com/korea-uni-lambda:latest . --push

aws lambda update-function-code \
  --function-name korea-uni-crawler \
  --image-uri 495599734093.dkr.ecr.ap-northeast-2.amazonaws.com/korea-uni-lambda:latest
```

Set the handler to `app.router.lambda_handler` (default when using this Dockerfile). Keep the Lambda role, timeout (120 s), and memory (1024 MB) as currently configured for Selenium.

## Scheduling

Trigger the router Lambda via EventBridge or any custom integration. Include the JSON payload described above so the router knows which job to run.
