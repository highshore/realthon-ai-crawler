# Korea University Informatics Crawler

This repository now only contains the single-purpose scraper used to watch Korea University College of Informatics boards and send Kakao Alimtalk notifications through NHN Toast.

## Files

| File | Purpose |
| --- | --- |
| `korea_uni.py` | Fetches configured boards, filters posts from the past week, and sends Kakao messages to the two predefined contacts. |
| `requirements.txt` | Python dependencies (requests, BeautifulSoup). |
| `Dockerfile` | AWS Lambda container image definition (Python 3.11 base). |

## Running locally

```bash
pip install -r requirements.txt
python korea_uni.py
```

All Kakao credentials, recipients, and board lists are hard-coded to match the original Apps Script. Adjust the constants near the top of `korea_uni.py` if you need to change recipients, sender keys, or the lookback window.

## Lambda deployment (container image)

1. Build and push the image:
   ```bash
   docker buildx build --platform linux/amd64 -t 495599734093.dkr.ecr.ap-northeast-2.amazonaws.com/korea-uni-lambda:latest . --push
   ```
2. Create or update the function:
   ```bash
   aws lambda create-function \
     --function-name korea-uni-crawler \
     --package-type Image \
     --code ImageUri=495599734093.dkr.ecr.ap-northeast-2.amazonaws.com/korea-uni-lambda:latest \
     --role arn:aws:iam::<account-id>:role/korea-uni-lambda-exec
   # or, for existing functions:
   aws lambda update-function-code --function-name korea-uni-crawler \
     --image-uri 495599734093.dkr.ecr.ap-northeast-2.amazonaws.com/korea-uni-lambda:latest
   ```
3. Give the role `lambda.amazonaws.com` assume permissions and attach `AWSLambdaBasicExecutionRole` so logs reach CloudWatch.
4. Increase timeout/memory as needed (current production values: 60 s timeout, 512 MB memory).

## Scheduling

Use Amazon EventBridge (CloudWatch Events) to run the Lambda on your preferred cadence. No additional infrastructure files are required in this repo.

