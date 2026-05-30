# Daily Nexus Update

FastAPI app that produces a daily news video package for tech, finance, crypto, and geopolitics:

- uses Gemini to collect major stories and source references
- stores prior coverage in a local memory file so repeats are suppressed unless updated
- prunes detailed memory older than 90 days into a compact archive index so storage stays bounded
- captures screenshots of the reference pages
- generates story-length voiceover segments with ElevenLabs, then crossfades them into one video under 15 minutes
- optionally uploads the finished video to YouTube

## What you need to provide

1. Create a Gemini API key and place it in `.env` as `GEMINI_API_KEY`.
2. Create an ElevenLabs API key, choose a voice, and set `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`.
3. For YouTube uploads, create OAuth 2.0 desktop credentials in Google Cloud and save the downloaded client secret JSON at the path in `YOUTUBE_CLIENT_SECRETS_FILE`.
4. Run the app once and sign in to YouTube when prompted. The token file is stored at `YOUTUBE_TOKEN_FILE` and ignored by git.
5. If you want a custom font or background music, set `FONT_PATH` or `BACKGROUND_MUSIC_FILE` to local files on your machine.

## Security notes

- Keep all secrets in `.env` or the ignored `secrets/` folder.
- The local memory state lives in `data/news_memory.json` and is ignored by git.
- Older detailed records are compacted into `data/news_memory_archive.json` after 90 days.
- Do not commit OAuth tokens, client secrets, or generated media.
- The app validates URLs before screenshotting and only allows `http` / `https` targets.
- YouTube upload is opt-in through configuration, not hard-coded.

## Google TLS Certificate Update Safety (Q2 2026)

- The app does not pin Google intermediate or leaf certificates.
- By default it relies on the system CA trust store.
- If you use a custom trust store (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, or `CUSTOM_CA_BUNDLE`), include all Google Trust Services roots.
- On startup, the app runs a TLS guard and logs warnings if custom trust-store configuration looks risky.
- Health endpoint will report `tls=warning` if potential trust-store issues are detected.

## Timing rules

- Each story is allotted a shorter segment (default 30 to 90 seconds) depending on importance.
- The pipeline keeps the final cut under 5 minutes by budgeting intro, story, and outro durations.
- Story audio fades out at the end of each segment, and the next story fades in cleanly.

## Retry behavior for busy providers

- Transient Gemini and ElevenLabs errors (for example 429/503/high demand/timeouts) are retried automatically.
- Default retry policy waits 5 minutes between attempts.
- Retry settings in `.env`:
	- `RETRY_MAX_ATTEMPTS` (default `3`)
	- `RETRY_DELAY_SECONDS` (default `300`)
	- `RETRY_BACKOFF_MULTIPLIER` (default `1.0` for fixed delay)
- Job status message shows when a retry is pending and how long until the next attempt.

## Output folder naming

- Each pipeline run now creates a timestamped folder under `OUTPUT_DIR`.
- Format: `YYYY-MM-DD_HH-MM-SS` (with a numeric suffix if two runs start in the same second).
- This makes each run easy to identify by date/time instead of job/session ID.

## Failure email notifications

- If a job fails after all retries, the app can send an email notification.
- Configure these in `.env`:
	- `FAILURE_EMAIL_ENABLED=true`
	- `FAILURE_EMAIL_TO=you@example.com`
	- `FAILURE_EMAIL_FROM=you@example.com`
	- `FAILURE_EMAIL_SUBJECT_PREFIX=[Daily Nexus Update]`
	- `SMTP_HOST=smtp.yourprovider.com`
	- `SMTP_PORT=587`
	- `SMTP_USERNAME=you@example.com`
	- `SMTP_PASSWORD=app-password-or-smtp-password`
	- `SMTP_USE_TLS=true`
- Email is sent only on final failure (not on intermediate retries).

## Setup with UV

```powershell
uv sync
uv run playwright install chromium
cp .env.example .env
```

If you are on Windows and `cp` is unavailable, copy `.env.example` to `.env` in Explorer or use `Copy-Item .env.example .env`.

## Run

```powershell
uv run uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` and trigger a job from the dashboard.

## YouTube upload flow

1. Enable the YouTube Data API v3 in your Google Cloud project.
2. Create OAuth desktop credentials.
3. Download the client secret JSON and store it outside git.
4. Launch a job with `publish_to_youtube` enabled in the UI or request payload.
5. Complete browser consent once; future runs reuse the saved token file.

## Project layout

- `app/` application code
- `app/services/` API clients and media pipeline steps
- `templates/` dashboard UI
- `static/` styling

