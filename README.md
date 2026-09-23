# Oracle

**Operational Resource for Analysis, Communication, and Logical Execution**

A text-first Python desktop assistant with Gmail job-application triage.

Oracle chats in a Tkinter window (or the terminal), uses an LLM for general requests, and uses spaCy for simple local intents such as “show my job chart”. It can classify recent job-application email threads into **Offer**, **Declined**, **Responded / In Progress**, and **Awaiting Response**, then open an interactive pie chart.

## Features

- Desktop chat UI (`python oracle.py`) and terminal mode (`--terminal`)
- Gmail + Google Calendar tools (read, send, create, cancel, move)
- Conservative job-email classifier (platform receipts are applications, not offers)
- **21-day silence rule**: no meaningful employer reply after 21 days counts as declined
- Incremental Gmail snapshots so later refreshes only pull new mail
- Interactive pie chart: click a slice, preview an email, refresh Gmail
- Local conversation memory (stored on disk, not in git)

## Requirements

- Python 3.11+ (3.12 recommended)
- OpenAI API key (or an OpenAI-compatible provider)
- Optional: a Google Cloud OAuth client with Gmail and Calendar APIs enabled

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
Copy-Item .env.example .env
```

Edit `.env` with your own keys. Never commit that file.

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/google/callback
```

Run the assistant:

```powershell
.\.venv\Scripts\python.exe oracle.py
```

Terminal mode:

```powershell
.\.venv\Scripts\python.exe oracle.py --terminal
```

## Connect Google

1. In [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials), create an OAuth **Web** or desktop client.
2. Add this **Authorized redirect URI** exactly:

   ```text
   http://127.0.0.1:8000/api/google/callback
   ```

3. Enable the Gmail API and Google Calendar API.
4. Put the client ID and secret in `.env`.
5. Sign in:

```powershell
.\.venv\Scripts\python.exe oracle.py --connect-google
.\.venv\Scripts\python.exe oracle.py --status
```

Tokens are saved locally in `.data/google_token.json` and are gitignored.

## Job application triage

Scan (or incrementally refresh) the last two months of Gmail and open the chart:

```powershell
.\.venv\Scripts\python.exe oracle.py --show-job-chart
```

Force a full two-month rescan:

```powershell
.\.venv\Scripts\python.exe oracle.py --show-job-chart --full-rescan
```

Label threads without changing the usual chart flow:

```powershell
.\.venv\Scripts\python.exe oracle.py --triage-job-emails
```

Gmail labels applied:

| Category | Gmail label |
| --- | --- |
| Offer | `Oracle/Jobs/Offer` |
| Declined (explicit or 21-day timeout) | `Oracle/Jobs/Declined` |
| Recruiter reply / next stage | `Oracle/Jobs/Responded` |
| Applied, still inside 21 days | `Oracle/Jobs/Awaiting Response` |

**How categories are chosen**

- **Awaiting**: application evidence exists, and there is no meaningful employer reply yet.
- **Responded / in progress**: a real recruiter step (interview, assessment, “next stage”, shortlist, written questions).
- **Declined**: explicit rejection language, or 21 days with no real reply.
- **Offer**: explicit offer wording only. Indeed/Lever receipts are **not** offers.

Ads, housing/roommate mail, job alerts, and incomplete-application nags are excluded.

Each successful scan writes a snapshot to `.data/job_triage_latest.json`. Later runs download mail **since that snapshot**, re-label new threads, and re-label threads whose category changed (including 21-day timeouts). That file contains your subjects and senders — it is not committed.

## Privacy

This repo is meant to be public. Keep secrets and mailbox data off GitHub:

| Kept local (gitignored) | Safe to commit |
| --- | --- |
| `.env` | `.env.example` (placeholders only) |
| `.data/` (tokens, chat memory, triage snapshot) | Source under `app/` |
| `.venv/` | `requirements.txt` |
| `credentials.json`, `token.json`, `*.pem` | This README |

Do not put API keys, OAuth client secrets, or Gmail exports in issues, commits, or the README.

## Project layout

```text
oracle.py              # CLI + desktop entry
app/assistant.py       # chat loop and job-chart intents
app/nlp.py             # spaCy routing
app/job_triage.py      # classifier + incremental snapshot
app/job_chart.py       # interactive pie chart
app/google_auth.py     # OAuth
app/google_services.py # Gmail / Calendar API
app/llm.py             # model + tools
scripts/               # audits and one-off helpers
static/ + app/main.py  # optional legacy web UI
```

## Optional legacy web UI

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The supported path is the desktop assistant, not the website.

## License

Use and modify for your own setup. Add a `LICENSE` file if you want a specific open-source grant.
