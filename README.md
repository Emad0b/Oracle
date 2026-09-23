# O.R.A.C.L.E.

**Operational Resource for Analysis, Communication, and Logical Execution**

A JARVIS-style desktop AI assistant written in Python.

Primary interface: `python oracle.py`  
Not a website-first product. Voice + terminal first. British female neural speech.

## What works now

- Python desktop assistant loop (`python oracle.py`)
- British female spoken replies (`en-GB-SoniaNeural`)
- Wake phrase listening (`Hey Oracle`)
- Microphone speech-to-text with Whisper
- Persistent conversation memory across sessions
- Gmail + Google Calendar tools (read, send, create, cancel, move)
- Unread email digest briefings
- Open allow-listed Windows apps, URLs, and web search
- Text fallback mode if the microphone stack fails

Custom MP3 voice cloning is deferred (unstable on Python 3.14). See `BACKLOG.md`.

## Quick start

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Put your keys in `.env` (never paste them into chat):

```text
OPENAI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
TTS_VOICE=en-GB-SoniaNeural
WAKE_PHRASE=Hey Oracle
```

### Connect Google (desktop)

In Google Cloud, for your OAuth client, also allow:

```text
http://localhost
```

Then:

```powershell
python oracle.py --connect-google
```

### Run the assistant

Text-first LLM mode:

```powershell
python oracle.py
```

An **Oracle** window opens with a chat transcript and typed prompt. Oracle uses
an LLM for general requests and spaCy for simple local intent routing.

Terminal mode (no interactive window):

```powershell
python oracle.py --terminal
```

Triage Gmail job applications from the last two months:

```powershell
python oracle.py --triage-job-emails
```

This creates/applies the Gmail labels `Oracle/Jobs/Offer`,
`Oracle/Jobs/Declined`, `Oracle/Jobs/Responded`, and
`Oracle/Jobs/Awaiting Response`. Applications with **no employer reply after
21 days (3 weeks)** are counted as **declined**. Indeed receipts are
applications, not offers. Ads, housing, and roommate mail are excluded.

After triage, Oracle opens an **interactive pie chart**:
- Click a slice or legend item to filter the email list
- Click an email to preview its sender, subject, date, and body
- Hover to highlight a category
- Click **Refresh Gmail** to rescan and reconcile labels
- `python oracle.py --show-job-chart` refreshes Gmail before opening the chart

## How to talk to it

1. Run `python oracle.py`
2. Type a request and click **Send**
3. To classify applications, type: `label my job application emails from the past two months`

## Project layout

```text
oracle.py              # main text-first desktop entry
app/assistant.py       # LLM chat + local intent routing
app/nlp.py             # spaCy simple-language routing
app/job_triage.py      # conservative job-email classifier
app/llm.py             # brain + tools
app/google_*.py        # Gmail/Calendar
BACKLOG.md             # later phases
static/ + app/main.py  # optional legacy web UI
```

## Optional legacy web UI

The older FastAPI chat UI still exists if you want it:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The supported path forward is the Python desktop assistant.

## Notes

- Speech recognition uses OpenAI Whisper (`WHISPER_MODEL`)
- Spoken voice defaults to British female neural TTS
- Google tokens stay in `.data/google_token.json`
- Secrets stay in `.env`
