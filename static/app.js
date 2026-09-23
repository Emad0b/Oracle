const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messages = document.querySelector("#messages");
const sendButton = document.querySelector("#send-button");
const googleStatusEl = document.querySelector("#google-status");
const connectGoogleLink = document.querySelector("#connect-google");
const disconnectGoogleButton = document.querySelector("#disconnect-google");
const voiceStatusEl = document.querySelector("#voice-status");
const wakeHintEl = document.querySelector("#wake-hint");
const voiceToggle = document.querySelector("#voice-toggle");
const micPush = document.querySelector("#mic-push");
const voiceCard = document.querySelector(".voice-card");
const voiceTranscriptEl = document.querySelector("#voice-transcript");

const history = [];
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let wakePhrase = "hey oracle";
let listeningEnabled = false;
let mode = "idle"; // idle | listening | command | thinking | speaking
let recognition = null;
let commandBuffer = "";
let commandTimer = null;
let busy = false;

const WAKE_VARIANTS = [
  "hey oracle",
  "hey oricle",
  "hey oracal",
  "hey orakel",
  "a oracle",
  "hey o r a c l e",
  "okay oracle",
  "ok oracle",
];

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function addMessage(role, content, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role}${options.error ? " error" : ""}`;

  const label = document.createElement("span");
  label.className = "label";
  label.textContent = role === "user" ? "You" : "O.R.A.C.L.E.";

  const paragraph = document.createElement("p");
  paragraph.textContent = content;

  article.append(label, paragraph);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function setVoiceMode(nextMode, label) {
  mode = nextMode;
  voiceStatusEl.textContent = label;
  voiceCard.classList.toggle("listening", nextMode === "listening");
  voiceCard.classList.toggle("command", nextMode === "command");
  voiceCard.classList.toggle("speaking", nextMode === "speaking");
}

function setTranscript(text, options = {}) {
  const value = String(text || "").trim();
  voiceTranscriptEl.textContent = value || options.placeholder || "…";
  voiceTranscriptEl.classList.toggle("interim", Boolean(options.interim));
}

function setLoading(isLoading) {
  busy = isLoading;
  sendButton.disabled = isLoading;
  input.disabled = isLoading;
  sendButton.textContent = isLoading ? "Thinking..." : "Send";
}

async function refreshGoogleStatus() {
  try {
    const response = await fetch("/api/google/status");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Could not load Google status.");
    }

    wakePhrase = normalizeText(payload.wake_phrase || "hey oracle");
    wakeHintEl.textContent = `Wake phrase: ${payload.wake_phrase || "Hey Oracle"}`;

    if (!payload.configured) {
      googleStatusEl.textContent = "OAuth not configured";
      connectGoogleLink.hidden = false;
      disconnectGoogleButton.hidden = true;
      return;
    }

    if (payload.connected) {
      const caps = [
        payload.can_read_mail ? "mail" : null,
        payload.can_send_mail ? "send" : null,
        payload.can_use_calendar ? "calendar" : null,
      ].filter(Boolean);
      const account = payload.email ? `Connected as ${payload.email}` : "Connected";
      googleStatusEl.textContent = caps.length
        ? `${account} (${caps.join(", ")})`
        : account;
      connectGoogleLink.hidden = true;
      disconnectGoogleButton.hidden = false;
    } else {
      googleStatusEl.textContent = "Not connected";
      connectGoogleLink.hidden = false;
      disconnectGoogleButton.hidden = true;
    }
  } catch (error) {
    googleStatusEl.textContent = error.message;
  }
}

async function sendMessage(message, voiceMode = false) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, voice_mode: voiceMode }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "O.R.A.C.L.E. could not complete the request.");
  }

  return payload;
}

function speak(text, options = {}) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !text) {
      resolve();
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = options.rate || 1.02;
    utterance.pitch = 1;
    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    if (!options.silentStatus) {
      setVoiceMode("speaking", "Speaking");
    }
    window.speechSynthesis.speak(utterance);
  });
}

function extractCommand(transcript) {
  const normalized = normalizeText(transcript);
  const phrases = [wakePhrase, ...WAKE_VARIANTS];

  for (const phrase of phrases) {
    const index = normalized.indexOf(phrase);
    if (index !== -1) {
      return normalizeText(normalized.slice(index + phrase.length));
    }
  }
  return null;
}

function containsWakePhrase(transcript) {
  const normalized = normalizeText(transcript);
  return [wakePhrase, ...WAKE_VARIANTS].some((phrase) => normalized.includes(phrase));
}

async function handleAssistantTurn(message, voiceMode = false) {
  if (!message || busy) {
    return;
  }

  addMessage("user", message);
  setLoading(true);
  if (voiceMode) {
    setVoiceMode("thinking", "Thinking");
  }

  try {
    const payload = await sendMessage(message, voiceMode);
    addMessage("assistant", payload.reply);
    history.push(
      { role: "user", content: message },
      { role: "assistant", content: payload.reply },
    );
    if (history.length > 20) {
      history.splice(0, history.length - 20);
    }

    if (voiceMode) {
      await speak(payload.speak || payload.reply);
    }
  } catch (error) {
    addMessage("assistant", error.message, { error: true });
    if (voiceMode) {
      await speak(error.message);
    }
  } finally {
    setLoading(false);
    if (listeningEnabled) {
      setVoiceMode("listening", "Listening for wake phrase");
      setTranscript("Say Hey Oracle…", { interim: true });
      startRecognition();
    } else {
      setVoiceMode("idle", "Idle");
      setTranscript("Listening is off.");
    }
    input.focus();
  }
}

function finalizeCommand() {
  const command = normalizeText(commandBuffer);
  commandBuffer = "";
  if (!command) {
    if (listeningEnabled) {
      setVoiceMode("listening", "Listening for wake phrase");
      setTranscript("Say Hey Oracle…", { interim: true });
    }
    return;
  }
  setTranscript(command);
  stopRecognition();
  handleAssistantTurn(command, true);
}

function getTranscriptParts(event) {
  let finalText = "";
  let interimText = "";

  for (const result of event.results) {
    const chunk = result[0].transcript.trim();
    if (!chunk) {
      continue;
    }
    if (result.isFinal) {
      finalText = `${finalText} ${chunk}`.trim();
    } else {
      interimText = `${interimText} ${chunk}`.trim();
    }
  }

  const full = `${finalText} ${interimText}`.trim();
  return { finalText, interimText, full, isFinal: Boolean(finalText) && !interimText };
}

function handleSpeechResult(event) {
  const { full, interimText, isFinal } = getTranscriptParts(event);
  if (!full) {
    return;
  }

  setTranscript(full, {
    interim: Boolean(interimText),
    placeholder: "Listening…",
  });

  if (mode === "listening" || mode === "idle") {
    if (!containsWakePhrase(full)) {
      return;
    }

    setVoiceMode("command", "Listening for command");
    const command = extractCommand(full);
    commandBuffer = command || "";
    speak("Yes?", { silentStatus: true, rate: 1.15 });

    if (command && isFinal) {
      clearTimeout(commandTimer);
      commandTimer = setTimeout(finalizeCommand, 450);
    }
    return;
  }

  if (mode === "command") {
    const maybeCommand = extractCommand(full);
    commandBuffer = maybeCommand || normalizeText(full);
    if (isFinal || (!interimText && commandBuffer)) {
      clearTimeout(commandTimer);
      commandTimer = setTimeout(finalizeCommand, 450);
    }
  }
}

function createRecognition(continuous) {
  if (!SpeechRecognition) {
    return null;
  }

  const instance = new SpeechRecognition();
  instance.lang = "en-US";
  instance.continuous = continuous;
  instance.interimResults = true;
  instance.maxAlternatives = 1;

  instance.onresult = handleSpeechResult;
  instance.onerror = (event) => {
    if (event.error === "not-allowed") {
      setVoiceMode("idle", "Microphone blocked");
      listeningEnabled = false;
      voiceToggle.textContent = "Enable Listening";
      voiceToggle.classList.remove("active");
      return;
    }
    if (listeningEnabled && mode !== "thinking" && mode !== "speaking") {
      setTimeout(startRecognition, 400);
    }
  };
  instance.onend = () => {
    if (listeningEnabled && !busy && (mode === "listening" || mode === "command")) {
      startRecognition();
    }
  };

  return instance;
}

function stopRecognition() {
  if (!recognition) {
    return;
  }
  try {
    recognition.onend = null;
    recognition.stop();
  } catch (_error) {
    // Recognition may already be stopped.
  }
}

function startRecognition() {
  if (!SpeechRecognition) {
    setVoiceMode("idle", "Speech recognition unsupported in this browser");
    return;
  }
  if (busy || mode === "speaking" || mode === "thinking") {
    return;
  }

  stopRecognition();
  recognition = createRecognition(true);
  try {
    recognition.start();
    if (mode !== "command") {
      setVoiceMode("listening", "Listening for wake phrase");
    }
  } catch (_error) {
    setTimeout(() => {
      if (listeningEnabled) {
        startRecognition();
      }
    }, 500);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) {
    return;
  }
  input.value = "";
  await handleAssistantTurn(message, false);
});

voiceToggle.addEventListener("click", async () => {
  if (!SpeechRecognition) {
    addMessage(
      "assistant",
      "Voice recognition needs Chrome, Edge, or another Chromium browser on localhost/HTTPS.",
      { error: true },
    );
    return;
  }

  listeningEnabled = !listeningEnabled;
  voiceToggle.textContent = listeningEnabled ? "Disable Listening" : "Enable Listening";
  voiceToggle.classList.toggle("active", listeningEnabled);

  if (listeningEnabled) {
    setTranscript("Say Hey Oracle…", { interim: true });
    await speak("Listening. Say Hey Oracle.");
    setVoiceMode("listening", "Listening for wake phrase");
    startRecognition();
  } else {
    stopRecognition();
    window.speechSynthesis.cancel();
    setVoiceMode("idle", "Idle");
    setTranscript("Listening is off.");
  }
});

micPush.addEventListener("click", () => {
  if (!SpeechRecognition || busy) {
    return;
  }

  stopRecognition();
  setVoiceMode("command", "Push to talk");
  setTranscript("Speak now…", { interim: true });
  recognition = createRecognition(false);
  recognition.onresult = (event) => {
    const { full } = getTranscriptParts(event);
    setTranscript(full || "…", { interim: true });
    const command = extractCommand(full) || normalizeText(full);
    if (command && event.results[event.results.length - 1].isFinal) {
      setTranscript(command);
      handleAssistantTurn(command, true);
    }
  };
  recognition.onend = () => {
    if (listeningEnabled && !busy) {
      setVoiceMode("listening", "Listening for wake phrase");
      setTranscript("Say Hey Oracle…", { interim: true });
      startRecognition();
    }
  };
  recognition.start();
});

disconnectGoogleButton.addEventListener("click", async () => {
  await fetch("/api/google/disconnect", { method: "POST" });
  await refreshGoogleStatus();
  addMessage("assistant", "Google account disconnected.");
});

refreshGoogleStatus();
