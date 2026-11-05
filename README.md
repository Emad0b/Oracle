# Oracle

**Operational Resource for Analysis, Communication, and Logical Execution**

A Python personal assistant with a local web dashboard: API-backed reasoning,
planning, communication, productivity tools, and configurable IoT integration.

## Start Oracle

```powershell
.\.venv\Scripts\python.exe oracle.py
```

Oracle starts at `http://127.0.0.1:8000` and opens your default browser once the
server is ready. Keep the terminal running; press Ctrl+C to stop the server.
Use `--no-browser` to start without opening a tab. If port 8000 is busy, stop the
existing server before restarting. The server binds only to your own computer.

The dashboard includes Overview, Ask Oracle, MyMoney, Devices and Connections.
Connections shows missing credentials, revoked Google sessions, Google API access
failures, provider authentication/quota errors and unreachable Home Assistant.
Use **Configure** to save credentials locally, **Reconnect Google** to sign in,
and **Test API** to send a short model request (which may use API credit).
The API is marked untested until a test or chat request succeeds; storing a key
does not prove that billing or model access works. Connections refreshes each
minute while the page is visible. Google and IoT checks do not invoke the LLM.

Credentials are write-only from the dashboard and saved in ignored `.env`.
Google OAuth must use `http://127.0.0.1:8000/api/google/callback` (or the matching
localhost URL) registered in Google Cloud. Enable both Gmail and Calendar APIs.
OAuth failures return to the dashboard; callback codes are not logged.
Foreign origins and unsafe requests without the local-dashboard header are
rejected. This is a local single-user app, not an authenticated hosted service.

## MyMoney — private local budgeting

Open **MyMoney** in Oracle's sidebar, or run:

```powershell
.\.venv\Scripts\python.exe oracle.py --money
```

Manage actual transactions, recurring bills and expected income, savings pots,
daily/weekly allowances, shortfall warnings and a 90-day cashflow forecast.
This workspace is served locally. It works without an API
key and keeps financial records in ignored `.data/finance.sqlite3`.
No financial database is included in GitHub or the source-only E: release.
See [MyMoney setup, calculations and privacy](docs/MYMONEY.md).

## Assistant mode

Run `.\.venv\Scripts\python.exe oracle.py`. Use the web workspace sidebar,
starter cards, or type natural-language requests. General conversation
requires a working `OPENAI_API_KEY` and sufficient provider quota. Set
`OPENAI_MODEL` and optionally `OPENAI_BASE_URL` for your compatible provider.

### Legacy desktop workspace

Use `python oracle.py --desktop` for the previous Tkinter interface and its
screen-preview, API speech and device-monitor controls. The default web interface
offers browser dictation when supported; it may use the browser's speech service.
Dictation is a draft until sent. Web chat history is held in the tab's memory and
is cleared when the page reloads; it does not load desktop conversation history.

The native desktop GUI includes a dark navy theme, a focused conversation area,
starter prompts, and a sidebar for capabilities, devices, preferences and
monitoring. Starter cards fill a draft; press Send when ready. Enter sends a
message and Ctrl+L focuses the composer. Voice, screen and read-aloud controls
sit below the input. Connections & privacy explains integration status and data
sharing without displaying keys. Clear conversation asks before deleting saved
chat history. The layout adapts down to 880 × 680 and requires no new GUI package.

Try `help`, `list devices`, `turn on the study light`, or ask Oracle to plan a task.
The first two commands work without an LLM call. Device commands through natural
language use the LLM tools.

### IoT monitoring cards

Create and rename monitoring cards in Devices, capture timestamped readings, and see saved cards in Overview. To ask about device readings, explicitly share them for a chat message. See [device setup](docs/DEVICES.md) for Arduino, Raspberry Pi and Home Assistant.

### IoT without hardware

`IOT_BACKEND=demo` is the default. A study light, desk lamp and temperature sensor
are explicitly simulated; their state resets when Oracle exits. No physical
device is contacted in this mode.

When hardware is available, configure locally in `.env`:

```text
IOT_BACKEND=home_assistant
HA_URL=http://homeassistant.local:8123
HA_TOKEN=your_local_token
HA_ALLOWED_ENTITIES=light.study,switch.desk_lamp
```

The adapter uses the [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/).
Only allowlisted entities are exposed. Control currently supports lights and
switches, with explicit on/off actions. Never commit tokens or local snapshots.
Real hardware connectivity has not been validated without a Home Assistant host.

## Voice, vision, background checks and personalization

- **Record 6 seconds** asks before recording and uploading to the configured
  transcription API. Review the resulting text in the input box, then Send.
- **Speak last reply** uses AI-generated speech through the configured API.
  The default voice is `nova`; a British accent is not guaranteed.
- **Preview screen** captures the primary screen locally. Only clicking
  **Analyze this screenshot** uploads that image to your configured vision model.
  Cancel sends nothing. Images and audio are held in memory, not saved as files.
- **Monitor devices** enables read-only device checks every five minutes while
  Oracle is open. Only changes/errors are displayed. **Stop monitor** stops it;
  it does not resume automatically after restart or execute model-generated tasks.
- `learn: I prefer short answers` saves a local preference for future LLM replies.
  `show preferences` reviews it; `forget preferences` removes it. This is explicit
  personalization, **not training model weights or rewriting Oracle's code**.

Install current dependencies with `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
Speech/vision require API credit and provider support for their endpoints/models.
`WHISPER_MODEL`, `SPEECH_VOICE`, `VISION_MODEL` and optional `MIC_DEVICE` are configurable.
Preferences and chat history stay in ignored `.data/`; saved preferences are sent
as context with LLM requests. Speech sends reply text to the configured provider.

Actual fine-tuning, open-ended autonomous agents, MQTT and cloud deployment remain
backlog work. Hardware capture and paid API calls need validation on your machine.

## Features

- Local web dashboard, legacy desktop UI and terminal mode
- Gmail reading and sending, plus Google Calendar tools
- API-backed conversation, voice and screen analysis
- Simulated or configured IoT devices
- Local conversation memory and explicit preferences

Automatic job-email classification, labels, snapshots, the 21-day rejection rule,
and the job chart have been removed. Existing Gmail labels are left unchanged.

## Requirements

- Python 3.11+ (3.12 recommended)
- OpenAI API key (or an OpenAI-compatible provider)
- Optional: a Google Cloud OAuth client with Gmail and Calendar APIs enabled

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
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

## Privacy

This repo is meant to be public. Keep secrets and mailbox data off GitHub:

| Kept local (gitignored) | Safe to commit |
| --- | --- |
| `.env` | `.env.example` (placeholders only) |
| `.data/` (tokens, chat memory, preferences) | Source under `app/` |
| `.venv/` | `requirements.txt` |
| `credentials.json`, `token.json`, `*.pem` | This README |

Do not put API keys, OAuth client secrets, or Gmail exports in issues, commits, or the README.

## Project layout

```text
oracle.py              # starts local server and opens browser
app/web_launcher.py    # loopback server lifecycle
app/web_dashboard.py   # connections, devices and finance API
app/assistant.py       # chat loop and assistant actions
app/hud.py             # desktop interaction
app/ui_layout.py       # desktop layout
app/google_auth.py     # OAuth
app/google_services.py # Gmail / Calendar API
app/llm.py             # model + tools
static/ + app/main.py  # default web dashboard
```

## Run the web server directly

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The default entry point `python oracle.py` also opens the browser automatically.

## License

Use and modify for your own setup. Add a `LICENSE` file if you want a specific open-source grant.
