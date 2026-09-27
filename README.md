# VERA Merchant AI - Deployment Guide

This project is configured for deployment to public cloud services like Google Cloud Run, AWS App Runner, Heroku, or any Docker-compatible hosting provider.

## Local Testing

If you have Python installed, you can test the application locally without Docker:
```bash
pip install -r requirements.txt
PORT=8080 uvicorn bot:app --host 0.0.0.0 --port 8080
```

## Docker Build & Run

To build and run the Docker image locally:
```bash
docker build -t vera-merchant-ai .
docker run -p 8080:8080 -e PORT=8080 -e GEMINI_API_KEY="your-api-key" vera-merchant-ai
```

## Cloud Deployment

### Configuration Requirements
When deploying to a cloud provider, ensure the following environment variables are set securely (do NOT commit them to code):
- `GEMINI_API_KEY` (Required for primary AI composer)
- `OPENAI_API_KEY` (Optional fallback)
- `PORT` (Most cloud services like Google Cloud Run inject this automatically. The Dockerfile respects this variable).

### Deploying to Google Cloud Run
```bash
gcloud run deploy vera-merchant-ai \
  --source . \
  --allow-unauthenticated \
  --set-env-vars="GEMINI_API_KEY=your_secret_key"
```

### Deploying to Heroku
```bash
heroku create
heroku config:set GEMINI_API_KEY=your_secret_key
git push heroku main
```
