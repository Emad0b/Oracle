# Oracle roadmap

## Implemented foundation
- API-backed LLM conversation and tool calling
- Desktop chat with capability, status and device shortcuts
- Local conversation history
- Gmail, Calendar, app-launch and job-triage skills
- Simulated IoT devices for development without hardware
- Opt-in Home Assistant REST adapter for allowlisted lights/switches

## Next: reliability
- Server-enforced confirmation tokens for existing email/calendar mutations
- Provider error messages, streaming and cancellation
- Regression suite for job classification and snapshot consistency
- Genuine data-analysis tools with bounded file access

## Hardware integration (requires devices)
- Validate Home Assistant adapter against a real installation
- MQTT adapter and broker configuration
- Sensor event subscriptions and automation rules

## Interaction and intelligence
- [x] User-triggered six-second recording, transcript review, API speech playback
- British female speech selection and local speech engines
- Local wake word; no continuous paid transcription for wake detection
- [x] Screenshot preview and explicit upload for vision analysis
- Retrieval over user-selected documents
- [x] Opt-in background device-state monitoring while Oracle runs
- Scheduled reminders, proactive briefings and durable task scheduling
- [x] Explicit local preference learning and removal
- Actual model fine-tuning with curated examples, consent and evaluation gates
- Tray app and animated desktop interface

## Deployment and advanced work
- Containerized backend, authentication and encrypted credential storage
- Mobile client, multi-user separation and cloud deployment
- Local model inference, evaluated intent learning
- Robotics only after hardware and action boundaries are specified

Old voice-cloning samples are not part of the runtime or public repository.
