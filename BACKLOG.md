# O.R.A.C.L.E. Backlog

Things not fully implemented yet. Build in order unless a dependency forces otherwise.

## Phase 2 — Stronger assistant core

- [ ] Local wake-word model (Porcupine / open-wake-word) so wake detection works offline
- [ ] Local Whisper model (`faster-whisper`) so STT can run without cloud
- [x] Conversation memory saved to disk between sessions
- [ ] Personality profiles (formal / casual / mission mode)
- [ ] Better confirmation UX for email/calendar actions in pure voice

## Phase 3 — Productivity skills

- [x] Read and summarize unread email digests on morning briefings
- [x] Natural-language “move my meeting” and “cancel event”
- [ ] Contacts lookup before sending mail
- [ ] Multi-calendar support
- [ ] Reminders / timers / alarms

## Phase 4 — System control (Windows)

- [x] Open apps and websites by voice (allow-listed starters)
- [ ] Volume / mute / media controls
- [ ] File search in selected folders
- [ ] Clipboard and note-taking skills
- [ ] Screenshot + describe screen (vision model)

## Phase 5 — Perception / ML upgrades

- [ ] Face recognition unlock (“camera greet”)
- [ ] Emotion / tone adaptation from voice
- [ ] Intent classifier trained on your command history
- [ ] On-device small LLM option for offline chat
- [ ] Custom voice cloning from user sample (deferred: unstable on Python 3.14)

## Phase 6 — Presence / JARVIS cinematic layer

- [ ] Always-on tray app instead of terminal window
- [ ] Animated avatar / waveform HUD (desktop overlay, not a website)
- [ ] Spatial sound cues for wake / thinking / done
- [ ] Proactive briefings (“You have 2 meetings in the next hour”)

## Phase 7 — Home / IoT

- [ ] Smart lights / plugs via Home Assistant or MQTT
- [ ] Room presence sensors
- [ ] Camera event alerts

## Explicitly deferred / hard

- [ ] True always-listening OS-level Siri replacement with guaranteed privacy offline
- [ ] Full movie-JARVIS holographic projection UI
- [ ] Autonomous email sending without confirmation
- [ ] Phone-call placing / SMS gateway
- [ ] Robot / hardware body control
- [ ] Custom MP3 voice cloning via XTTS on current Python 3.14 stack

## Done

- [x] Python-first assistant entry (`oracle.py`)
- [x] British female TTS (`en-GB-SoniaNeural`)
- [x] Wake phrase + Whisper STT
- [x] LLM tool-calling brain
- [x] Gmail + Calendar integration
- [x] Text fallback mode
- [x] Persistent conversation memory
- [x] Unread email digest skill
- [x] Cancel / move calendar events
- [x] Open allow-listed apps, URLs, and web search
