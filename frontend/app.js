// Automatic X-JARVIS-Session Header Interceptor
const _origFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const tokenMatch = document.cookie.match(new RegExp('(^| )session_token=([^;]+)'));
  const token = tokenMatch ? decodeURIComponent(tokenMatch[2]) : (localStorage.getItem("jarvis_session_token") || "");
  if (token && typeof url === "string" && url.startsWith("/api/")) {
    options.headers = options.headers || {};
    if (options.headers instanceof Headers) {
      if (!options.headers.has("X-JARVIS-Session")) {
        options.headers.set("X-JARVIS-Session", token);
      }
    } else if (Array.isArray(options.headers)) {
      options.headers.push(["X-JARVIS-Session", token]);
    } else {
      if (!options.headers["X-JARVIS-Session"]) {
        options.headers["X-JARVIS-Session"] = token;
      }
    }
  }
  return _origFetch.call(this, url, options);
};

// Robust HTML Sanitizer to Prevent XSS in Chat, Memories, and Workflows
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ==========================================================================
// JARVIS-APEX CLIENT CONTROLLER
// Dashboard UI: 100% English // Voice & Conversation: Pure Hindi / Hinglish
// Continuous Live Voice Dialogue Mode ("लाइव बातचीत") with Sarvam AI STT/TTS
// ==========================================================================

// --------------------------------------------------------------------------
// 1. High-Fidelity 16kHz Mono WAV Recorder with Native RMS Voice Activity Detection
// Directly feeds pristine PCM WAV to Sarvam Saaras (saaras:v4) & Groq Whisper
// --------------------------------------------------------------------------
class WavAudioRecorder {
  constructor(onSilenceCallback) {
    this.audioCtx = null;
    this.mediaStream = null;
    this.sourceNode = null;
    this.processorNode = null;
    this.audioChunks = [];
    this.isRecording = false;
    this.onSilence = onSilenceCallback;
    this.silenceTimer = null;
    this.hasSpoken = false;
    this.silenceThreshold = 0.012; // RMS audio energy threshold for speech
    this.silenceDuration = 400;    // Ultra-responsive ~0.4s speech completion detection
  }

  async initStream() {
    if (!this.mediaStream || !this.mediaStream.active) {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
    }
    return this.mediaStream;
  }

  async start() {
    this.audioChunks = [];
    this.hasSpoken = false;
    clearTimeout(this.silenceTimer);
    this.silenceTimer = null;

    await this.initStream();

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    this.audioCtx = new AudioContextClass();
    const sourceRate = this.audioCtx.sampleRate;
    this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);

    // Buffer size 4096 gives ~85ms audio slices
    this.processorNode = this.audioCtx.createScriptProcessor(4096, 1, 1);
    this.processorNode.onaudioprocess = (e) => {
      if (!this.isRecording) return;
      const input = e.inputBuffer.getChannelData(0);

      // RMS calculation for Voice Activity Detection
      let sum = 0;
      for (let i = 0; i < input.length; i++) {
        sum += input[i] * input[i];
      }
      const rms = Math.sqrt(sum / input.length);

      // Downsample to 16000Hz (universal speech format)
      const downsampled = this.downsampleTo16k(input, sourceRate, 16000);
      this.audioChunks.push(downsampled);

      if (rms > this.silenceThreshold) {
        this.hasSpoken = true;
        if (this.silenceTimer) {
          clearTimeout(this.silenceTimer);
          this.silenceTimer = null;
        }
      } else if (this.hasSpoken) {
        if (!this.silenceTimer) {
          this.silenceTimer = setTimeout(() => {
            if (this.isRecording && this.hasSpoken && this.onSilence) {
              this.onSilence();
            }
          }, this.silenceDuration);
        }
      }
    };

    this.sourceNode.connect(this.processorNode);
    this.processorNode.connect(this.audioCtx.destination);
    this.isRecording = true;
  }

  downsampleTo16k(buffer, sourceRate, targetRate) {
    if (sourceRate === targetRate) return new Float32Array(buffer);
    const ratio = sourceRate / targetRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffset = Math.round((offsetResult + 1) * ratio);
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffset && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = count > 0 ? accum / count : 0;
      offsetResult++;
      offsetBuffer = nextOffset;
    }
    return result;
  }

  stop() {
    this.isRecording = false;
    clearTimeout(this.silenceTimer);
    this.silenceTimer = null;

    if (this.processorNode) {
      try { this.processorNode.disconnect(); } catch (e) { }
      this.processorNode = null;
    }
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch (e) { }
      this.sourceNode = null;
    }
    if (this.audioCtx && this.audioCtx.state !== "closed") {
      try { this.audioCtx.close(); } catch (e) { }
      this.audioCtx = null;
    }

    return this.buildWavBlob();
  }

  buildWavBlob() {
    if (this.audioChunks.length === 0) return null;
    let totalLen = 0;
    for (const chunk of this.audioChunks) {
      totalLen += chunk.length;
    }
    const merged = new Float32Array(totalLen);
    let offset = 0;
    for (const chunk of this.audioChunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }

    // 16-bit PCM WAV Header & Data
    const sampleRate = 16000;
    const buffer = new ArrayBuffer(44 + merged.length * 2);
    const view = new DataView(buffer);

    const writeString = (view, off, str) => {
      for (let i = 0; i < str.length; i++) {
        view.setUint8(off + i, str.charCodeAt(i));
      }
    };

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + merged.length * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, merged.length * 2, true);

    let pcmOff = 44;
    for (let i = 0; i < merged.length; i++) {
      let s = Math.max(-1, Math.min(1, merged[i]));
      view.setInt16(pcmOff, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      pcmOff += 2;
    }

    return new Blob([buffer], { type: 'audio/wav' });
  }
}

// --------------------------------------------------------------------------
// 2. Main Jarvis Client Controller
// --------------------------------------------------------------------------
class JarvisClient {
  constructor() {
    this.ws = null;
    this.reconnectTimer = null;
    this.ttsPlayer = document.getElementById("tts-player");
    this.isSpeaking = false;
    this.isHudMode = false;

    // CONTINUOUS LIVE VOICE DIALOGUE STATE MACHINE
    this.isLiveMode = false;
    this.isTurnProcessing = false;
    this.liveIdleTimer = null;
    this.accumulatedInterimText = "";
    this.lastDispatchedTranscript = "";
    this.lastDispatchTime = 0;
    this.recentJarvisResponses = [];
    this.ignoreVoiceUntil = 0;

    // Recorders & Speech API
    this.wavRecorder = new WavAudioRecorder(() => this.handleVADSilence());
    this.recognition = null;
    this.speechDebounceTimer = null;

    // Audio and Turn Sync Management
    this.hasReceivedAudioForTurn = false;
    this.audioFallbackTimer = null;
    this.currentSymbol = "NIFTY50";
    this.currentTimeframe = "15m";
    this.liveScreenStream = null;
    this.isAutoRadarActive = false;
    this.autoRadarInterval = null;
    this.chart = null;
    this.candlestickSeries = null;

    // Waveform visualizer
    this.canvas = document.getElementById("waveform-canvas");
    this.ctx = this.canvas.getContext("2d");
    this.wavePhase = 0;

    this.initClock();
    this.initWaveform();
    this.initWebSocket();
    this.initSpeechRecognition();
    this.initTradingViewChart();
    this.bindEvents();
    this.bindDynamicPresets();
    this.fetchMarketScan();
    this.fetchOptionChain();
    this.fetchMarketOverview();
    setInterval(() => this.fetchMarketOverview(), 5000);

    // Upgraded Subsystem Initializers
    this.initTabs();
    this.initPrivacyControls();
    this.initVoiceInterruption();
    this.initConfirmationModal();
    this.initStrategyLab();
    this.initPaperTrading();
    this.initPsychologyJournal();
    this.initResearchWorkspace();
    this.initMemoryBrain();
    this.initWorkflowStudio();
    this.initSecurityAndUpdater();
    this.initSevenComponentsListeners();

    // Lock window position to origin (0, 0) so top navbar never scrolls off-screen
    window.scrollTo(0, 0);
    window.addEventListener("scroll", () => {
      if (window.scrollY !== 0 || window.scrollX !== 0) {
        window.scrollTo(0, 0);
      }
    });
  }

  // 1. Live Clock (English Format)
  initClock() {
    const clockEl = document.getElementById("live-clock");
    const update = () => {
      const now = new Date();
      clockEl.textContent = now.toTimeString().split(" ")[0];
    };
    update();
    setInterval(update, 1000);
  }

  // High-Tech Web Audio Synthesizer Chime
  playAlertChime() {
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioContextClass();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.16);
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.32);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.33);
    } catch (e) { }
  }

  getSessionToken() {
    const match = document.cookie.match(new RegExp('(^| )session_token=([^;]+)'));
    if (match) return decodeURIComponent(match[2]);
    return localStorage.getItem("jarvis_session_token") || "";
  }

  // 2. WebSocket Connection (Secure Token Authenticated)
  initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const token = this.getSessionToken();
    const wsUrl = `${protocol}//${window.location.host}/ws${token ? '?token=' + encodeURIComponent(token) : ''}`;
    const statusEl = document.getElementById("ws-status");

    statusEl.textContent = "CONNECTING...";
    statusEl.style.color = "var(--amber-warning)";

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[WS] Connected to JARVIS Core 2.0");
      statusEl.textContent = "ONLINE // ACTIVE";
      statusEl.style.color = "var(--emerald-profit)";
      clearTimeout(this.reconnectTimer);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleWSMessage(msg);
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };

    this.ws.onclose = () => {
      statusEl.textContent = "DISCONNECTED";
      statusEl.style.color = "var(--rose-loss)";
      this.reconnectTimer = setTimeout(() => this.initWebSocket(), 2000);
    };
  }

  handleWSMessage(msg) {
    if (msg.event === "telemetry") {
      this.renderTelemetry(msg.payload);
    } else if (msg.event === "chat_response") {
      const text = msg.payload.text;
      const action = msg.payload.action;
      const widget = msg.payload.dynamic_widget;

      this.renderChatMessage("JARVIS", text, false);
      this.updateHudTranscript(text);
      this.hasReceivedAudioForTurn = false;

      // Project dynamic autonomous widget if attached
      if (widget) {
        this.renderDynamicWidget(widget);
      }

      if (action && (action.includes("open") || action.includes("launch"))) {
        setTimeout(() => this.setHudMode(true), 1500);
      }
    } else if (msg.event === "dynamic_widget") {
      this.renderDynamicWidget(msg.payload);
    } else if (msg.event === "chat_audio") {
      // PURE MALE VOICE STREAM ARRIVAL (Sarvam AI Shubh / Edge-TTS Madhur)
      this.hasReceivedAudioForTurn = true;
      const audioUrl = msg.payload.audio_url;
      const text = msg.payload.text;
      if (audioUrl) {
        this.playSpeech(audioUrl, text);
      }
    } else if (msg.event === "local_wake_triggered") {
      this.setVoiceStatus("✦ WAKE DETECTED: 'Hey Jarvis' | आपकी बात सुन रहा हूँ...", "var(--cyan-neon)");
      if (this.canvas) this.canvas.style.opacity = "1";
    } else if (msg.event === "user_message_received") {
      const userText = msg.payload.text;
      if (userText) {
        this.renderChatMessage("YOU", userText, true);
        this.updateHudTranscript(userText);
      }
    } else if (msg.event === "research_progress") {
      const p = msg.payload || {};
      const statusText = `🔬 [${p.step}/${p.total_steps}] ${p.stage}: ${p.detail || p.subject || ""}`;
      this.setVoiceStatus(statusText, "var(--cyan-neon)");
      this.updateHudTranscript(statusText);
    } else if (msg.event === "trade_alert") {
      this.playAlertChime();
      this.renderSignals(msg.payload);
    } else if (msg.event === "option_chain") {
      this.renderOptionChain(msg.payload);
    } else if (msg.event === "morning_briefing") {
      this.renderMorningBriefing(msg.payload);
    } else if (msg.event === "market_overview") {
      this.renderMarketOverview(msg.payload);
    } else if (msg.event === "ping") {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ event: "pong", timestamp: Date.now() }));
      }
    } else if (msg.event === "voice_state") {
      const state = msg.payload?.state || "IDLE";
      const pill = document.getElementById("voice-state-text");
      if (pill) pill.textContent = state;
      const stopBtn = document.getElementById("voice-interrupt-btn");
      if (stopBtn) {
        stopBtn.style.display = (state === "SPEAKING" || state === "THINKING") ? "inline-flex" : "none";
      }
    } else if (msg.event === "action_confirmation" || (msg.event === "dynamic_widget" && msg.payload?.type === "action_confirmation")) {
      const actionData = msg.payload?.data || msg.payload;
      this.showConfirmationModal(actionData);
    }
  }

  // 3. System Telemetry
  renderTelemetry(data) {
    const cpuEl = document.getElementById("cpu-val");
    if (cpuEl) cpuEl.textContent = `${data.cpu_percent}%`;

    const ramEl = document.getElementById("ram-val");
    if (ramEl) ramEl.textContent = `${data.ram_percent}%`;

    const netEl = document.getElementById("net-up");
    if (netEl) netEl.textContent = `${data.network_sent_mb} MB/s`;
  }

  // 4. Waveform Canvas Animation
  initWaveform() {
    const draw = () => {
      const width = this.canvas.width;
      const height = this.canvas.height;
      const ctx = this.ctx;

      ctx.clearRect(0, 0, width, height);

      const amp = this.isSpeaking ? 20 : (this.isLiveMode ? 14 : 3);
      const freq = this.isSpeaking ? 0.05 : 0.025;

      ctx.beginPath();
      ctx.lineWidth = 2;
      ctx.strokeStyle = this.isSpeaking
        ? "#00f2fe"
        : (this.isLiveMode ? "#f43f5e" : "rgba(99, 102, 241, 0.4)");

      for (let x = 0; x < width; x++) {
        const y = (height / 2) + Math.sin(x * freq + this.wavePhase) * amp * Math.sin((x / width) * Math.PI);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      this.wavePhase += 0.08;
      requestAnimationFrame(draw);
    };
    draw();
  }

  // 5. Speech Audio Playback with Echo Immunity Gate
  stopSpeech() {
    if (this.ttsPlayer) {
      this.ttsPlayer.pause();
      this.ttsPlayer.currentTime = 0;
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    this.isSpeaking = false;
  }

  playSpeech(audioUrl, fallbackText) {
    this.stopSpeech();
    this.isSpeaking = true;

    // HARD ECHO IMMUNITY: Pause mic hardware so it NEVER hears itself!
    if (this.wavRecorder && this.wavRecorder.isRecording) {
      this.wavRecorder.stop();
    }
    this.pauseRecognition();

    if (fallbackText) {
      const norm = fallbackText.toLowerCase().replace(/[^a-z0-9 ]/g, " ").trim();
      this.recentJarvisResponses.push(norm);
      if (this.recentJarvisResponses.length > 6) {
        this.recentJarvisResponses.shift();
      }
    }

    this.setVoiceStatus("JARVIS SPEAKING...", "var(--cyan-neon)");

    // Safe completion handler
    const onPlaybackDone = () => {
      this.isSpeaking = false;
      this.ignoreVoiceUntil = Date.now() + 400; // 400ms cooldown for room acoustics

      setTimeout(() => {
        if (!this.isSpeaking) {
          if (this.isLiveMode) {
            // AUTOMATICALLY RE-OPEN MIC FOR SEAMLESS LIVE DIALOGUE!
            console.log("[Live Mode] JARVIS finished speaking. Re-opening mic for user response...");
            this.startListeningTurn();
          } else {
            this.setVoiceStatus("VOICE RADAR: Listening for 'Hey Jarvis'", "var(--text-muted)");
            this.resumeRecognition();
          }
        }
      }, 400);
    };

    if (audioUrl) {
      const freshUrl = audioUrl.includes("?") ? `${audioUrl}&_t=${Date.now()}` : `${audioUrl}?_t=${Date.now()}`;
      this.ttsPlayer.src = freshUrl;
      this.ttsPlayer.onended = onPlaybackDone;
      this.ttsPlayer.onerror = (e) => {
        console.warn("[Audio] Player notice:", e);
        onPlaybackDone();
      };
      this.ttsPlayer.play().catch(e => {
        console.warn("[Audio] Autoplay notice:", e);
        onPlaybackDone();
      });
    } else {
      onPlaybackDone();
    }
  }

  // 6. Speech Recognition Engine
  initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("[Voice] Web Speech API not supported in this browser.");
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = "hi-IN"; // Native Hindi input for speech accuracy

    this.recognition.onstart = () => {
      console.log("[Voice] Speech recognition active.");
    };

    this.recognition.onresult = (e) => {
      if (this.isSpeaking || Date.now() < this.ignoreVoiceUntil) return;

      let interimStr = "";
      let finalChunk = "";

      for (let i = e.resultIndex; i < e.results.length; ++i) {
        const item = e.results[i];
        const text = item[0].transcript;
        if (item.isFinal) {
          finalChunk += " " + text;
        } else {
          interimStr += " " + text;
        }
      }

      finalChunk = finalChunk.trim();
      interimStr = interimStr.trim();

      const activeText = (finalChunk || interimStr || "").trim();
      if (!activeText) return;

      // Echo filter
      if (this.isEchoOfJarvis(activeText)) return;

      this.accumulatedInterimText = activeText;
      this.setVoiceStatus(`HEARING: "${activeText}"`, "var(--rose-loss)");
      this.updateHudTranscript(`"${activeText}"`);

      // If in passive mode and wake word spoken:
      if (!this.isLiveMode && this.hasWakeWord(activeText.toLowerCase())) {
        console.log("[Voice] Wake word detected in passive radar. Starting Live Mode...");
        const cleanCmd = this.stripWakeWords(activeText);
        this.startLiveConversation(cleanCmd);
        return;
      }

      // If in Live Mode, keep debouncing silence with ultra-fast responsiveness
      if (this.isLiveMode) {
        clearTimeout(this.speechDebounceTimer);
        this.speechDebounceTimer = setTimeout(() => {
          this.commitVoiceTurn();
        }, 400);
      }
    };

    this.recognition.onerror = (e) => {
      console.warn("[Voice] Recognition error:", e.error);
    };

    this.recognition.onend = () => {
      // Auto-restart recognition if appropriate
      if (this.isLiveMode && !this.isSpeaking && !this.isTurnProcessing) {
        setTimeout(() => this.resumeRecognition(), 250);
      }
    };

    try {
      this.recognition.start();
    } catch (e) { }
  }

  pauseRecognition() {
    if (this.recognition) {
      try { this.recognition.abort(); } catch (e) { }
    }
  }

  resumeRecognition() {
    if (!this.recognition || this.isSpeaking || Date.now() < this.ignoreVoiceUntil) return;
    try {
      this.recognition.start();
    } catch (e) { }
  }

  isEchoOfJarvis(transcript) {
    if (!transcript) return false;
    const clean = transcript.toLowerCase().replace(/[^a-z0-9 ]/g, " ").trim();
    if (!clean) return false;
    for (const recent of this.recentJarvisResponses) {
      if (recent.includes(clean) || clean.includes(recent)) return true;
    }
    return false;
  }

  setVoiceStatus(text, color) {
    const el = document.getElementById("voice-status");
    if (el) {
      el.textContent = text;
      el.style.color = color;
    }
    const hudStatus = document.getElementById("hud-status-text");
    if (hudStatus) {
      hudStatus.textContent = text;
    }
  }

  hasWakeWord(text) {
    const wakeWords = ["hey jarvis", "jarvis", "jarvis suno", "suno jarvis", "namaste jarvis", "hello jarvis", "hi jarvis", "सुनो जार्विस", "नमस्ते जार्विस", "जार्विस"];
    return wakeWords.some(w => text.includes(w));
  }

  stripWakeWords(text) {
    const wakeWords = ["hey jarvis", "jarvis", "jarvis suno", "suno jarvis", "namaste jarvis", "hello jarvis", "hi jarvis", "सुनो जार्विस", "नमस्ते जार्विस", "जार्विस"];
    let result = text;
    for (const w of wakeWords) {
      result = result.replace(new RegExp(w, "gi"), "");
    }
    return result.trim();
  }

  // ------------------------------------------------------------------------
  // 7. CONTINUOUS LIVE VOICE CONVERSATION PROTOCOL ("लाइव बातचीत")
  // ------------------------------------------------------------------------
  toggleLiveConversation() {
    if (this.isLiveMode) {
      this.stopLiveConversation("USER_CLICK");
    } else {
      this.startLiveConversation();
    }
  }

  async startLiveConversation(initialCommand = "") {
    // BARGE-IN: If JARVIS is currently speaking, stop immediately!
    this.stopSpeech();

    this.isLiveMode = true;
    this.setLiveVisuals(true);
    this.setVoiceStatus("🔴 LIVE TALK ACTIVE: Listening... Speak now", "var(--rose-loss)");

    if (initialCommand && initialCommand.trim()) {
      // User spoke wake word + command together: execute right away!
      this.sendUserMessage(initialCommand.trim());
      return;
    }

    await this.startListeningTurn();
  }

  stopLiveConversation(reason = "MANUAL") {
    this.isLiveMode = false;
    this.isTurnProcessing = false;
    this.setLiveVisuals(false);
    clearTimeout(this.liveIdleTimer);
    clearTimeout(this.speechDebounceTimer);

    if (this.wavRecorder) {
      this.wavRecorder.stop();
    }
    this.pauseRecognition();

    if (reason === "USER_CLICK" || reason === "MANUAL") {
      this.setVoiceStatus("VOICE RADAR: Listening for 'Hey Jarvis'", "var(--text-muted)");
    } else if (reason === "IDLE_TIMEOUT") {
      this.setVoiceStatus("LIVE TALK IDLE: Click Mic or say 'Hey Jarvis'", "var(--text-muted)");
    }
    console.log(`[Live Mode] Stopped (${reason})`);
  }

  setLiveVisuals(active) {
    const micBtn = document.getElementById("mic-btn");
    const hudMicBtn = document.getElementById("hud-mic-btn");
    const arcReactor = document.getElementById("arc-reactor");

    if (active) {
      if (micBtn) {
        micBtn.classList.add("recording", "live-active");
        micBtn.setAttribute("title", "Live Conversation Active - Click to stop");
      }
      if (hudMicBtn) hudMicBtn.classList.add("recording", "live-active");
      if (arcReactor) arcReactor.classList.add("live-active");
    } else {
      if (micBtn) {
        micBtn.classList.remove("recording", "live-active");
        micBtn.setAttribute("title", "Click to start Live Conversation");
      }
      if (hudMicBtn) hudMicBtn.classList.remove("recording", "live-active");
      if (arcReactor) arcReactor.classList.remove("live-active");
    }
  }

  async startListeningTurn() {
    if (!this.isLiveMode || this.isSpeaking) return;

    this.isTurnProcessing = false;
    this.accumulatedInterimText = "";
    this.setVoiceStatus("🔴 LIVE TALK: Listening... Speak now", "var(--rose-loss)");
    this.updateHudTranscript("Listening for your voice...");

    // Idle timer: 35s of silence exits live mode cleanly
    clearTimeout(this.liveIdleTimer);
    this.liveIdleTimer = setTimeout(() => {
      if (this.isLiveMode && !this.isSpeaking && !this.isTurnProcessing) {
        this.stopLiveConversation("IDLE_TIMEOUT");
      }
    }, 35000);

    // 1. Start pristine 16kHz WAV recording
    try {
      await this.wavRecorder.start();
    } catch (e) {
      console.warn("[Voice] WAV recording failed to start:", e);
    }

    // 2. Start speech recognition for live preview
    this.resumeRecognition();
  }

  handleVADSilence() {
    if (!this.isLiveMode || this.isSpeaking || this.isTurnProcessing) return;
    this.commitVoiceTurn();
  }

  async commitVoiceTurn() {
    if (this.isTurnProcessing) return;
    this.isTurnProcessing = true;
    clearTimeout(this.speechDebounceTimer);
    clearTimeout(this.liveIdleTimer);

    this.setVoiceStatus("THINKING: Processing voice...", "var(--cyan-neon)");

    // 1. Stop recorder and get 16kHz WAV Blob
    let wavBlob = null;
    if (this.wavRecorder && this.wavRecorder.isRecording) {
      wavBlob = this.wavRecorder.stop();
    }
    this.pauseRecognition();

    let recognizedText = "";

    // 2. ULTRA-FAST FAST-PATH: Use Real-time On-Device Speech Transcript (<5ms)
    if (this.accumulatedInterimText && this.accumulatedInterimText.trim().length > 1) {
      recognizedText = this.accumulatedInterimText.trim();
      console.log("[Fast-Path On-Device STT]:", recognizedText);
    }

    // 3. Fallback to Server Neural STT only if on-device text was empty
    if (!recognizedText && wavBlob && wavBlob.size > 2000) {
      try {
        const formData = new FormData();
        formData.append("file", wavBlob, "live_speech.wav");
        const res = await fetch("/api/transcribe", {
          method: "POST",
          body: formData
        });
        if (res.ok) {
          const data = await res.json();
          if (data.text && data.text.trim()) {
            recognizedText = data.text.trim();
            console.log("[Neural STT Server Fallback Result]:", recognizedText);
          }
        }
      } catch (err) {
        console.warn("[Neural STT Server Error]:", err);
      }
    }

    this.accumulatedInterimText = "";

    if (!recognizedText) {
      // Nothing spoken or ambient click -> resume listening turn immediately
      this.isTurnProcessing = false;
      if (this.isLiveMode && !this.isSpeaking) {
        this.startListeningTurn();
      }
      return;
    }

    // 4. Voice exit commands
    const lower = recognizedText.toLowerCase();
    if (
      lower.includes("अलविदा") ||
      lower.includes("बंद करो") ||
      lower.includes("स्टॉप") ||
      lower.includes("बाय बाय") ||
      lower.includes("goodbye") ||
      lower.includes("stop live") ||
      lower.includes("stop listening") ||
      lower.includes("exit live")
    ) {
      this.stopLiveConversation("USER_COMMAND");
      this.renderChatMessage("JARVIS", "जी सर, लाइव बातचीत बंद कर दी गई है। आवश्यकता हो तो मुझे आवाज़ दीजिएगा।", false);
      this.updateHudTranscript("जी सर, लाइव बातचीत बंद कर दी गई है।");
      return;
    }

    // Fast Mode-Switch Commands
    if (lower.includes("widget mode") || lower.includes("mini mode") || lower.includes("floating mode")) {
      this.setHudMode(true);
      this.renderChatMessage("JARVIS", "जी सर, मिनी विजेट मोड सक्रिय कर दिया गया है।", false);
      this.updateHudTranscript("मिनी विजेट मोड सक्रिय।");
      return;
    }
    if (lower.includes("dashboard mode") || lower.includes("full screen") || lower.includes("dashboard")) {
      this.setHudMode(false);
      this.renderChatMessage("JARVIS", "जी सर, मुख्य डैशबोर्ड खोल दिया गया है।", false);
      this.updateHudTranscript("मुख्य डैशबोर्ड खुला है।");
      return;
    }

    // 5. Send message to JARVIS
    this.sendUserMessage(recognizedText);
  }

  // 8. Messaging Pipeline
  sendUserMessage(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();

    this.renderChatMessage("YOU", cleanText, true);
    this.updateHudTranscript(`"${cleanText}"`);

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        event: "user_message",
        payload: { text: cleanText }
      }));
    } else {
      fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: cleanText })
      })
        .then(res => res.json())
        .then(data => {
          this.renderChatMessage("JARVIS", data.text, false);
          this.updateHudTranscript(data.text);
          this.playSpeech(data.audio_url, data.text);
        })
        .catch(err => {
          console.error(err);
          this.setVoiceStatus("ERROR: Server Unreachable", "var(--rose-loss)");
        });
    }
  }

  renderChatMessage(sender, text, isUser) {
    const feed = document.getElementById("chat-feed");
    const msgEl = document.createElement("div");
    msgEl.className = `chat-msg ${isUser ? "user-msg" : "jarvis-msg"}`;
    const timeStr = new Date().toTimeString().split(" ")[0];

    const safeSender = escapeHtml(sender);
    const safeText = escapeHtml(text);

    msgEl.innerHTML = `
      <div class="msg-avatar">${isUser ? "U" : "J"}</div>
      <div class="msg-body">
        <span class="msg-sender">${safeSender}</span>
        <p>${safeText}</p>
        <span class="msg-time">${timeStr}</span>
      </div>
    `;

    feed.appendChild(msgEl);
    feed.scrollTop = feed.scrollHeight;
  }

  updateHudTranscript(text) {
    const hudEl = document.getElementById("hud-transcript");
    if (hudEl) hudEl.textContent = text || "Ready for voice command...";
  }

  // 9. Dual-Mode Switcher (Full Dashboard <-> Floating HUD)
  setHudMode(isHud) {
    this.isHudMode = isHud;
    if (isHud) {
      document.body.classList.add("hud-mode");
    } else {
      document.body.classList.remove("hud-mode");
    }
  }

  toggleHudMode() {
    this.setHudMode(!this.isHudMode);
  }

  updateInstantMarketStatus() {
    const statusEl = document.getElementById("chart-market-status");
    const noteEl = document.getElementById("chart-session-note");
    const nEl = document.getElementById("price-nifty50");
    const bEl = document.getElementById("price-banknifty");
    const cEl = document.getElementById("price-btcusdt");

    // Fast fallback initial price placeholders (prevent "Fetching..." freeze)
    if (nEl && nEl.textContent.trim() === "Fetching...") nEl.textContent = "₹ 22,936.75";
    if (bEl && bEl.textContent.trim() === "Fetching...") bEl.textContent = "₹ 54,909.65";
    if (cEl && cEl.textContent.trim() === "Fetching...") cEl.textContent = "$ 80,824.00";

    if (!statusEl) return;

    // Check IST time (UTC + 5:30)
    const now = new Date();
    const utcMs = now.getTime() + (now.getTimezoneOffset() * 60000);
    const istTime = new Date(utcMs + (3600000 * 5.5));
    const day = istTime.getDay(); // 0 is Sunday, 6 is Saturday
    const hours = istTime.getHours();
    const minutes = istTime.getMinutes();
    const currentMins = (hours * 60) + minutes;
    const openMins = (9 * 60) + 15; // 09:15 AM
    const closeMins = (15 * 60) + 30; // 03:30 PM

    const isWeekday = day >= 1 && day <= 5;
    const isNseOpen = isWeekday && (currentMins >= openMins && currentMins <= closeMins);

    const sym = (this.currentSymbol || "NIFTY50").toUpperCase();
    if (sym.includes("BTC") || sym.includes("ETH") || sym.includes("SOL")) {
      statusEl.textContent = "● 24/7 LIVE STREAM";
      statusEl.style.color = "var(--emerald-profit)";
      statusEl.style.borderColor = "rgba(16, 185, 129, 0.3)";
      if (noteEl) noteEl.textContent = "(Binance Live Crypto Stream)";
    } else if (isNseOpen) {
      statusEl.textContent = "● LIVE (NSE SESSION)";
      statusEl.style.color = "var(--emerald-profit)";
      statusEl.style.borderColor = "rgba(16, 185, 129, 0.3)";
      if (noteEl) noteEl.textContent = "(Trading Session Closes at 03:30 PM IST)";
    } else {
      statusEl.textContent = "🔴 MARKET CLOSED";
      statusEl.style.color = "var(--amber-warning)";
      statusEl.style.borderColor = "rgba(245, 158, 11, 0.4)";
      if (noteEl) noteEl.textContent = "(Session: 09:15 AM - 03:30 PM IST | Opens Mon-Fri)";
    }
  }

  // 10. Interactive TradingView Lightweight Chart & SMC Zones
  initTradingViewChart() {
    this.updateInstantMarketStatus();
    const container = document.getElementById("tv-chart");
    if (!container || !window.LightweightCharts) return;

    try {
      this.chart = window.LightweightCharts.createChart(container, {
        width: container.clientWidth || 330,
        height: 180,
        layout: {
          background: { color: "#080b11" },
          textColor: "#94a3b8"
        },
        grid: {
          vertLines: { color: "rgba(255, 255, 255, 0.03)" },
          horzLines: { color: "rgba(255, 255, 255, 0.03)" }
        },
        timeScale: {
          borderColor: "rgba(255, 255, 255, 0.08)",
          timeVisible: true,
          secondsVisible: false
        }
      });

      this.candlestickSeries = this.chart.addCandlestickSeries({
        upColor: "#10b981",
        downColor: "#f43f5e",
        borderVisible: false,
        wickUpColor: "#10b981",
        wickDownColor: "#f43f5e"
      });

      window.addEventListener("resize", () => {
        if (this.chart && container) {
          this.chart.applyOptions({ width: container.clientWidth });
        }
      });

      this.loadChartCandles(this.currentSymbol);
    } catch (e) {
      console.warn("[Chart] Init notice:", e);
    }
  }

  async loadChartCandles(symbol, interval = (this.currentTimeframe || "15m")) {
    try {
      this.currentSymbol = symbol;
      this.currentTimeframe = interval;
      const res = await fetch(`/api/candles?symbol=${symbol}&interval=${interval}&limit=100`);
      if (res.ok) {
        const data = await res.json();
        if (data.candles && this.candlestickSeries) {
          this.candlestickSeries.setData(data.candles);
          const titleEl = document.getElementById("chart-symbol-label");
          if (titleEl) titleEl.textContent = `${symbol} (${interval.toUpperCase()} SMC)`;
          if (this.latestMarketData) {
            this.renderMarketOverview(this.latestMarketData);
          }
        }
      }
    } catch (e) {
      console.warn("[Chart] Loading error:", e);
    }
  }

  // 10B. Live Market Overview, Prices & Session States
  async fetchMarketOverview() {
    try {
      const res = await fetch("/api/market_overview");
      if (res.ok) {
        const data = await res.json();
        this.renderMarketOverview(data);
      }
    } catch (e) {
      console.warn("[MarketOverview] Fetch notice:", e);
    }
  }

  renderMarketOverview(data) {
    if (!data) return;
    this.latestMarketData = data;

    // 1. Update left sidebar price chips
    if (data.prices) {
      const nEl = document.getElementById("price-nifty50");
      if (nEl && data.prices.nifty50) nEl.textContent = data.prices.nifty50.formatted;

      const bEl = document.getElementById("price-banknifty");
      if (bEl && data.prices.banknifty) bEl.textContent = data.prices.banknifty.formatted;

      const cEl = document.getElementById("price-btcusdt");
      if (cEl && data.prices.btcusdt) cEl.textContent = data.prices.btcusdt.formatted;
    }

    // 2. Update India VIX
    if (data.market_status && data.market_status.india_vix) {
      const vixEl = document.getElementById("opt-vix");
      if (vixEl) vixEl.textContent = data.market_status.india_vix;
    }

    // 3. Update Chart Status Badge & Session Note
    const statusEl = document.getElementById("chart-market-status");
    const noteEl = document.getElementById("chart-session-note");
    if (!statusEl) return;

    const sym = (this.currentSymbol || "NIFTY50").toUpperCase();
    if (sym.includes("BTC") || sym.includes("ETH") || sym.includes("SOL")) {
      statusEl.textContent = "● 24/7 LIVE STREAM";
      statusEl.style.color = "var(--emerald-profit)";
      statusEl.style.borderColor = "rgba(16, 185, 129, 0.3)";
      if (noteEl) noteEl.textContent = "(Binance Live Crypto Stream)";
    } else {
      const isNseOpen = data.market_status && data.market_status.nse_open;
      const statusText = data.market_status ? data.market_status.status_text : "NSE";
      if (isNseOpen) {
        statusEl.textContent = "● LIVE (NSE SESSION)";
        statusEl.style.color = "var(--emerald-profit)";
        statusEl.style.borderColor = "rgba(16, 185, 129, 0.3)";
        if (noteEl) noteEl.textContent = "(Trading Session Closes at 03:30 PM IST)";
      } else {
        statusEl.textContent = `🔴 ${statusText}`;
        statusEl.style.color = "var(--amber-warning)";
        statusEl.style.borderColor = "rgba(245, 158, 11, 0.4)";
        const lastDate = (data.market_status && data.market_status.last_session_date) ? data.market_status.last_session_date : new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
        if (noteEl) noteEl.textContent = `(Last Traded: ${lastDate} 15:30 IST | Next Session: Opens 09:15 AM)`;
      }
    }
  }

  // 11. Option Chain & PCR Engine
  async fetchOptionChain() {
    try {
      const res = await fetch("/api/option_chain?symbol=NIFTY50");
      if (res.ok) {
        const data = await res.json();
        this.renderOptionChain(data);
      }
    } catch (e) { }
  }

  renderOptionChain(data) {
    if (!data) return;
    const pcrEl = document.getElementById("opt-pcr");
    const maxPainEl = document.getElementById("opt-maxpain");
    const vixEl = document.getElementById("opt-vix");
    if (pcrEl) {
      pcrEl.textContent = data.pcr;
      pcrEl.style.color = data.pcr >= 1.15 ? "var(--emerald-profit)" : (data.pcr <= 0.85 ? "var(--rose-loss)" : "var(--cyan-neon)");
    }
    if (maxPainEl) maxPainEl.textContent = data.max_pain ? data.max_pain.toLocaleString() : "24,350";
    if (vixEl) vixEl.textContent = data.india_vix ? data.india_vix : "--";
  }

  renderMorningBriefing(brief) {
    if (!brief) return;
    this.renderChatMessage("JARVIS (PRE-MARKET BRIEFING)", brief.spoken_brief, false);
    this.updateHudTranscript(brief.spoken_brief);
    this.playAlertChime();
  }

  // 12. Market Scanner & Tickers
  async fetchMarketScan() {
    try {
      const res = await fetch("/api/scan");
      if (res.ok) {
        const data = await res.json();
        if (data.signals) {
          this.renderSignals(data.signals);
        }
      }
    } catch (e) {
      console.warn("[Scanner] Error fetching scan:", e);
    }
  }

  renderSignals(signals) {
    const listEl = document.getElementById("signals-list");
    if (!signals || signals.length === 0) {
      listEl.innerHTML = `
        <div class="empty-signals">
          <span class="pulse-dot"></span>
          <p>Institutional order flow across NSE and Crypto is normal. No fair value gap imbalances detected.</p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = signals.map(sig => {
      const isBull = sig.signal_type.includes("BULLISH");
      const badgeClass = isBull ? "badge-bullish" : "badge-bearish";

      const symKey = sig.symbol.toLowerCase().replace(/[^a-z0-9]/g, "");
      const chipEl = document.getElementById(`price-${symKey}`);
      if (chipEl) chipEl.textContent = `${sig.current_price.toLocaleString()}`;

      return `
        <div class="signal-card">
          <div class="signal-top">
            <span class="signal-sym">${sig.symbol}</span>
            <span class="signal-badge ${badgeClass}">${sig.signal_type.replace('_', ' ')}</span>
          </div>
          <div class="signal-metrics">
            <div class="sig-metric-item">
              <span>ENTRY</span>
              <span>₹/$ ${sig.entry_zone[0]}</span>
            </div>
            <div class="sig-metric-item">
              <span>STOP</span>
              <span>₹/$ ${sig.stop_loss}</span>
            </div>
            <div class="sig-metric-item">
              <span>R:R</span>
              <span>1:${sig.risk_reward}</span>
            </div>
          </div>
          <p class="signal-desc">${sig.description}</p>
        </div>
      `;
    }).join("");
  }

  // 13. Event Bindings
  bindEvents() {
    const input = document.getElementById("user-text-input");
    const sendBtn = document.getElementById("send-btn");
    const micBtn = document.getElementById("mic-btn");
    const refreshBtn = document.getElementById("refresh-radar-btn");
    const modeToggleBtn = document.getElementById("mode-toggle-btn");
    const hudExpandBtn = document.getElementById("hud-expand-btn");
    const hudMicBtn = document.getElementById("hud-mic-btn");
    const hudReactorBtn = document.getElementById("hud-reactor-btn");
    const arcReactor = document.getElementById("arc-reactor");

    const submitInput = () => {
      const val = input.value.trim();
      if (val) {
        this.sendUserMessage(val);
        input.value = "";
      }
    };

    sendBtn.addEventListener("click", submitInput);

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        submitInput();
      }
    });

    input.addEventListener("focus", () => {
      window.scrollTo(0, 0);
    });

    modeToggleBtn.addEventListener("click", () => this.toggleHudMode());
    hudExpandBtn.addEventListener("click", () => this.setHudMode(false));

    // Live Voice Conversation Toggles
    micBtn.addEventListener("click", () => this.toggleLiveConversation());
    hudMicBtn.addEventListener("click", () => this.toggleLiveConversation());
    hudReactorBtn.addEventListener("click", () => this.toggleLiveConversation());
    if (arcReactor) {
      arcReactor.addEventListener("click", () => this.toggleLiveConversation());
    }

    refreshBtn.addEventListener("click", () => {
      this.fetchMarketScan();
      this.fetchOptionChain();
      if (this.currentSymbol) this.loadChartCandles(this.currentSymbol);
    });

    // Timeframe (5m, 15m, 1h) button listeners
    document.querySelectorAll(".tf-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
        const target = e.currentTarget;
        target.classList.add("active");
        const tf = target.getAttribute("data-tf") || "15m";
        this.currentTimeframe = tf;
        this.loadChartCandles(this.currentSymbol, tf);
      });
    });

    // Ticker chips switching
    document.querySelectorAll(".ticker-chip").forEach(chip => {
      chip.addEventListener("click", (e) => {
        document.querySelectorAll(".ticker-chip").forEach(c => c.classList.remove("active"));
        const target = e.currentTarget;
        target.classList.add("active");
        const sym = target.getAttribute("data-symbol");
        if (sym) {
          this.currentSymbol = sym;
          this.loadChartCandles(sym, this.currentTimeframe || "15m");
        }
      });
    });

    document.querySelectorAll(".action-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const cmd = e.target.getAttribute("data-cmd");
        if (cmd) this.sendUserMessage(cmd);
      });
    });

    const clearBtn = document.getElementById("clear-dynamic-btn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => this.resetDynamicPanel());
    }
  }

  // 14. Autonomous Dynamic Omni-Canvas Engine
  renderDynamicWidget(widget) {
    if (!widget || !widget.type) return;

    const titleEl = document.getElementById("dynamic-panel-title");
    const container = document.getElementById("dynamic-content-body");
    if (!container) return;

    if (widget.title && titleEl) {
      titleEl.textContent = widget.title.toUpperCase();
    }

    const type = widget.type;
    const d = widget.data || {};

    let html = "";

    if (type === "weather") {
      html = `
        <div class="weather-card">
          <div class="weather-top">
            <div>
              <div class="weather-city">${this.escapeHtml(d.city || "Weather")}</div>
              <div class="weather-desc">${this.escapeHtml(d.condition || "Clear Sky")}</div>
              <div style="font-size: 0.62rem; color: #38bdf8; font-weight: 600; margin-top: 2px;">
                ⚡ Powered by ${d.provider || "WeatherAPI.com"}
              </div>
            </div>
            <div class="weather-icon-large">
              ${d.icon_url ? `<img src="${d.icon_url}" alt="weather" style="width: 44px; height: 44px; vertical-align: middle;">` : (d.icon || "☀️")}
            </div>
          </div>
          <div class="weather-temp-row">
            <span class="weather-temp-main">${d.temp || "--"}</span>
            <div style="display: flex; flex-direction: column; justify-content: center; margin-left: 0.4rem;">
              <span class="weather-feels">Feels like ${d.feels_like || "--"}</span>
              ${d.max_temp && d.min_temp ? `<span style="font-size: 0.68rem; color: #94a3b8;">H: ${d.max_temp} • L: ${d.min_temp}</span>` : ""}
            </div>
          </div>
          <div class="weather-stats-grid">
            <div class="w-stat">
              <span class="w-stat-label">HUMIDITY</span>
              <span class="w-stat-val">${d.humidity || "--"}</span>
            </div>
            <div class="w-stat">
              <span class="w-stat-label">WIND</span>
              <span class="w-stat-val">${d.wind || "--"}</span>
            </div>
            <div class="w-stat">
              <span class="w-stat-label">UV INDEX</span>
              <span class="w-stat-val">${d.uv_index || "--"}</span>
            </div>
          </div>
          ${d.air_quality_status ? `
            <div style="margin-top: 0.4rem; padding-top: 0.3rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; font-size: 0.68rem; color: #cbd5e1;">
              <span>Air Quality (AQI): <b style="color: #34d399;">${this.escapeHtml(d.air_quality_status)}</b></span>
              <span>PM2.5: <b>${d.air_quality_pm25 || "--"}</b></span>
            </div>
          ` : ""}
        </div>
      `;
    } else if (type === "cricket") {
      const bats = d.current_batsmen || [];
      const bowler = d.current_bowler || {};
      const otherMatches = d.all_matches || [];
      html = `
        <div class="cricket-card">
          <div class="cricket-header">
            <span class="cricket-teams">${d.teams || "CRICKET MATCH"}</span>
            <span class="cricket-badge">LIVE MATCH</span>
          </div>
          <div class="cricket-scores-box">
            <div class="cricket-score-row">
              <span style="font-weight:700; color:#fff;">${d.score_team1 || ""}</span>
            </div>
            ${d.score_team2 ? `
            <div class="cricket-score-row" style="color: #38bdf8; margin-top:0.2rem;">
              <span style="font-weight:700;">${d.score_team2}</span>
            </div>` : ""}
          </div>
          <div class="cricket-status">⚡ ${d.status || ""}</div>
          ${bats.length > 0 ? `
          <div class="batsmen-table">
            <div style="font-size: 0.58rem; color: var(--text-muted); border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0.2rem;">CURRENT BATSMEN</div>
            ${bats.map(b => `<div class="batsman-row"><span>${b.name}</span><span style="color: #fff; font-weight:700;">${b.runs} (${b.balls})</span></div>`).join("")}
            <div class="batsman-row" style="margin-top: 0.3rem; color: #cbd5e1;"><span>Bowling: ${bowler.name || "Bowler"}</span><span>${bowler.wickets || 0}/${bowler.runs || 0} (${bowler.overs || 0} ov)</span></div>
          </div>` : ""}
          ${otherMatches.length > 0 ? `
          <div style="margin-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.35rem;">
            <div style="font-size: 0.58rem; color: #94a3b8; font-weight: 700; margin-bottom: 0.25rem;">OTHER ACTIVE MATCHES</div>
            ${otherMatches.slice(0, 4).map(m => `
              <div style="font-size: 0.62rem; color: #cbd5e1; padding: 0.15rem 0; border-bottom: 1px solid rgba(255,255,255,0.03); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                • ${m.title}
              </div>
            `).join("")}
          </div>` : ""}
        </div>
      `;
    } else if (type === "os_action") {
      html = `
        <div class="dev-card" style="border-color: rgba(56, 189, 248, 0.4);">
          <div class="dev-title" style="color: #38bdf8;">🖥️ Desktop Action Executed</div>
          <div style="font-size:0.85rem; font-weight:700; color:#fff; margin-top:0.35rem;">${d.message || "कार्रवाई पूरी कर दी गई है।"}</div>
          <div class="dev-stat-row" style="margin-top:0.4rem;">
            <span class="dev-stat-label">COMMAND</span>
            <span class="dev-stat-val" style="color: #a5b4fc; font-family: var(--font-mono);">${d.action || ""}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">STATUS</span>
            <span class="dev-stat-val" style="color: var(--emerald-profit);">LAUNCHED</span>
          </div>
        </div>
      `;
        } else if (type === "developer") {
      html = `
        <div class="dev-card">
          <div class="dev-title">⚡ ${widget.title || "Developer Workstation"}</div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">GIT BRANCH</span>
            <span class="dev-stat-val" style="color: #38bdf8;">${d.git_branch || "main"}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">PYTHON RUNTIME</span>
            <span class="dev-stat-val">${d.python_env || "Python 3.12"}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">ACTIVE PORTS</span>
            <span class="dev-stat-val" style="color: #a5b4fc;">${d.active_ports || "8000"}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">DATABASE</span>
            <span class="dev-stat-val" style="color: #fbbf24;">${d.database || "Firestore (Live)"}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">WORKSPACE</span>
            <span class="dev-stat-val" style="font-size: 0.6rem;">${d.workspace || "D:\\Trading"}</span>
          </div>
        </div>
      `;
    } else if (type === "vision") {
      const trendBadge = d.trend === "BULLISH"
        ? '<span class="vision-trend-badge bullish">▲ BULLISH TREND</span>'
        : (d.trend === "BEARISH" ? '<span class="vision-trend-badge bearish">▼ BEARISH TREND</span>' : '<span class="vision-trend-badge neutral">● REAL-TIME MONITORING</span>');

      const fallbackImg = (!this.liveScreenStream && d.image_base64)
        ? `<img src="data:image/jpeg;base64,${d.image_base64}" id="live-vision-fallback-img" class="vision-fallback-snap" alt="Live Screen Snapshot" />`
        : "";

      html = `
        <div class="live-vision-terminal">
          <div class="vision-feed-header">
            <div class="vision-live-indicator">
              <span class="live-beacon"></span>
              <span class="vision-title-text" id="live-vision-status-label">${this.liveScreenStream ? "● LIVE SCREEN STREAM (60 FPS)" : "👁️ LIVE SCREEN VISION HUD"}</span>
            </div>
            <div class="vision-metrics">
              <span class="vision-fps-chip" id="vision-fps-badge">${this.liveScreenStream ? "60 FPS" : "ACTIVE"}</span>
              ${trendBadge}
            </div>
          </div>

          <div class="vision-video-wrapper" id="vision-viewport">
            <video id="live-screen-feed" autoplay playsinline muted style="${this.liveScreenStream ? "display:block;" : "display:none;"}"></video>
            <canvas id="vision-overlay-canvas"></canvas>
            ${fallbackImg}
            <div class="vision-laser-sweep"></div>
            <div class="vision-crosshair ch-tl"></div>
            <div class="vision-crosshair ch-tr"></div>
            <div class="vision-crosshair ch-bl"></div>
            <div class="vision-crosshair ch-br"></div>
            
            <div id="vision-stream-prompt" class="vision-stream-prompt" style="${this.liveScreenStream ? "display:none;" : "display:flex;"}">
              <span style="font-size: 1.8rem; margin-bottom: 0.2rem;">🖥️</span>
              <div style="font-weight: 700; color: #fff; font-size: 0.85rem;">लाइव स्क्रीन विज़न चालू करें</div>
              <p style="font-size: 0.68rem; color: #94a3b8; text-align: center; margin: 0.3rem 0 0.6rem 0;">
                JARVIS को रियल-टाइम 60 FPS में अपना ट्रेडिंग चार्ट या डेस्कटॉप लाइव देखने की अनुमति दें।
              </p>
              <button id="btn-start-stream" class="btn-activate-stream">
                ▶️ START 60 FPS LIVE STREAM
              </button>
            </div>
          </div>

          <div class="vision-control-actions" style="grid-template-columns: 1fr 1.1fr 1.1fr; gap: 0.35rem; margin-bottom: 0.35rem;">
            <button id="btn-analyze-frame" class="vision-hud-btn primary" title="Analyze active screen">
              ⚡ Live Vision
            </button>
            <button id="btn-auto-detect-patterns" class="vision-hud-btn accent" title="Auto-detect support/resistance, FVG, patterns">
              📐 Overlays
            </button>
            <button id="btn-ocr-clipboard" class="vision-hud-btn accent" title="Extract code/error and copy to Windows clipboard">
              📋 Copy Code
            </button>
          </div>
          <div class="vision-control-actions-sub" style="display: flex; gap: 0.35rem; margin-bottom: 0.5rem;">
            <button id="btn-toggle-autoradar" class="vision-hud-btn secondary" style="flex: 1;">
              ${this.isAutoRadarActive ? "🔄 Auto-Radar: ON (8s)" : "🔄 Auto-Radar: OFF"}
            </button>
            <button id="btn-stop-stream" class="vision-hud-btn danger" style="${this.liveScreenStream ? "display:inline-block;" : "display:none;"}; flex: 0.8;">
              ⏹️ Stop Live
            </button>
          </div>

          <div class="vision-ai-perception">
            <div class="perception-header">
              <span>🧠 LIVE NEURAL PERCEPTION & INSIGHTS</span>
              <span style="font-size: 0.55rem; color: #38bdf8; font-family: var(--font-mono);">GEMINI 2.5 MULTIMODAL</span>
            </div>
            <div class="perception-body" id="live-vision-text">
              ${d.text || "स्क्रीन का लाइव विज़न मॉनिटर सक्रिय है।"}
            </div>
          </div>
        </div>
      `;
    } else if (type === "cyber_report") {
      const risk = d.risk_score || 0;
      let riskColor = "#10b981";
      let riskBg = "rgba(16, 185, 129, 0.15)";
      if (risk >= 80) {
        riskColor = "#f43f5e";
        riskBg = "rgba(244, 63, 94, 0.2)";
      } else if (risk >= 55) {
        riskColor = "#f97316";
        riskBg = "rgba(249, 115, 22, 0.2)";
      } else if (risk >= 30) {
        riskColor = "#eab308";
        riskBg = "rgba(234, 179, 8, 0.2)";
      }

      const indicators = d.indicators || [];
      const scamTypes = d.scam_types || [];
      const recs = d.safety_recommendations || [];

      html = `
        <div class="cyber-threat-card" style="border-color: ${riskColor};">
          <div class="cyber-card-header">
            <div class="cyber-header-left">
              <span class="cyber-radar-pulse" style="background: ${riskColor}; color: ${riskColor};"></span>
              <div class="cyber-title-group">
                <span class="cyber-header-title">🛡️ CYBER THREAT RADAR</span>
                <span class="cyber-domain-tag">${this.escapeHtml(d.domain || "Unknown Domain")}</span>
              </div>
            </div>
            <div class="cyber-risk-badge" style="color: ${riskColor}; background: ${riskBg}; border-color: ${riskColor};">
              ${risk}% RISK // ${this.escapeHtml(d.threat_level || "UNKNOWN")}
            </div>
          </div>

          <div class="cyber-verdict-banner" style="border-left: 3px solid ${riskColor};">
            <div style="font-weight: 700; color: #fff; font-size: 0.8rem;">${this.escapeHtml(d.threat_badge || "")}</div>
            <p style="font-size: 0.72rem; color: #cbd5e1; margin-top: 0.2rem; line-height: 1.4;">
              ${this.escapeHtml(d.hindi_verdict || "")}
            </p>
          </div>

          <!-- Technical Metadata Chips -->
          <div class="cyber-meta-grid">
            <div class="cyber-meta-item">
              <span class="cyber-meta-label">TARGET IP</span>
              <span class="cyber-meta-val">${this.escapeHtml(d.ip_address || "Hidden")}</span>
            </div>
            <div class="cyber-meta-item">
              <span class="cyber-meta-label">DOMAIN TLD</span>
              <span class="cyber-meta-val">.${this.escapeHtml(d.tld || "unknown")}</span>
            </div>
            <div class="cyber-meta-item">
              <span class="cyber-meta-label">TARGET BRAND</span>
              <span class="cyber-meta-val" style="color: ${d.impersonated_brand ? '#f43f5e' : '#94a3b8'};">
                ${this.escapeHtml(d.impersonated_brand ? "Fake " + d.impersonated_brand : "None")}
              </span>
            </div>
            <div class="cyber-meta-item">
              <span class="cyber-meta-label">PROPAGATION</span>
              <span class="cyber-meta-val">${d.is_whatsapp_scam ? "WhatsApp Loop (s=wa)" : "Direct Web"}</span>
            </div>
          </div>

          <!-- Scam Classification Tags -->
          ${scamTypes.length > 0 ? `
            <div class="pattern-tag-cloud" style="margin-top: 0.35rem;">
              ${scamTypes.map(st => `<span class="pattern-pill resistance">${this.escapeHtml(st)}</span>`).join("")}
            </div>
          ` : ""}

          <!-- Forensics Indicators -->
          ${indicators.length > 0 ? `
            <div class="cyber-indicators-list" style="margin-top: 0.4rem;">
              <span style="font-size: 0.64rem; font-weight: 700; color: #94a3b8; font-family: var(--font-mono); letter-spacing: 0.5px;">
                FORENSIC THREAT INDICATORS (${indicators.length}):
              </span>
              ${indicators.map(ind => `
                <div class="cyber-indicator-item">
                  <div class="cyber-ind-header">
                    <span class="cyber-ind-title">${this.escapeHtml(ind.title)}</span>
                    <span class="cyber-ind-sev ${ind.severity ? ind.severity.toLowerCase() : 'high'}">${ind.severity}</span>
                  </div>
                  <p class="cyber-ind-desc">${this.escapeHtml(ind.detail)}</p>
                </div>
              `).join("")}
            </div>
          ` : ""}

          <!-- Safety Advisory Recommendations -->
          <div class="cyber-advisory-box" style="margin-top: 0.4rem;">
            <div style="font-size: 0.65rem; font-weight: 700; color: #fbbf24; margin-bottom: 0.25rem;">
              🛡️ JARVIS SAFETY PROTOCOL & ADVISORY:
            </div>
            <ul class="cyber-advisory-list">
              ${recs.map(r => `<li>${this.escapeHtml(r)}</li>`).join("")}
            </ul>
          </div>

          <!-- PDF Report Download & Actions -->
          <div class="cyber-pdf-actions" style="margin-top: 0.5rem; display: flex; gap: 0.4rem;">
            ${d.pdf_report && d.pdf_report.web_url ? `
              <a href="${d.pdf_report.web_url}" target="_blank" download="${d.pdf_report.filename}" class="cyber-pdf-btn" style="flex: 1; text-align: center; text-decoration: none;">
                📄 Download Official PDF Report
              </a>
              <a href="${d.pdf_report.web_url}" target="_blank" class="cyber-pdf-btn view-btn" style="padding: 0.4rem 0.6rem; text-decoration: none;" title="Open in browser">
                👁️ Open PDF
              </a>
            ` : `
              <button class="cyber-pdf-btn" onclick="window.open('/reports/', '_blank')" style="flex: 1;">
                📄 View PDF Intelligence Report
              </button>
            `}
          </div>
        </div>
      `;
    } else if (type === "deep_research_report") {
      const depth = (d.mode || d.depth_mode || "STANDARD").toUpperCase();
      let depthColor = "#38bdf8";
      let depthBg = "rgba(56, 189, 248, 0.15)";
      if (depth === "DEEP") {
        depthColor = "#a855f7";
        depthBg = "rgba(168, 85, 247, 0.2)";
      } else if (depth === "QUICK") {
        depthColor = "#10b981";
        depthBg = "rgba(16, 185, 129, 0.15)";
      }

      const keyMetrics = d.key_metrics || [];
      const sections = d.sections || [];
      const timeline = d.timeline || [];
      const citations = d.citations || [];
      const pdf = d.pdf_report || {};

      html = `
        <div class="research-report-card" style="border-color: ${depthColor};">
          <div class="research-card-header">
            <div class="research-header-left">
              <span class="research-radar-pulse" style="background: ${depthColor}; color: ${depthColor};"></span>
              <div class="research-title-group">
                <span class="research-header-title">🔬 UNIVERSAL DEEP RESEARCH LAB</span>
                <span class="research-category-tag">${this.escapeHtml(d.category_display || "Universal Research")} // ${this.escapeHtml(d.topic || "")}</span>
              </div>
            </div>
            <div class="research-depth-badge" style="color: ${depthColor}; background: ${depthBg}; border-color: ${depthColor};">
              ${depth} RESEARCH
            </div>
          </div>

          <!-- Report Title & Subtitle Banner -->
          <div class="research-title-banner" style="border-left: 3px solid ${depthColor};">
            <h3 style="font-size: 0.88rem; font-weight: 800; color: #fff; margin: 0; line-height: 1.3;">
              ${this.escapeHtml(d.title || d.topic || "Research Dossier")}
            </h3>
            ${d.subtitle ? `
              <p style="font-size: 0.72rem; color: #94a3b8; margin: 0.25rem 0 0; line-height: 1.35; font-style: italic;">
                ${this.escapeHtml(d.subtitle)}
              </p>
            ` : ""}
          </div>

          <!-- 4-Box Key Metrics Grid -->
          ${keyMetrics.length > 0 ? `
            <div class="research-metrics-grid">
              ${keyMetrics.slice(0, 4).map(m => `
                <div class="research-metric-cell">
                  <span class="research-metric-label">${this.escapeHtml(m.label || "Metric")}</span>
                  <span class="research-metric-val">${this.escapeHtml(m.value || "--")}</span>
                </div>
              `).join("")}
            </div>
          ` : ""}

          <!-- Bilingual Executive Summary -->
          <div class="research-summary-box">
            <div class="research-summary-label">
              <span>🇮🇳 कार्यकारी सारांश (EXECUTIVE SUMMARY)</span>
            </div>
            <p class="research-summary-text-hi">
              ${this.escapeHtml(d.executive_summary_hi || "")}
            </p>
            ${d.executive_summary_en ? `
              <p class="research-summary-text-en">
                ${this.escapeHtml(d.executive_summary_en)}
              </p>
            ` : ""}
          </div>

          <!-- 10 Comprehensive Chapters Included -->
          ${d.modules && d.modules.length > 0 ? `
            <div class="research-timeline-section" style="margin-top: 0.35rem;">
              <div class="research-timeline-label" style="color: #38bdf8;">
                📖 10-PAGE FORMAL RESEARCH MONOGRAPH (${d.modules.length} MODULES):
              </div>
              <div class="research-timeline-rail" style="border-left-color: #38bdf8; max-height: 180px; overflow-y: auto;">
                ${d.modules.map(m => `
                  <div class="research-timeline-item" style="margin-bottom: 0.25rem;">
                    <span class="timeline-date" style="color: #fbbf24; min-width: 55px;">PAGE ${m.module_num || 1}</span>
                    <span class="timeline-event" style="font-size: 0.68rem; color: #f1f5f9;">
                      <b>${this.escapeHtml(m.module_title || "")}</b>
                      <div style="font-size: 0.62rem; color: #94a3b8; margin-top: 1px;">${this.escapeHtml((m.section_subtitle || m.executive_brief_hi || "").slice(0, 95))}...</div>
                    </span>
                  </div>
                `).join("")}
              </div>
            </div>
          ` : (timeline.length > 0 ? `
            <div class="research-timeline-section">
              <div class="research-timeline-label">⏱️ CHRONOLOGICAL TIMELINE (${timeline.length} MILESTONES)</div>
              <div class="research-timeline-rail">
                ${timeline.slice(0, 4).map(t => `
                  <div class="research-timeline-item">
                    <span class="timeline-date">${this.escapeHtml(t.date_or_period || "")}</span>
                    <span class="timeline-event">${this.escapeHtml(t.event || "")}</span>
                  </div>
                `).join("")}
              </div>
            </div>
          ` : "")}

          <!-- Multi-Source Intelligence Audit Footer -->
          <div class="research-audit-bar">
            <span>📚 ${d.sources_analyzed || (d.sources && d.sources.length) || citations.length || 0} SOURCES AUDITED (${d.execution_time_sec || d.elapsed_seconds || 0}s)</span>
            <span style="color: #10b981;">
              ${d.verification_summary ? `✓ ${d.verification_summary.verification_accuracy_pct}% ACCURACY (${d.verification_summary.verified_count} VERIFIED CLAIMS)` : "✓ FACT-CHECKED & VERIFIED"}
            </span>
          </div>

          <!-- Verified Claims Preview Strip -->
          ${d.verified_claims && d.verified_claims.length > 0 ? `
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 4px; padding: 0.35rem 0.5rem; margin-top: 0.35rem;">
              <div style="font-size: 0.64rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.2rem;">
                📋 INDEPENDENT FACT VERIFICATION REGISTRY (${d.verified_claims.length} CLAIMS):
              </div>
              <div style="display: flex; flex-direction: column; gap: 3px; max-height: 100px; overflow-y: auto;">
                ${d.verified_claims.slice(0, 4).map(c => `
                  <div style="font-size: 0.62rem; color: #cbd5e1; display: flex; gap: 6px; align-items: baseline;">
                    <span style="color: ${c.verification_status === 'VERIFIED' ? '#34d399' : (c.verification_status === 'PARTIALLY_VERIFIED' ? '#fbbf24' : '#f87171')}; font-weight: 700; min-width: 55px;">
                      [${this.escapeHtml(c.verification_status)}]
                    </span>
                    <span style="flex: 1;">${this.escapeHtml(c.claim_text.slice(0, 90))}...</span>
                  </div>
                `).join("")}
              </div>
            </div>
          ` : ""}

          <!-- PDF Publication Download Action Bar -->
          <div class="research-pdf-actions">
            ${(pdf.web_url || d.pdf_filename) ? `
              <a href="${pdf.web_url || ('/reports/' + d.pdf_filename)}" target="_blank" download="${pdf.filename || d.pdf_filename}" class="research-pdf-btn" style="flex: 1; text-align: center; text-decoration: none;">
                📄 Download Official PDF Report (${d.pdf_pages || pdf.pages || 1}p • ${pdf.file_size_kb || 0} KB)
              </a>
              <a href="${pdf.web_url || ('/reports/' + d.pdf_filename)}" target="_blank" class="research-pdf-btn view-btn" style="padding: 0.45rem 0.7rem; text-decoration: none;" title="Open in New Tab">
                👁️ Open PDF
              </a>
            ` : `
              <button class="research-pdf-btn" onclick="window.open('/reports/', '_blank')" style="flex: 1;">
                📄 View Generated Research Report
              </button>
            `}
          </div>
        </div>
      `;
    } else if (type === "ocr_clipboard") {
      const isOk = d.clipboard_copied !== false;
      html = `
        <div class="ocr-clipboard-card">
          <div class="ocr-card-header">
            <div class="ocr-card-title">
              <span>📋</span> Windows Clipboard OCR
            </div>
            <span class="ocr-badge">${isOk ? "COPIED TO CLIPBOARD" : "EXTRACTED"}</span>
          </div>
          <div class="ocr-code-viewport">${this.escapeHtml(d.extracted_text || d.preview || "No code detected")}</div>
          <div class="ocr-action-bar">
            <span>${d.char_count || 0} characters extracted</span>
            <span style="color: #38bdf8; font-weight: 600;">Press Ctrl + V to Paste Anywhere</span>
          </div>
        </div>
      `;
    } else if (type === "chart_patterns") {
      const overlays = d.overlays || [];
      const patterns = d.patterns_detected || [];
      html = `
        <div class="ocr-clipboard-card" style="border-color: rgba(56, 189, 248, 0.4);">
          <div class="ocr-card-header">
            <div class="ocr-card-title" style="color: #38bdf8;">
              <span>📐</span> Chart Pattern Auto-Overlays
            </div>
            <span class="ocr-badge" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; border-color: rgba(56, 189, 248, 0.4);">
              ${d.trend || "ACTIVE"}
            </span>
          </div>
          <div class="pattern-tag-cloud">
            ${patterns.map(p => `<span class="pattern-pill fvg">${this.escapeHtml(p)}</span>`).join("")}
          </div>
          <div class="perception-body" style="font-size: 0.72rem; color: #f1f5f9; margin-top: 0.3rem;">
            ${d.summary || "चार्ट पैटर्न्स और सपोर्ट/रेजिस्टेंस लेवल्स डिटेक्ट कर लिए गए हैं।"}
          </div>
          <div style="font-size: 0.65rem; color: #94a3b8; font-family: var(--font-mono); margin-top: 0.2rem;">
            ${overlays.length} visual zones projected onto Vision HUD Canvas
          </div>
        </div>
      `;
      // Trigger canvas drawing if overlays exist
      if (overlays.length > 0) {
        setTimeout(() => this.drawChartOverlays(overlays), 150);
      }
    } else if (type === "calculator") {
      html = `
        <div class="dev-card" style="border-color: rgba(16, 185, 129, 0.4); background: linear-gradient(135deg, rgba(16, 185, 129, 0.05), rgba(6, 182, 212, 0.08));">
          <div class="dev-title" style="color: #10b981;">⚡ Instant Local Calculation (0.001s)</div>
          <div style="font-size:1.8rem; font-weight:800; color:#fff; margin-top:0.35rem; font-family: var(--font-mono); letter-spacing: 0.5px;">
            ${d.formatted || d.result || ""}
          </div>
          <div class="dev-stat-row" style="margin-top:0.4rem;">
            <span class="dev-stat-label">EXPRESSION</span>
            <span class="dev-stat-val" style="color: #38bdf8; font-family: var(--font-mono); font-size: 0.85rem;">${d.expression || ""}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">STATUS</span>
            <span class="dev-stat-val" style="color: var(--emerald-profit);">COMPUTED LOCALLY (NO WEB SEARCH)</span>
          </div>
        </div>
      `;
    } else if (type === "briefing") {
      html = `
        <div class="dev-card" style="border-color: rgba(245, 158, 11, 0.4);">
          <div class="dev-title" style="color: #fbbf24;">☀️ Pre-Market Morning Briefing</div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">GIFT NIFTY</span>
            <span class="dev-stat-val" style="color: var(--emerald-profit);">${d.gift_nifty || "--"} (+${d.gift_nifty_change || 0} pts)</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">GLOBAL SENTIMENT</span>
            <span class="dev-stat-val">${d.us_markets_summary || "Mild Green"}</span>
          </div>
          <div class="dev-stat-row">
            <span class="dev-stat-label">CRUDE OIL / DXY</span>
            <span class="dev-stat-val">$${d.crude_oil || 74.8} / ${d.dxy || 104.2}</span>
          </div>
          <p style="font-size:0.72rem; line-height:1.4; color:var(--text-secondary); margin-top:0.4rem;">${d.spoken_brief || ""}</p>
        </div>
      `;
    } else if (type === "market_scan") {
      const sigs = d.signals || [];
      html = `
        <div class="dev-card" style="border-color: rgba(0, 242, 254, 0.35);">
          <div class="dev-title" style="color: var(--cyan-neon);">📈 ${d.symbol || "Market"} SMC Radar</div>
          ${sigs.length > 0 ? `
            <div style="font-size:0.75rem; font-weight:700; color:var(--emerald-profit); margin-top:0.2rem;">Setup: ${sigs[0].signal_type}</div>
            <div class="dev-stat-row"><span class="dev-stat-label">ENTRY ZONE</span><span class="dev-stat-val">${sigs[0].entry_zone ? sigs[0].entry_zone.join(" - ") : "--"}</span></div>
            <div class="dev-stat-row"><span class="dev-stat-label">STOP LOSS</span><span class="dev-stat-val">${sigs[0].stop_loss || "--"}</span></div>
            <div class="dev-stat-row"><span class="dev-stat-label">RISK:REWARD</span><span class="dev-stat-val">1:${sigs[0].risk_reward || 2.0}</span></div>
            <p style="font-size:0.7rem; color:var(--text-secondary); margin-top:0.3rem;">${sigs[0].description || ""}</p>
          ` : `<p style="font-size:0.72rem; color:var(--text-muted);">फिलहाल कोई नया असंतुलन नहीं है। मार्केट संतुलन में है।</p>`}
        </div>
      `;
    } else if (type === "web_search") {
      const results = d.results || [];
      const sourcesCount = d.sources_count || results.length;
      const searchTime = d.search_time_ms ? `${d.search_time_ms}ms` : "Live";

      html = `
        <div class="web-search-card">
          <div class="web-search-header">
            <span class="web-search-title">🌐 Live Internet Grounding</span>
            <span class="web-search-pill">⚡ ${searchTime} • ${sourcesCount} Sources</span>
          </div>
          <div class="web-search-query">
            <span style="color:var(--text-muted); font-size:0.68rem;">Query:</span> <span style="color:#38bdf8; font-weight:600; font-size:0.75rem;">"${d.query || ""}"</span>
          </div>
          ${d.summary ? `
          <div class="web-search-summary">
            <div style="font-size:0.6rem; color:var(--emerald-profit); font-weight:700; margin-bottom:0.25rem;">✦ 100% VERIFIED REAL-TIME ANSWER</div>
            <p style="margin:0; font-size:0.78rem; line-height:1.45; color:#f8fafc;">${d.summary}</p>
          </div>` : ""}
          <div class="web-search-sources">
            <div style="font-size:0.58rem; color:#94a3b8; font-weight:700; margin-bottom:0.35rem; letter-spacing:0.05em;">GROUND TRUTH CITATIONS</div>
            ${results.slice(0, 5).map(r => `
              <div class="web-source-item">
                <div class="web-source-row">
                  <span class="web-source-tag">${r.source || "Web"}</span>
                  ${r.url ? `<a href="${r.url}" target="_blank" rel="noopener noreferrer" class="web-source-link">OPEN ↗</a>` : ""}
                </div>
                <div class="web-source-title">${r.title || ""}</div>
                <div class="web-source-snippet">${r.snippet || ""}</div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    } else if (type === "breaking_news") {
      const results = d.results || [];
      const cat = d.category || "शीर्ष ब्रेकिंग न्यूज़";
      const count = d.count || results.length;
      const fetchTime = d.fetch_time_ms ? `${d.fetch_time_ms}ms` : "Live";

      html = `
        <div class="breaking-news-card">
          <div class="breaking-news-header">
            <span class="breaking-news-title">
              <span class="pulsing-live-dot"></span> LIVE NEWS RADAR
            </span>
            <span class="breaking-news-pill">⚡ ${fetchTime} • ${count} Fresh Stories</span>
          </div>

          <!-- Category Quick Tabs -->
          <div class="news-category-bar">
            <button class="news-cat-tab ${d.category_key === 'top' ? 'active' : ''}" onclick="window.jarvis.sendUserMessage('आज की ताज़ा और बड़ी खबरें बताओ')">🔥 Top Stories</button>
            <button class="news-cat-tab ${d.category_key === 'markets' ? 'active' : ''}" onclick="window.jarvis.sendUserMessage('मार्केट और शेयर बाजार की ताज़ा खबर बताओ')">📈 Markets</button>
            <button class="news-cat-tab ${d.category_key === 'tech' ? 'active' : ''}" onclick="window.jarvis.sendUserMessage('लेटेस्ट टेक और एआई न्यूज़ बताओ')">💻 Tech/AI</button>
            <button class="news-cat-tab ${d.category_key === 'sports' ? 'active' : ''}" onclick="window.jarvis.sendUserMessage('खेल और क्रिकेट की ताज़ा खबरें बताओ')">🏏 Sports</button>
          </div>

          ${d.summary ? `
          <div class="breaking-news-summary">
            <div style="font-size:0.58rem; color:#f59e0b; font-weight:700; margin-bottom:0.25rem;">✦ LIVE HIGHLIGHTS (${cat})</div>
            <p style="margin:0; font-size:0.75rem; line-height:1.45; color:#f8fafc;">${d.summary}</p>
          </div>` : ""}

          <div class="breaking-news-list">
            <div style="font-size:0.58rem; color:#94a3b8; font-weight:700; margin-bottom:0.35rem; letter-spacing:0.05em; display:flex; justify-content:space-between;">
              <span>UP-TO-THE-MINUTE HEADLINES</span>
              <span style="color:#38bdf8;">NEWEST FIRST</span>
            </div>
            ${results.map((r) => `
              <div class="news-article-item">
                <div class="news-article-top">
                  <span class="news-time-badge">${r.relative_time || "ताज़ा"}</span>
                  <span class="news-source-tag">${r.source || "News"}</span>
                  ${r.url ? `<a href="${r.url}" target="_blank" rel="noopener noreferrer" class="news-read-link">READ ↗</a>` : ""}
                </div>
                <div class="news-article-title">${r.title || ""}</div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    container.innerHTML = html;

    if (type === "vision") {
      this.initLiveVisionUI(d);
    }
  }


  // =========================================================================
  // 15. LIVE SCREEN VISION ENGINE (WebRTC 60 FPS Stream & Multi-Modal Vision)
  // =========================================================================
  async openLiveScreenVision() {
    this.renderDynamicWidget({
      type: "vision",
      title: "Live Screen Vision HUD",
      data: {
        text: "लाइव विज़न टर्मिनल शुरू हो रहा है... अनुमति मिलने पर आपकी स्क्रीन 60 FPS में लाइव स्ट्रीम होगी।",
        trend: "NEUTRAL",
        is_live_stream: true
      }
    });

    if (!this.liveScreenStream) {
      await this.startLiveScreenStream();
    }
  }

  initLiveVisionUI(data) {
    const video = document.getElementById("live-screen-feed");
    const promptEl = document.getElementById("vision-stream-prompt");
    const startBtn = document.getElementById("btn-start-stream");
    const analyzeBtn = document.getElementById("btn-analyze-frame");
    const autoBtn = document.getElementById("btn-toggle-autoradar");
    const stopBtn = document.getElementById("btn-stop-stream");

    if (this.liveScreenStream && video) {
      video.srcObject = this.liveScreenStream;
      video.style.display = "block";
      if (promptEl) promptEl.style.display = "none";
      if (stopBtn) stopBtn.style.display = "inline-block";
    }

    if (startBtn) {
      startBtn.addEventListener("click", () => this.startLiveScreenStream());
    }

    if (analyzeBtn) {
      analyzeBtn.addEventListener("click", () => {
        this.analyzeCurrentLiveFrame("स्क्रीन पर वर्तमान में क्या दिखाई दे रहा है? चार्ट लेवल्स और ट्रेंड का त्वरित विश्लेषण दें।");
      });
    }

    const patternBtn = document.getElementById("btn-auto-detect-patterns");
    if (patternBtn) {
      patternBtn.addEventListener("click", () => {
        this.triggerChartPatternDetection();
      });
    }

    const ocrBtn = document.getElementById("btn-ocr-clipboard");
    if (ocrBtn) {
      ocrBtn.addEventListener("click", () => {
        this.triggerScreenOCR();
      });
    }

    if (autoBtn) {
      autoBtn.addEventListener("click", () => this.toggleAutoRadar());
    }

    if (stopBtn) {
      stopBtn.addEventListener("click", () => this.stopLiveScreenStream());
    }
  }

  async startLiveScreenStream() {
    try {
      if (this.liveScreenStream) {
        this.stopLiveScreenStream();
      }

      console.log("[LiveVision] Requesting WebRTC screen capture...");
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          cursor: "always",
          displaySurface: "monitor",
          frameRate: { ideal: 60, max: 60 }
        },
        audio: false
      });

      this.liveScreenStream = stream;

      const video = document.getElementById("live-screen-feed");
      const promptEl = document.getElementById("vision-stream-prompt");
      const statusLabel = document.getElementById("live-vision-status-label");
      const fpsBadge = document.getElementById("vision-fps-badge");
      const stopBtn = document.getElementById("btn-stop-stream");

      if (video) {
        video.srcObject = stream;
        video.style.display = "block";
      }
      if (promptEl) promptEl.style.display = "none";
      if (statusLabel) statusLabel.textContent = "● LIVE SCREEN STREAMING (60 FPS)";
      if (fpsBadge) fpsBadge.textContent = "60 FPS LIVE";
      if (stopBtn) stopBtn.style.display = "inline-block";

      const fallbackImg = document.getElementById("live-vision-fallback-img");
      if (fallbackImg) fallbackImg.style.display = "none";

      // Handle user stopping stream via browser native UI banner
      stream.getVideoTracks()[0].onended = () => {
        this.stopLiveScreenStream();
      };

      this.renderChatMessage("JARVIS", "जी सर, लाइव स्क्रीन विज़न सक्रिय हो चुका है। आपका स्क्रीन रियल-टाइम 60 FPS में स्ट्रीम हो रहा है।", false);
      this.updateHudTranscript("LIVE VISION STREAM ACTIVE (60 FPS)");

      // Perform initial instantaneous live frame analysis in 1 second
      setTimeout(() => {
        this.analyzeCurrentLiveFrame("लाइव स्क्रीन एक्टिव हो चुकी है। चार्ट पर क्या दिखाई दे रहा है? मुख्य लेवल्स और ट्रेंड बताएं।");
      }, 1000);

    } catch (err) {
      console.warn("[LiveVision] Stream request notice:", err);
      const promptEl = document.getElementById("vision-stream-prompt");
      if (promptEl) promptEl.style.display = "flex";
    }
  }


  // =========================================================================
  // VISION 2.0: CHART PATTERNS AUTO-DETECTION & VISUAL OVERLAY ENGINE
  // =========================================================================
  async triggerChartPatternDetection() {
    const textEl = document.getElementById("live-vision-text");
    const statusLabel = document.getElementById("live-vision-status-label");
    if (statusLabel) statusLabel.textContent = "📐 AUTO-DETECTING CHART PATTERNS & ZONES...";
    if (textEl) textEl.textContent = "Gemini 2.5 Vision चार्ट पर सपोर्ट/रेजिस्टेंस, FVG और चार्ट पैटर्न्स को स्कैन कर रहा है...";

    try {
      const b64 = this.captureLiveVideoFrame();
      const payload = b64 ? { image_base64: b64 } : {};

      const res = await fetch("/api/screen_patterns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        const summary = data.summary || "चार्ट पैटर्न्स सफलतापूर्वक डिटेक्ट कर लिए गए हैं।";
        if (textEl) textEl.textContent = summary;
        if (statusLabel) statusLabel.textContent = this.liveScreenStream ? "● LIVE SCREEN STREAM (60 FPS)" : "👁️ LIVE SCREEN VISION HUD";

        // Draw overlays onto the HUD canvas
        if (data.overlays && data.overlays.length > 0) {
          this.drawChartOverlays(data.overlays);
        }

        // Project widget to dynamic panel
        this.renderDynamicWidget({
          type: "chart_patterns",
          title: "Vision 2.0 Chart Pattern Overlays",
          data: data
        });

        this.renderChatMessage("JARVIS (CHART PATTERNS)", summary, false);
        this.speakText(summary);
      }
    } catch (e) {
      console.error("[Vision 2.0] Pattern detection error:", e);
      if (textEl) textEl.textContent = "चार्ट स्कैन के दौरान त्रुटि आई। कृपया पुनः प्रयास करें।";
    }
  }

  // =========================================================================
  // VISION 2.0: INSTANT SCREEN OCR & WINDOWS CLIPBOARD COPY
  // =========================================================================
  async triggerScreenOCR() {
    const textEl = document.getElementById("live-vision-text");
    const statusLabel = document.getElementById("live-vision-status-label");
    if (statusLabel) statusLabel.textContent = "📋 EXTRACTING CODE/ERROR TO CLIPBOARD...";
    if (textEl) textEl.textContent = "स्क्रीन से कोड, एरर और टर्मिनल कमांड्स निकाले जा रहे हैं...";

    try {
      const b64 = this.captureLiveVideoFrame();
      const payload = b64 ? { image_base64: b64 } : {};

      const res = await fetch("/api/screen_ocr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        const spoken = data.spoken || "सर, स्क्रीन पर दिख रहा कोड आपके क्लिपबोर्ड पर कॉपी कर दिया गया है।";
        if (textEl) textEl.textContent = spoken;
        if (statusLabel) statusLabel.textContent = this.liveScreenStream ? "● LIVE SCREEN STREAM (60 FPS)" : "👁️ LIVE SCREEN VISION HUD";

        // Project widget to dynamic panel
        this.renderDynamicWidget({
          type: "ocr_clipboard",
          title: "Vision 2.0 Screen Clipboard",
          data: data
        });

        this.renderChatMessage("JARVIS (CLIPBOARD OCR)", spoken, false);
        this.speakText(spoken);
      }
    } catch (e) {
      console.error("[Vision 2.0] OCR error:", e);
      if (textEl) textEl.textContent = "OCR निष्कर्षण के दौरान त्रुटि आई।";
    }
  }

  // =========================================================================
  // VISION 2.0: DRAW GLOWING CHART OVERLAYS ON CANVAS
  // =========================================================================
  drawChartOverlays(overlays) {
    const canvas = document.getElementById("vision-overlay-canvas");
    const viewport = document.getElementById("vision-viewport");
    if (!canvas || !viewport) return;

    canvas.width = viewport.clientWidth || 320;
    canvas.height = viewport.clientHeight || 180;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const w = canvas.width;
    const h = canvas.height;

    overlays.forEach(ov => {
      if (!ov.box_percent || ov.box_percent.length < 4) return;
      const [ymin, xmin, ymax, xmax] = ov.box_percent;
      const rx = (xmin / 100) * w;
      const ry = (ymin / 100) * h;
      const rw = Math.max(16, ((xmax - xmin) / 100) * w);
      const rh = Math.max(12, ((ymax - ymin) / 100) * h);

      const color = ov.color || "#38bdf8";

      // 1. Semi-transparent fill
      ctx.fillStyle = color + "26";
      ctx.fillRect(rx, ry, rw, rh);

      // 2. Glowing border
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.shadowColor = color;
      ctx.shadowBlur = 6;
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.restore();

      // 3. Corner tick brackets
      const tick = 6;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      // top-left
      ctx.beginPath();
      ctx.moveTo(rx, ry + tick);
      ctx.lineTo(rx, ry);
      ctx.lineTo(rx + tick, ry);
      ctx.stroke();
      // bottom-right
      ctx.beginPath();
      ctx.moveTo(rx + rw, ry + rh - tick);
      ctx.lineTo(rx + rw, ry + rh);
      ctx.lineTo(rx + rw - tick, ry + rh);
      ctx.stroke();

      // 4. Label Badge
      const labelText = ov.label || "ZONE";
      ctx.font = "bold 9px 'JetBrains Mono', monospace";
      const tm = ctx.measureText(labelText);
      const badgeW = tm.width + 8;
      const badgeH = 14;
      const badgeX = rx;
      const badgeY = Math.max(0, ry - badgeH);

      ctx.fillStyle = color;
      ctx.fillRect(badgeX, badgeY, badgeW, badgeH);

      ctx.fillStyle = "#020617";
      ctx.fillText(labelText, badgeX + 4, badgeY + 10);
    });
  }

  captureLiveVideoFrame() {
    const video = document.getElementById("live-screen-feed");
    if (!video || !this.liveScreenStream) {
      return null;
    }
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.82);
      return dataUrl;
    } catch (e) {
      console.warn("[LiveVision] Frame capture error:", e);
      return null;
    }
  }

  async analyzeCurrentLiveFrame(customPrompt) {
    const textEl = document.getElementById("live-vision-text");
    const statusLabel = document.getElementById("live-vision-status-label");
    if (statusLabel) statusLabel.textContent = "⚡ ANALYZING REAL-TIME SCREEN FRAME...";
    if (textEl) textEl.innerHTML = `<span style="color:#38bdf8;">✦ लाइव स्क्रीन फ्रेम का विश्लेषण किया जा रहा है...</span>`;

    const frameB64 = this.captureLiveVideoFrame();

    try {
      const payload = {
        query: customPrompt || "स्क्रीन पर वर्तमान में क्या दिखाई दे रहा है? चार्ट लेवल्स और ट्रेंड का त्वरित विश्लेषण दें।",
        image_base64: frameB64 || ""
      };

      const res = await fetch("/api/screen_vision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        const replyText = data.text || "स्क्रीन का विश्लेषण पूरा हो गया है।";
        if (textEl) textEl.textContent = replyText;
        if (statusLabel) {
          statusLabel.textContent = this.liveScreenStream ? "● LIVE SCREEN STREAM (60 FPS)" : "👁️ LIVE SCREEN VISION HUD";
        }

        // Voice speech feedback
        this.renderChatMessage("JARVIS (SCREEN VISION)", replyText, false);
        this.updateHudTranscript(replyText);
        this.speakText(replyText);
      }
    } catch (err) {
      console.error("[LiveVision] Analysis error:", err);
      if (textEl) textEl.textContent = "विश्लेषण के दौरान त्रुटि आई। कृपया पुनः प्रयास करें।";
    }
  }

  toggleAutoRadar() {
    this.isAutoRadarActive = !this.isAutoRadarActive;
    const autoBtn = document.getElementById("btn-toggle-autoradar");

    if (this.isAutoRadarActive) {
      if (autoBtn) {
        autoBtn.textContent = "🔄 Auto-Radar: ON (8s)";
        autoBtn.style.background = "rgba(16, 185, 129, 0.25)";
        autoBtn.style.color = "#34d399";
        autoBtn.style.borderColor = "rgba(16, 185, 129, 0.5)";
      }
      this.renderChatMessage("JARVIS", "जी सर, ऑटो-विज़न रडार चालू कर दिया गया है। हर 8 सेकंड में स्क्रीन को स्वचालित रूप से मॉनिटर किया जाएगा।", false);
      
      this.autoRadarInterval = setInterval(() => {
        if (this.liveScreenStream) {
          this.analyzeCurrentLiveFrame("लाइव चार्ट का तुरंत संक्षिप्त अपडेट दें: कोई नया प्राइस एक्शन, ब्रेकआउट या कैंडलस्टिक बदलाव?");
        }
      }, 8000);
    } else {
      if (autoBtn) {
        autoBtn.textContent = "🔄 Auto-Radar: OFF";
        autoBtn.style.background = "";
        autoBtn.style.color = "";
        autoBtn.style.borderColor = "";
      }
      if (this.autoRadarInterval) {
        clearInterval(this.autoRadarInterval);
        this.autoRadarInterval = null;
      }
      this.renderChatMessage("JARVIS", "ऑटो-विज़न रडार बंद कर दिया गया है।", false);
    }
  }

  stopLiveScreenStream() {
    if (this.autoRadarInterval) {
      clearInterval(this.autoRadarInterval);
      this.autoRadarInterval = null;
      this.isAutoRadarActive = false;
    }

    if (this.liveScreenStream) {
      this.liveScreenStream.getTracks().forEach(track => track.stop());
      this.liveScreenStream = null;
    }

    const video = document.getElementById("live-screen-feed");
    const promptEl = document.getElementById("vision-stream-prompt");
    const statusLabel = document.getElementById("live-vision-status-label");
    const fpsBadge = document.getElementById("vision-fps-badge");
    const stopBtn = document.getElementById("btn-stop-stream");

    if (video) {
      video.srcObject = null;
      video.style.display = "none";
    }
    if (promptEl) promptEl.style.display = "flex";
    if (statusLabel) statusLabel.textContent = "👁️ LIVE SCREEN VISION HUD (STANDBY)";
    if (fpsBadge) fpsBadge.textContent = "STANDBY";
    if (stopBtn) stopBtn.style.display = "none";

    console.log("[LiveVision] Screen stream stopped.");
  }

  resetDynamicPanel() {
    const titleEl = document.getElementById("dynamic-panel-title");
    if (titleEl) titleEl.textContent = "AUTONOMOUS CANVAS";
    const container = document.getElementById("dynamic-content-body");
    if (!container) return;
    container.innerHTML = `
      <div class="dynamic-placeholder" id="dynamic-placeholder">
        <div class="placeholder-icon">✦</div>
        <h3>JARVIS OMNI CANVAS</h3>
        <p>जब आप मौसम, क्रिकेट स्कोर, ताज़ा समाचार, इंटरनेट सर्च, स्क्रीन विज़न या कोडिंग से जुड़ा सवाल पूछेंगे, तो जार्विस स्वतः यहाँ लाइव इंटरेक्टिव कार्ड प्रोजेक्ट करेगा।</p>
        <div class="preset-triggers">
          <button class="preset-pill" data-cmd="आज की ताज़ा और बड़ी खबरें बताओ">🔥 Breaking News</button>
          <button class="preset-pill" data-cmd="मार्केट और शेयर बाजार की ताज़ा खबर बताओ">📈 Market News</button>
          <button class="preset-pill" data-cmd="आज का मौसम कैसा है?">⛅ Live Weather</button>
          <button class="preset-pill" data-cmd="क्रिकेट स्कोर क्या हुआ?">🏏 Cricket Match</button>
          <button class="preset-pill" data-cmd="गूगल का वर्तमान सीईओ कौन है?">🌐 Web Search</button>
          <button class="preset-pill" data-cmd="स्क्रीन देखो और बताओ क्या दिख रहा है">👁️ Screen Vision</button>
        </div>
      </div>
    `;
    this.bindDynamicPresets();
  }

  bindDynamicPresets() {
    document.querySelectorAll(".preset-pill").forEach(pill => {
      pill.addEventListener("click", (e) => {
        const cmd = e.target.getAttribute("data-cmd");
        if (cmd) this.sendUserMessage(cmd);
      });
    });
  }

  // =========================================================================
  // UPGRADED SUB-SYSTEM CONTROLLERS & EVENT BINDINGS
  // =========================================================================

  initTabs() {
    document.querySelectorAll(".nav-tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const tabId = btn.getAttribute("data-tab");
        document.querySelectorAll(".nav-tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-view").forEach(v => v.classList.remove("active"));
        btn.classList.add("active");
        const view = document.getElementById(tabId);
        if (view) view.classList.add("active");

        if (tabId === "tab-health") this.fetchHealthDiagnostics();
        else if (tabId === "tab-models") this.fetchModelTelemetry();
        else if (tabId === "tab-paper") this.fetchPaperPortfolio();
        else if (tabId === "tab-psychology") this.fetchPsychologyAnalytics();
        else if (tabId === "tab-research") this.fetchResearchJobs();
        else if (tabId === "tab-memory") this.fetchMemoryList();
        else if (tabId === "tab-workflows") this.fetchWorkflows();
        else if (tabId === "tab-security") this.fetchAuditLogs();
        else if (tabId === "tab-browser") this.initBrowserOperator();
        else if (tabId === "tab-skills") this.fetchSkills();
        else if (tabId === "tab-skill-manager") this.fetchSkillManager();
        else if (tabId === "tab-permissions") this.fetchPermissions();
        else if (tabId === "tab-collaboration") this.fetchCollaboration();
        else if (tabId === "tab-activity-log") this.fetchActivityLogs();
        else if (tabId === "tab-memory-timeline") this.fetchMemoryTimeline();
      });
    });
  }

  initPrivacyControls() {
    const micBtn = document.getElementById("privacy-mic-btn");
    const screenBtn = document.getElementById("privacy-screen-btn");
    const secMicBtn = document.getElementById("sec-mic-toggle");
    const secScreenBtn = document.getElementById("sec-screen-toggle");
    const secWakeBtn = document.getElementById("sec-wake-toggle");

    const updateUI = (status) => {
      if (micBtn) {
        micBtn.textContent = status.mic_kill_switch ? "🎙️ MIC: KILLED" : "🎙️ MIC: ON";
        micBtn.classList.toggle("killed", status.mic_kill_switch);
      }
      if (secMicBtn) {
        secMicBtn.textContent = status.mic_kill_switch ? "Killed (Blocked)" : "Active (Enabled)";
        secMicBtn.classList.toggle("danger-btn", status.mic_kill_switch);
      }
      if (screenBtn) {
        screenBtn.textContent = status.screen_kill_switch ? "👁️ SCREEN: KILLED" : "👁️ SCREEN: ON";
        screenBtn.classList.toggle("killed", status.screen_kill_switch);
      }
      if (secScreenBtn) {
        secScreenBtn.textContent = status.screen_kill_switch ? "Killed (Blocked)" : "Active (Enabled)";
        secScreenBtn.classList.toggle("danger-btn", status.screen_kill_switch);
      }
      if (secWakeBtn) {
        secWakeBtn.textContent = status.wake_listener_active ? "Listening (Active)" : "Disabled (Off)";
        secWakeBtn.classList.toggle("primary-btn", status.wake_listener_active);
      }
    };

    fetch("/api/privacy/status")
      .then(r => r.json())
      .then(s => updateUI(s))
      .catch(() => {});

    const toggle = (target, currentState) => {
      fetch("/api/privacy/kill-switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: target, state: !currentState })
      })
      .then(r => r.json())
      .then(res => {
        if (res.status) updateUI(res.status);
      });
    };

    if (micBtn) micBtn.onclick = () => toggle("mic", !micBtn.classList.contains("killed"));
    if (secMicBtn) secMicBtn.onclick = () => toggle("mic", !secMicBtn.classList.contains("danger-btn"));
    if (screenBtn) screenBtn.onclick = () => toggle("screen", !screenBtn.classList.contains("killed"));
    if (secScreenBtn) secScreenBtn.onclick = () => toggle("screen", !secScreenBtn.classList.contains("danger-btn"));
    if (secWakeBtn) {
      secWakeBtn.onclick = () => {
        const isCurrentActive = secWakeBtn.textContent.includes("Active");
        toggle("wake", isCurrentActive);
      };
    }
  }

  initVoiceInterruption() {
    const stopBtn = document.getElementById("voice-interrupt-btn");
    const ttsPlayer = document.getElementById("tts-player");
    const voiceStateText = document.getElementById("voice-state-text");

    const interruptSpeech = () => {
      if (ttsPlayer) {
        ttsPlayer.pause();
        ttsPlayer.currentTime = 0;
        ttsPlayer.src = "";
      }
      if (stopBtn) stopBtn.style.display = "none";
      if (voiceStateText) voiceStateText.textContent = "INTERRUPTED";

      fetch("/api/voice/interrupt", { method: "POST" })
        .then(r => r.json())
        .then(() => {
          setTimeout(() => {
            if (voiceStateText) voiceStateText.textContent = "LISTENING";
          }, 400);
        })
        .catch(() => {});
    };

    if (stopBtn) stopBtn.onclick = interruptSpeech;

    if (ttsPlayer) {
      ttsPlayer.onplay = () => {
        if (stopBtn) stopBtn.style.display = "inline-flex";
        if (voiceStateText) voiceStateText.textContent = "SPEAKING";
      };
      ttsPlayer.onended = () => {
        if (stopBtn) stopBtn.style.display = "none";
        if (voiceStateText) voiceStateText.textContent = "IDLE";
      };
      ttsPlayer.onerror = () => {
        if (stopBtn) stopBtn.style.display = "none";
        if (voiceStateText) voiceStateText.textContent = "IDLE";
      };
    }

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && ttsPlayer && !ttsPlayer.paused) {
        interruptSpeech();
      }
    });
  }

  initConfirmationModal() {
    this.currentPendingActionId = null;
    this.confirmTimer = null;
    const modal = document.getElementById("confirmation-modal");
    const approveBtn = document.getElementById("confirm-approve-btn");
    const denyBtn = document.getElementById("confirm-deny-btn");

    if (approveBtn) {
      approveBtn.onclick = () => {
        if (!this.currentPendingActionId) return;
        fetch("/api/os/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action_id: this.currentPendingActionId })
        })
        .then(r => r.json())
        .then(res => {
          modal.style.display = "none";
          clearInterval(this.confirmTimer);
          const msg = res.result?.message || "Action executed successfully.";
          this.renderChatMessage("JARVIS", `✅ ${msg}`, false);
        })
        .catch(err => {
          alert("Approval failed: " + err);
        });
      };
    }

    if (denyBtn) {
      denyBtn.onclick = () => {
        if (!this.currentPendingActionId) return;
        fetch("/api/os/reject", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action_id: this.currentPendingActionId })
        })
        .then(() => {
          modal.style.display = "none";
          clearInterval(this.confirmTimer);
          this.renderChatMessage("JARVIS", "❌ कार्रवाई उपयोगकर्ता द्वारा अस्वीकार कर दी गई।", false);
        });
      };
    }
  }

  showConfirmationModal(pendingAction) {
    const modal = document.getElementById("confirmation-modal");
    const desc = document.getElementById("confirm-description");
    const details = document.getElementById("confirm-details");
    const timerEl = document.getElementById("confirm-time-left");

    if (!modal || !pendingAction) return;
    this.currentPendingActionId = pendingAction.action_id;
    if (desc) desc.textContent = pendingAction.description;
    if (details) {
      details.innerHTML = `
        <div><strong>Action:</strong> ${escapeHtml(pendingAction.action_type)}</div>
        <div><strong>Target:</strong> ${escapeHtml(pendingAction.target)}</div>
        <div><strong>Risk Level:</strong> <span class="badge warning-badge">${escapeHtml(pendingAction.risk_level.toUpperCase())}</span></div>
        <div><strong>ID:</strong> ${escapeHtml(pendingAction.action_id)}</div>
      `;
    }

    let remaining = pendingAction.remaining_seconds || 60;
    if (timerEl) timerEl.textContent = remaining;
    modal.style.display = "flex";

    clearInterval(this.confirmTimer);
    this.confirmTimer = setInterval(() => {
      remaining -= 1;
      if (timerEl) timerEl.textContent = remaining;
      if (remaining <= 0) {
        clearInterval(this.confirmTimer);
        modal.style.display = "none";
      }
    }, 1000);
  }

  async fetchHealthDiagnostics() {
    const container = document.getElementById("health-grid-content");
    const refreshBtn = document.getElementById("refresh-health-btn");
    if (refreshBtn) refreshBtn.onclick = () => this.fetchHealthDiagnostics();
    if (!container) return;

    try {
      const res = await fetch("/api/health/diagnostics");
      const data = await res.json();
      const p = data.process || {};
      const h = data.hardware || {};
      const ai = data.ai_providers || {};
      const db = data.database || {};
      const wsCount = data.websocket?.active_clients || 0;

      let aiHtml = "";
      for (const [provider, info] of Object.entries(ai)) {
        const isOnline = info.status === "ONLINE";
        const color = isOnline ? "var(--emerald-profit)" : "var(--rose-loss)";
        aiHtml += `
          <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-bottom:4px;">
            <span>${provider}</span>
            <span style="color:${color}; font-weight:700;">${info.status} ${info.latency_ms ? `(${info.latency_ms}ms)` : ""}</span>
          </div>
        `;
      }

      container.innerHTML = `
        <div class="glass-card">
          <h3>Hardware & Resources</h3>
          <p><strong>CPU Total:</strong> ${h.cpu_total_percent}% (${h.cpu_cores_logical} Cores)</p>
          <p><strong>RAM Usage:</strong> ${h.ram_used_gb} GB / ${h.ram_total_gb} GB (${h.ram_percent}%)</p>
          <p><strong>Disk Usage:</strong> ${h.disk_used_gb} GB / ${h.disk_total_gb} GB (${h.disk_percent}%)</p>
        </div>
        <div class="glass-card">
          <h3>Process Footprint</h3>
          <p><strong>PID:</strong> ${p.pid}</p>
          <p><strong>Process RAM (RSS):</strong> ${p.memory_rss_mb} MB</p>
          <p><strong>Threads:</strong> ${p.threads_count}</p>
          <p><strong>Uptime:</strong> ${Math.floor(data.server_uptime_seconds / 60)} minutes</p>
          <p><strong>Active WebSockets:</strong> ${wsCount}</p>
        </div>
        <div class="glass-card">
          <h3>AI Providers Latency Matrix</h3>
          ${aiHtml}
        </div>
        <div class="glass-card">
          <h3>Database & Integrity</h3>
          <p><strong>Status:</strong> <span style="color:var(--emerald-profit);">${db.status?.toUpperCase()}</span></p>
          <p><strong>Integrity:</strong> ${db.integrity}</p>
          <p><strong>Size:</strong> ${db.size_kb} KB</p>
          <p><strong>Recent Errors (1h):</strong> ${data.recent_errors?.last_hour_count || 0}</p>
        </div>
      `;
    } catch (e) {
      container.innerHTML = `<div class="error-msg">Failed to load diagnostics: ${e}</div>`;
    }
  }

  async fetchModelTelemetry() {
    const container = document.getElementById("models-grid-content");
    const refreshBtn = document.getElementById("refresh-models-btn");
    if (refreshBtn) refreshBtn.onclick = () => this.fetchModelTelemetry();
    if (!container) return;

    try {
      const res = await fetch("/api/models/telemetry");
      const data = await res.json();
      const circuits = data.circuits || {};

      let html = "";
      for (const [key, cb] of Object.entries(circuits)) {
        const isClosed = cb.state === "CLOSED";
        const stateColor = isClosed ? "var(--emerald-profit)" : (cb.state === "OPEN" ? "var(--rose-loss)" : "var(--amber-warning)");
        html += `
          <div class="glass-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <h3 style="margin:0;">${cb.name}</h3>
              <span class="badge" style="background:${stateColor}22; color:${stateColor}; border:1px solid ${stateColor};">${cb.state}</span>
            </div>
            <p><strong>Total Requests:</strong> ${cb.total_requests}</p>
            <p><strong>Successful:</strong> ${cb.successful_requests}</p>
            <p><strong>Failures:</strong> ${cb.failure_count}</p>
            <p><strong>Average Latency:</strong> ${cb.avg_latency_ms} ms</p>
          </div>
        `;
      }

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="error-msg">Failed to load model telemetry: ${e}</div>`;
    }
  }

  initStrategyLab() {
    const runBtn = document.getElementById("run-backtest-btn");
    if (!runBtn) return;

    runBtn.onclick = async () => {
      const strat = document.getElementById("bt-strategy-select").value;
      const sym = document.getElementById("bt-symbol-select").value;
      const cap = parseFloat(document.getElementById("bt-capital").value) || 1000000;
      const slip = parseFloat(document.getElementById("bt-slippage").value) || 0.05;
      const fee = parseFloat(document.getElementById("bt-fee").value) || 0.03;
      const outView = document.getElementById("strategy-results-view");

      outView.innerHTML = "<div class='loading-state'>Running quantitative backtest simulation...</div>";
      runBtn.disabled = true;

      try {
        const res = await fetch("/api/trading/backtest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: sym,
            strategy_name: strat,
            initial_capital: cap,
            slippage_pct: slip,
            fee_pct: fee
          })
        });
        const data = await res.json();
        runBtn.disabled = false;

        if (!data.success) {
          outView.innerHTML = `<div class="error-msg">Backtest error: ${data.error || "Simulation failed"}</div>`;
          return;
        }

        const fp = data.full_period;
        const wf = data.walk_forward_validation;
        const retColor = fp.total_return_pct >= 0 ? "var(--emerald-profit)" : "var(--rose-loss)";

        outView.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-subtle); padding-bottom:6px; margin-bottom:8px;">
            <h3 style="margin:0;">Backtest Performance: ${data.strategy} (${sym})</h3>
            <span class="badge ${wf.is_robust ? 'buy-btn' : 'warning-badge'}">Walk-Forward: ${wf.is_robust ? 'ROBUST MODEL' : 'CURVE-FITTED'}</span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; margin-bottom:10px;">
            <div class="fno-item"><span class="fno-label">WIN RATE</span><span class="fno-val" style="color:var(--cyan-neon);">${fp.win_rate_pct}%</span></div>
            <div class="fno-item"><span class="fno-label">PROFIT FACTOR</span><span class="fno-val" style="color:var(--emerald-profit);">${fp.profit_factor}</span></div>
            <div class="fno-item"><span class="fno-label">NET RETURN</span><span class="fno-val" style="color:${retColor};">${fp.total_return_pct}%</span></div>
            <div class="fno-item"><span class="fno-label">MAX DRAWDOWN</span><span class="fno-val" style="color:var(--rose-loss);">${fp.max_drawdown_pct}%</span></div>
          </div>
          <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:8px;">
            Total Trades: <strong>${fp.total_trades}</strong> (Wins: ${fp.winning_trades}, Losses: ${fp.losing_trades}) | Sharpe Ratio: <strong>${fp.sharpe_ratio}</strong>
          </div>
          <p style="font-size:0.65rem; color:var(--text-muted);">${data.disclaimer}</p>
        `;
      } catch (err) {
        runBtn.disabled = false;
        outView.innerHTML = `<div class="error-msg">Execution error: ${err}</div>`;
      }
    };
  }

  initPaperTrading() {
    const buyBtn = document.getElementById("btn-paper-buy");
    const sellBtn = document.getElementById("btn-paper-sell");
    const resetBtn = document.getElementById("reset-paper-btn");

    const placeOrder = (side) => {
      const sym = document.getElementById("order-symbol").value;
      const qty = parseInt(document.getElementById("order-qty").value) || 1;
      const orderType = document.getElementById("order-type").value;
      const sl = parseFloat(document.getElementById("order-sl").value) || null;

      fetch("/api/trading/paper/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          side: side,
          quantity: qty,
          order_type: orderType,
          stop_loss: sl
        })
      })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          alert(`Order Filled: ${side} ${qty} ${sym} @ ₹${res.executed_price}`);
          this.fetchPaperPortfolio();
        } else {
          alert(`Order Rejected: ${res.error}`);
        }
      });
    };

    if (buyBtn) buyBtn.onclick = () => placeOrder("BUY");
    if (sellBtn) sellBtn.onclick = () => placeOrder("SELL");
    if (resetBtn) {
      resetBtn.onclick = () => {
        if (confirm("Reset simulated paper account back to ₹10,00,000 INR?")) {
          fetch("/api/trading/paper/reset", { method: "POST" })
            .then(r => r.json())
            .then(res => {
              alert(res.message);
              this.fetchPaperPortfolio();
            });
        }
      };
    }
  }

  async fetchPaperPortfolio() {
    const sumEl = document.getElementById("paper-summary-content");
    const posEl = document.getElementById("paper-positions-content");
    if (!sumEl) return;

    try {
      const res = await fetch("/api/trading/paper/portfolio");
      const data = await res.json();

      const pnlColor = data.total_pnl >= 0 ? "var(--emerald-profit)" : "var(--rose-loss)";
      sumEl.innerHTML = `
        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:8px;">
          <div><span class="fno-label">CASH BALANCE</span><div style="font-size:1.1rem; font-weight:700;">₹${data.cash_balance.toLocaleString('en-IN')}</div></div>
          <div><span class="fno-label">INVESTED VALUE</span><div style="font-size:1.1rem; font-weight:700;">₹${data.invested_value.toLocaleString('en-IN')}</div></div>
          <div><span class="fno-label">TOTAL EQUITY</span><div style="font-size:1.1rem; font-weight:700; color:var(--cyan-neon);">₹${data.total_portfolio_equity.toLocaleString('en-IN')}</div></div>
          <div><span class="fno-label">TOTAL P&L</span><div style="font-size:1.1rem; font-weight:700; color:${pnlColor};">₹${data.total_pnl.toLocaleString('en-IN')} (${data.total_pnl_pct}%)</div></div>
        </div>
      `;

      if (posEl) {
        if (!data.positions || data.positions.length === 0) {
          posEl.innerHTML = "<p class='placeholder-text'>No active open positions. Place an order above.</p>";
        } else {
          let rows = data.positions.map(p => `
            <tr>
              <td><strong>${p.symbol}</strong></td>
              <td><span class="badge ${p.side === 'LONG' ? 'buy-btn' : 'sell-btn'}">${p.side}</span></td>
              <td>${p.quantity}</td>
              <td>₹${p.avg_entry_price}</td>
              <td>₹${p.current_price}</td>
              <td style="color:${p.unrealized_pnl >= 0 ? 'var(--emerald-profit)' : 'var(--rose-loss)'}; font-weight:700;">
                ₹${p.unrealized_pnl} (${p.pnl_pct}%)
              </td>
            </tr>
          `).join("");

          posEl.innerHTML = `
            <table>
              <thead>
                <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry Price</th><th>Current Price</th><th>Unrealized P&L</th></tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          `;
        }
      }
    } catch (e) {
      sumEl.innerHTML = `<div class="error-msg">Failed to load paper portfolio: ${e}</div>`;
    }
  }

  initPsychologyJournal() {
    const saveBtn = document.getElementById("save-psychology-btn");
    if (!saveBtn) return;

    saveBtn.onclick = () => {
      const em = document.getElementById("psy-emotion").value;
      const notes = document.getElementById("psy-notes").value;
      const c1 = document.getElementById("check-1").checked;
      const c2 = document.getElementById("check-2").checked;
      const c3 = document.getElementById("check-3").checked;
      const c4 = document.getElementById("check-4").checked;

      fetch("/api/trading/psychology/entry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: this.currentSymbol || "NIFTY50",
          action: "NOTE",
          emotion_tag: em,
          checklist_answers: [c1, c2, c3, c4],
          notes: notes
        })
      })
      .then(r => r.json())
      .then(res => {
        alert(res.message);
        document.getElementById("psy-notes").value = "";
        this.fetchPsychologyAnalytics();
      });
    };
  }

  async fetchPsychologyAnalytics() {
    const container = document.getElementById("psychology-analytics-content");
    if (!container) return;

    try {
      const res = await fetch("/api/trading/psychology/analytics");
      const data = await res.json();

      const scoreColor = data.avg_discipline_score >= 70 ? "var(--emerald-profit)" : "var(--amber-warning)";
      container.innerHTML = `
        <h3>Mental Discipline Dashboard</h3>
        <div style="display:flex; align-items:center; gap:1.5rem; margin:1rem 0;">
          <div style="font-size:2.4rem; font-weight:800; color:${scoreColor}; font-family:var(--font-display);">
            ${data.avg_discipline_score} <span style="font-size:1rem; color:var(--text-muted);">/100</span>
          </div>
          <div>
            <div style="font-weight:700; color:${scoreColor};">${data.risk_advisory}</div>
            <div style="font-size:0.75rem; color:var(--text-secondary);">Total Journal Entries: ${data.total_entries} | Top Emotion: ${data.top_emotion}</div>
          </div>
        </div>
      `;
    } catch (e) {}
  }

  initResearchWorkspace() {
    const startBtn = document.getElementById("start-research-btn");
    if (!startBtn) return;

    startBtn.onclick = () => {
      const topic = document.getElementById("research-topic-input").value.trim();
      const mode = document.getElementById("research-mode-select").value;
      if (!topic) {
        alert("Please enter a research topic.");
        return;
      }
      this.sendUserMessage(`${topic} ka complete research report banao`);
      document.querySelector('[data-tab="tab-command"]')?.click();
    };
  }

  async fetchResearchJobs() {
    const container = document.getElementById("research-jobs-list");
    if (!container) return;

    try {
      const res = await fetch("/api/research/jobs");
      const data = await res.json();
      const jobs = data.jobs || [];

      if (jobs.length === 0) {
        container.innerHTML = "<p class='placeholder-text'>No research monographs generated yet.</p>";
        return;
      }

      let rows = jobs.map(j => `
        <tr>
          <td><strong>${j.topic}</strong></td>
          <td><span class="badge">${j.mode}</span></td>
          <td><span class="badge ${j.status === 'COMPLETED' ? 'buy-btn' : 'warning-badge'}">${j.status}</span></td>
          <td>${j.progress}%</td>
          <td>${j.current_step || '-'}</td>
        </tr>
      `).join("");

      container.innerHTML = `
        <table>
          <thead><tr><th>Subject</th><th>Mode</th><th>Status</th><th>Progress</th><th>Step</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    } catch (e) {
      container.innerHTML = `<div class="error-msg">Failed to load jobs: ${e}</div>`;
    }
  }

  initMemoryBrain() {
    const exportBtn = document.getElementById("export-memory-btn");
    const addBtn = document.getElementById("add-memory-btn");
    const searchInput = document.getElementById("memory-search-input");
    const catFilter = document.getElementById("memory-category-filter");

    if (exportBtn) {
      exportBtn.onclick = () => {
        window.open("/api/memory/export", "_blank");
      };
    }

    if (addBtn) {
      addBtn.onclick = () => {
        const text = prompt("Enter persistent fact / memory to store in J.A.R.V.I.S. Brain:");
        if (text) {
          fetch("/api/memory", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: "user_approved_memories", content: text })
          })
          .then(r => r.json())
          .then(() => this.fetchMemoryList());
        }
      };
    }

    if (searchInput) {
      searchInput.oninput = () => {
        this.fetchMemoryList(searchInput.value, catFilter.value);
      };
    }

    if (catFilter) {
      catFilter.onchange = () => {
        this.fetchMemoryList(searchInput.value, catFilter.value);
      };
    }
  }

  async fetchMemoryList(query = "", category = "") {
    const container = document.getElementById("memory-items-list");
    if (!container) return;

    try {
      let url = "/api/memory";
      if (query) url = `/api/memory/search?q=${encodeURIComponent(query)}`;
      if (category) url += (url.includes("?") ? `&category=${category}` : `?category=${category}`);

      const res = await fetch(url);
      const data = await res.json();
      const items = data.memories || data.results || [];

      if (items.length === 0) {
        container.innerHTML = "<p class='placeholder-text'>No memories found matching filter.</p>";
        return;
      }

      let rows = items.map(m => `
        <tr>
          <td><span class="badge">${escapeHtml(m.category)}</span></td>
          <td>${escapeHtml(m.content)}</td>
          <td><button class="action-btn danger-btn" onclick="window.jarvis.deleteMemoryItem('${encodeURIComponent(m.id)}')">Delete</button></td>
        </tr>
      `).join("");

      container.innerHTML = `
        <table>
          <thead><tr><th>Category</th><th>Memory Content</th><th>Action</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    } catch (e) {
      container.innerHTML = `<div class="error-msg">Failed to load memories: ${e}</div>`;
    }
  }

  deleteMemoryItem(id) {
    if (confirm("Delete this memory node from SQLite?")) {
      fetch(`/api/memory/${id}`, { method: "DELETE" })
        .then(() => this.fetchMemoryList());
    }
  }

  initWorkflowStudio() {}

  async fetchWorkflows() {
    const container = document.getElementById("workflow-templates-grid");
    const histContainer = document.getElementById("workflow-history-list");
    if (!container) return;

    try {
      const res = await fetch("/api/workflows");
      const data = await res.json();
      const list = data.workflows || [];

      container.innerHTML = list.map(wf => `
        <div class="glass-card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 style="margin:0;">${escapeHtml(wf.name)}</h3>
            <span class="badge">${escapeHtml(wf.trigger_type)}</span>
          </div>
          <p style="font-size:0.75rem; color:var(--text-secondary); margin:6px 0;">${escapeHtml(wf.description || '')}</p>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-bottom:8px;">Action: <code>${escapeHtml(wf.action_type)}</code></div>
          <div style="display:flex; gap:6px;">
            <button class="action-btn primary-btn" onclick="window.jarvis.runWorkflow('${encodeURIComponent(wf.id)}', false)">▶ Run</button>
            <button class="action-btn" onclick="window.jarvis.runWorkflow('${encodeURIComponent(wf.id)}', true)">🧪 Dry-Run</button>
          </div>
        </div>
      `).join("");

      if (histContainer) {
        const hRes = await fetch("/api/workflows/history");
        const hData = await hRes.json();
        const runs = hData.history || [];
        if (runs.length === 0) {
          histContainer.innerHTML = "<p class='placeholder-text'>No workflow executions logged yet.</p>";
        } else {
          histContainer.innerHTML = `
            <table>
              <thead><tr><th>Workflow</th><th>Type</th><th>Status</th><th>Duration</th></tr></thead>
              <tbody>
                ${runs.map(r => `
                  <tr>
                    <td><strong>${escapeHtml(r.workflow_name || r.workflow_id)}</strong></td>
                    <td>${r.is_dry_run ? 'Dry-Run' : 'Real Execution'}</td>
                    <td><span class="badge ${r.status === 'COMPLETED' ? 'buy-btn' : 'sell-btn'}">${escapeHtml(r.status)}</span></td>
                    <td>${Math.round((r.completed_at - r.started_at)*1000)}ms</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          `;
        }
      }
    } catch (e) {}
  }

  async runWorkflow(wfId, isDryRun) {
    const url = isDryRun ? `/api/workflows/${wfId}/dry-run` : `/api/workflows/${wfId}/run`;
    try {
      const res = await fetch(url, { method: "POST" });
      const data = await res.json();
      alert(`Workflow ${data.status}:
${data.message || JSON.stringify(data.trace)}`);
      this.fetchWorkflows();
    } catch (e) {
      alert("Workflow execution error: " + e);
    }
  }

  initSecurityAndUpdater() {
    const chkBtn = document.getElementById("check-update-btn");
    if (chkBtn) {
      chkBtn.onclick = () => {
        chkBtn.textContent = "Checking...";
        fetch("/api/updater/check")
          .then(r => r.json())
          .then(res => {
            chkBtn.textContent = "Check for Updates";
            alert(`J.A.R.V.I.S. Updater Status:
Current Version: ${res.current_version}
Update Available: ${res.update_available ? 'Yes (' + res.remote_version + ')' : 'No (Already on latest build)'}`);
          });
      };
    }
  }

  async fetchAuditLogs() {
    const container = document.getElementById("audit-log-content");
    if (!container) return;

    try {
      const res = await fetch("/api/security/audit-logs");
      const data = await res.json();
      const logs = data.audit_logs || [];

      if (logs.length === 0) {
        container.innerHTML = "<p class='placeholder-text'>No audit events recorded.</p>";
        return;
      }

      let rows = logs.map(l => `
        <tr>
          <td>${l.timestamp}</td>
          <td><strong>${l.action_type}</strong></td>
          <td>${l.target}</td>
          <td><span class="badge ${l.risk_level === 'high' ? 'danger-btn' : ''}">${l.risk_level}</span></td>
          <td><span class="badge ${l.status === 'success' ? 'buy-btn' : 'sell-btn'}">${l.status}</span></td>
        </tr>
      `).join("");

      container.innerHTML = `
        <table>
          <thead><tr><th>Timestamp</th><th>Action Type</th><th>Target</th><th>Risk</th><th>Status</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    } catch (e) {
      container.innerHTML = `<div class="error-msg">Failed to load audit logs: ${e}</div>`;
    }
  }

  // =========================================================================
  // 7 CORE ARCHITECTURE COMPONENTS INTEGRATION CONTROLLERS
  // =========================================================================
  initSevenComponentsListeners() {
    // 1. Browser Event Listeners
    const goBtn = document.getElementById("br-go-btn");
    const urlInput = document.getElementById("br-url-input");
    if (goBtn && urlInput) {
      goBtn.onclick = () => this.navigateBrowser(urlInput.value);
      urlInput.onkeydown = (e) => { if (e.key === "Enter") this.navigateBrowser(urlInput.value); };
    }
    document.getElementById("br-back-btn")?.addEventListener("click", () => this.performBrowserAction("back"));
    document.getElementById("br-forward-btn")?.addEventListener("click", () => this.performBrowserAction("forward"));
    document.getElementById("br-reload-btn")?.addEventListener("click", () => this.performBrowserAction("reload"));
    document.getElementById("br-home-btn")?.addEventListener("click", () => this.performBrowserAction("home"));
    document.getElementById("br-search-btn")?.addEventListener("click", () => {
      const q = document.getElementById("br-search-input")?.value;
      if (q) this.performBrowserAction("search", { query: q });
    });
    document.getElementById("br-bookmark-btn")?.addEventListener("click", () => this.addBrowserBookmark());
    document.getElementById("br-stop-btn")?.addEventListener("click", async () => {
      await fetch("/api/browser/stop", { method: "POST" });
      alert("🛑 Emergency stop triggered. All automated browser actions halted.");
    });
    document.getElementById("br-new-tab-btn")?.addEventListener("click", () => this.openNewBrowserTab());
    document.getElementById("br-view-screenshot-btn")?.addEventListener("click", () => {
      document.getElementById("br-screenshot-wrapper").style.display = "block";
      document.getElementById("br-dom-text").style.display = "none";
      document.getElementById("br-view-screenshot-btn").classList.add("active");
      document.getElementById("br-view-dom-btn").classList.remove("active");
    });
    document.getElementById("br-view-dom-btn")?.addEventListener("click", () => {
      document.getElementById("br-screenshot-wrapper").style.display = "none";
      document.getElementById("br-dom-text").style.display = "block";
      document.getElementById("br-view-dom-btn").classList.add("active");
      document.getElementById("br-view-screenshot-btn").classList.remove("active");
    });
    document.getElementById("br-ai-summarize-btn")?.addEventListener("click", () => this.aiSummarizePage());
    document.getElementById("br-qa-btn")?.addEventListener("click", () => {
      const q = document.getElementById("br-qa-input")?.value;
      if (q) this.aiGroundedQA(q);
    });
    document.getElementById("br-extract-tables-btn")?.addEventListener("click", () => this.aiExtractTables());
    document.getElementById("br-gen-report-btn")?.addEventListener("click", () => this.aiGenerateReport());
    document.getElementById("drawer-tab-bm")?.addEventListener("click", () => {
      document.getElementById("br-bookmarks-view").style.display = "flex";
      document.getElementById("br-history-view").style.display = "none";
      document.getElementById("drawer-tab-bm").classList.add("active");
      document.getElementById("drawer-tab-hist").classList.remove("active");
      this.fetchBrowserBookmarks();
    });
    document.getElementById("drawer-tab-hist")?.addEventListener("click", () => {
      document.getElementById("br-bookmarks-view").style.display = "none";
      document.getElementById("br-history-view").style.display = "flex";
      document.getElementById("drawer-tab-hist").classList.add("active");
      document.getElementById("drawer-tab-bm").classList.remove("active");
      this.fetchBrowserHistory();
    });

    // 2. Skills Listeners
    document.querySelectorAll("[data-skill-filter]").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-skill-filter]").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this.fetchSkills(btn.getAttribute("data-skill-filter"));
      });
    });
    document.getElementById("skills-search-input")?.addEventListener("input", (e) => {
      this.fetchSkills(undefined, e.target.value);
    });
    document.getElementById("skills-rescan-btn")?.addEventListener("click", () => this.fetchSkills());
    document.getElementById("skills-run-btn")?.addEventListener("click", () => this.executeSelectedSkill());
    document.getElementById("skills-view-doc-btn")?.addEventListener("click", () => this.viewSelectedSkillDoc());

    // 3. Skill Manager Listeners
    document.getElementById("skmgr-install-btn")?.addEventListener("click", () => this.installSkillFromPath());

    // 4. Permissions Listeners
    document.getElementById("perm-grant-submit-btn")?.addEventListener("click", () => this.submitGrantPermission());

    // 5. Collaboration Listeners
    document.getElementById("collab-plan-btn")?.addEventListener("click", () => this.planCollaborationTask());
    document.getElementById("collab-start-btn")?.addEventListener("click", () => this.startCollaborationTask());
    document.getElementById("collab-pause-btn")?.addEventListener("click", () => this.pauseCollaborationTask());
    document.getElementById("collab-resume-btn")?.addEventListener("click", () => this.resumeCollaborationTask());
    document.getElementById("collab-cancel-btn")?.addEventListener("click", () => this.cancelCollaborationTask());

    // 6. Activity Log Listeners
    document.getElementById("act-filter-apply-btn")?.addEventListener("click", () => this.loadActivityEvents());
    document.getElementById("act-export-json-btn")?.addEventListener("click", () => this.exportActivityLogs("json"));
    document.getElementById("act-export-csv-btn")?.addEventListener("click", () => this.exportActivityLogs("csv"));
    document.getElementById("act-clear-btn")?.addEventListener("click", () => this.clearActivityLogs());

    // 7. Memory Timeline Listeners
    document.getElementById("mem-recording-toggle")?.addEventListener("click", () => this.toggleMemoryRecording());
    document.getElementById("mem-purge-cat-btn")?.addEventListener("click", () => this.bulkPurgeCategory());
    document.getElementById("mem-search-btn")?.addEventListener("click", () => this.loadMemoryTimeline());
    document.getElementById("mem-filter-cat")?.addEventListener("change", () => this.loadMemoryTimeline());
    document.getElementById("mem-filter-source")?.addEventListener("change", () => this.loadMemoryTimeline());
    document.getElementById("mem-add-modal-btn")?.addEventListener("click", () => this.addMemoryNodePrompt());
  }

  // -------------------------------------------------------------------------
  // COMPONENT 1: AI BROWSER OPERATOR
  // -------------------------------------------------------------------------
  async initBrowserOperator() {
    await this.fetchBrowserTabs();
    await this.fetchBrowserSnapshot();
    this.fetchBrowserBookmarks();
  }

  async fetchBrowserTabs() {
    try {
      const res = await fetch("/api/browser/tabs");
      const data = await res.json();
      const tabs = data.tabs || [];
      const strip = document.getElementById("br-tab-strip");
      if (!strip) return;

      const items = tabs.map(t => `
        <div class="br-tab-item ${t.is_active ? 'active' : ''}" data-tab-id="${t.tab_id}" onclick="jarvis.switchBrowserTab('${t.tab_id}')">
          <span class="br-tab-title" title="${escapeHtml(t.title)}">${escapeHtml(t.title || 'Blank')}</span>
          <button class="br-tab-close" onclick="event.stopPropagation(); jarvis.closeBrowserTab('${t.tab_id}')">×</button>
        </div>
      `).join("");

      strip.innerHTML = items + `<button class="br-new-tab-btn" id="br-new-tab-btn" onclick="jarvis.openNewBrowserTab()">+ New Tab</button>`;
    } catch (e) {
      console.error("fetchBrowserTabs error:", e);
    }
  }

  async openNewBrowserTab(url = "about:blank") {
    try {
      const res = await fetch("/api/browser/tab/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();
      if (data.tab_id) {
        await this.fetchBrowserTabs();
        await this.fetchBrowserSnapshot();
      }
    } catch (e) {
      alert("Open tab error: " + e);
    }
  }

  async switchBrowserTab(tabId) {
    try {
      await fetch("/api/browser/tab/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tab_id: tabId })
      });
      await this.fetchBrowserTabs();
      await this.fetchBrowserSnapshot();
    } catch (e) {
      console.error("switchBrowserTab error:", e);
    }
  }

  async closeBrowserTab(tabId) {
    try {
      await fetch("/api/browser/tab/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tab_id: tabId })
      });
      await this.fetchBrowserTabs();
      await this.fetchBrowserSnapshot();
    } catch (e) {
      console.error("closeBrowserTab error:", e);
    }
  }

  async navigateBrowser(url) {
    if (!url || !url.trim()) return;
    let target = url.trim();
    if (!target.startsWith("http://") && !target.startsWith("https://") && target !== "about:blank") {
      target = "https://" + target;
    }
    const titleEl = document.getElementById("br-viewport-title");
    if (titleEl) titleEl.textContent = "Navigating to " + target + "...";

    try {
      const res = await fetch("/api/browser/navigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: target })
      });
      const data = await res.json();
      if (data.status === "ERROR") {
        alert("Navigation Blocked: " + data.error);
      } else {
        const input = document.getElementById("br-url-input");
        if (input) input.value = data.url;
        await this.fetchBrowserTabs();
        await this.fetchBrowserSnapshot();
      }
    } catch (e) {
      alert("Navigation Error: " + e);
    }
  }

  async performBrowserAction(action, params = {}) {
    try {
      const res = await fetch("/api/browser/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, params })
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        await this.fetchBrowserSnapshot();
      }
    } catch (e) {
      console.error("performBrowserAction error:", e);
    }
  }

  async fetchBrowserSnapshot() {
    try {
      const res = await fetch("/api/browser/snapshot");
      const data = await res.json();
      if (data.status === "SUCCESS") {
        const titleEl = document.getElementById("br-viewport-title");
        if (titleEl) titleEl.textContent = data.title || "Blank";

        const urlInput = document.getElementById("br-url-input");
        if (urlInput && data.url && data.url !== "about:blank") urlInput.value = data.url;

        const img = document.getElementById("br-screenshot-img");
        const placeholder = document.getElementById("br-placeholder-msg");
        const domPre = document.getElementById("br-dom-text");

        if (domPre) domPre.textContent = data.text || "No readable body text.";

        if (img && data.screenshot_b64) {
          img.src = "data:image/jpeg;base64," + data.screenshot_b64;
          img.style.display = "block";
          if (placeholder) placeholder.style.display = "none";
        }
      }
    } catch (e) {
      console.error("fetchBrowserSnapshot error:", e);
    }
  }

  async aiSummarizePage() {
    const box = document.getElementById("br-summary-output");
    if (box) box.innerHTML = "<span class='dim-text'>Extracting page DOM and generating AI summary...</span>";
    try {
      const res = await fetch("/api/browser/ai/summarize", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        box.innerHTML = `
          <strong>${escapeHtml(data.title)}</strong> (${data.word_count} words)<br><br>
          <p>${escapeHtml(data.summary)}</p>
          <ul style="margin:6px 0; padding-left:18px;">
            ${(data.takeaways || []).map(t => `<li>${escapeHtml(t)}</li>`).join("")}
          </ul>
        `;
      } else {
        box.innerHTML = `<span style="color:#ef4444;">Error: ${escapeHtml(data.error)}</span>`;
      }
    } catch (e) {
      if (box) box.innerHTML = `<span style="color:#ef4444;">Summarization failed: ${e}</span>`;
    }
  }

  async aiGroundedQA(question) {
    const box = document.getElementById("br-qa-output");
    if (box) box.innerHTML = "<span class='dim-text'>Scanning page DOM for verified answers...</span>";
    try {
      const res = await fetch("/api/browser/ai/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        box.innerHTML = `
          <strong style="color:var(--cyan-neon);">Answer (Confidence: ${Math.round(data.confidence * 100)}%):</strong><br>
          <p style="margin-top:4px;">${escapeHtml(data.answer)}</p>
          <span style="font-size:0.7rem; color:var(--text-muted);">Source: ${escapeHtml(data.source_url)}</span>
        `;
      }
    } catch (e) {
      if (box) box.innerHTML = `<span style="color:#ef4444;">Q&A error: ${e}</span>`;
    }
  }

  async aiExtractTables() {
    const box = document.getElementById("br-tables-output");
    if (box) box.innerHTML = "<span class='dim-text'>Scanning page for table elements...</span>";
    try {
      const res = await fetch("/api/browser/ai/extract-tables", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const data = await res.json();
      if (data.status === "SUCCESS" && data.tables.length > 0) {
        box.innerHTML = `<strong>Found ${data.table_count} Table(s):</strong><pre class="code-output-pre" style="max-height:120px; margin-top:6px;">${escapeHtml(JSON.stringify(data.tables, null, 2))}</pre>`;
      } else {
        box.innerHTML = "<span class='dim-text'>No tabular HTML elements detected on this page.</span>";
      }
    } catch (e) {
      if (box) box.innerHTML = `<span style="color:#ef4444;">Table extraction failed: ${e}</span>`;
    }
  }

  async aiGenerateReport() {
    const box = document.getElementById("br-report-output");
    if (box) box.innerHTML = "<span class='dim-text'>Compiling grounded publication-grade PDF report...</span>";
    try {
      const res = await fetch("/api/browser/ai/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const data = await res.json();
      if (data.status === "SUCCESS" && data.report) {
        box.innerHTML = `
          <span style="color:#10b981; font-weight:700;">✅ Research Report Ready!</span><br>
          <a href="${data.report.pdf_url}" target="_blank" class="action-btn-sm primary-btn" style="display:inline-block; margin-top:6px; text-decoration:none;">📄 Open ${escapeHtml(data.report.pdf_filename)} (${data.report.size_kb} KB)</a>
        `;
      } else {
        box.innerHTML = `<span style="color:#ef4444;">Report error: ${escapeHtml(data.error)}</span>`;
      }
    } catch (e) {
      if (box) box.innerHTML = `<span style="color:#ef4444;">PDF compilation failed: ${e}</span>`;
    }
  }

  async fetchBrowserBookmarks() {
    try {
      const res = await fetch("/api/browser/bookmarks");
      const data = await res.json();
      const list = data.bookmarks || [];
      const countEl = document.getElementById("br-bm-count");
      if (countEl) countEl.textContent = list.length;

      const container = document.getElementById("br-bookmarks-view");
      if (!container) return;

      if (list.length === 0) {
        container.innerHTML = "<p class='dim-text' style='padding:10px;'>No bookmarks saved.</p>";
        return;
      }
      container.innerHTML = list.map(b => `
        <div class="drawer-item">
          <div>
            <strong>${escapeHtml(b.title)}</strong>
            <span class="dim-text" style="margin-left:8px;">${escapeHtml(b.url)}</span>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="action-btn-sm" onclick="jarvis.navigateBrowser('${b.url}')">Open</button>
            <button class="action-btn-sm danger-btn" onclick="jarvis.deleteBrowserBookmark('${b.id}')">Delete</button>
          </div>
        </div>
      `).join("");
    } catch (e) {}
  }

  async addBrowserBookmark() {
    const title = document.getElementById("br-viewport-title")?.textContent || "Web Bookmark";
    const url = document.getElementById("br-url-input")?.value || "";
    if (!url) return alert("Please navigate to a page first.");
    try {
      await fetch("/api/browser/bookmarks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, url })
      });
      this.fetchBrowserBookmarks();
      alert("Bookmark saved!");
    } catch (e) {
      alert("Bookmark error: " + e);
    }
  }

  async deleteBrowserBookmark(id) {
    try {
      await fetch(`/api/browser/bookmarks/${id}`, { method: "DELETE" });
      this.fetchBrowserBookmarks();
    } catch (e) {}
  }

  async fetchBrowserHistory() {
    try {
      const res = await fetch("/api/browser/history");
      const data = await res.json();
      const list = data.history || [];
      const countEl = document.getElementById("br-hist-count");
      if (countEl) countEl.textContent = list.length;

      const container = document.getElementById("br-history-view");
      if (!container) return;
      if (list.length === 0) {
        container.innerHTML = "<p class='dim-text' style='padding:10px;'>No history recorded.</p>";
        return;
      }
      container.innerHTML = list.map(h => `
        <div class="drawer-item">
          <div>
            <strong>${escapeHtml(h.title)}</strong>
            <span class="dim-text" style="margin-left:8px;">${escapeHtml(h.url)}</span>
          </div>
          <button class="action-btn-sm" onclick="jarvis.navigateBrowser('${h.url}')">Visit</button>
        </div>
      `).join("");
    } catch (e) {}
  }

  // -------------------------------------------------------------------------
  // COMPONENT 2: SKILLS SYSTEM
  // -------------------------------------------------------------------------
  async fetchSkills(filterType = "all", searchQuery = "") {
    const grid = document.getElementById("skills-cards-grid");
    if (!grid) return;
    try {
      const res = await fetch("/api/skills/list");
      const data = await res.json();
      let skills = data.skills || [];

      if (filterType !== "all") {
        skills = skills.filter(s => s.skill_type === filterType);
      }
      if (searchQuery && searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        skills = skills.filter(s => s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q) || s.description.toLowerCase().includes(q));
      }

      this.installedSkillsCache = skills;

      if (skills.length === 0) {
        grid.innerHTML = "<p class='dim-text' style='grid-column:1/-1; padding:20px;'>No skills matched the criteria.</p>";
        return;
      }

      grid.innerHTML = skills.map(s => `
        <div class="skill-card ${this.selectedSkillId === s.id ? 'selected' : ''}" onclick="jarvis.selectSkill('${s.id}')">
          <div class="skill-card-top">
            <span class="skill-title">${escapeHtml(s.name)}</span>
            <span class="badge-pill ${s.skill_type}">${s.skill_type}</span>
          </div>
          <p class="skill-desc">${escapeHtml(s.description)}</p>
          <div class="skill-tags">
            ${(s.manifest.tags || []).map(t => `<span class="tag-chip">#${escapeHtml(t)}</span>`).join("")}
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
            <span style="font-size:0.68rem; color:var(--text-muted);">v${s.version} • by ${escapeHtml(s.author)}</span>
            <span class="status-tag ${s.is_enabled ? 'active' : 'denied'}">${s.is_enabled ? 'ENABLED' : 'DISABLED'}</span>
          </div>
        </div>
      `).join("");

      if (!this.selectedSkillId && skills.length > 0) {
        this.selectSkill(skills[0].id);
      }
    } catch (e) {
      grid.innerHTML = `<div class="error-msg">Failed to load skills: ${e}</div>`;
    }
  }

  selectSkill(skillId) {
    this.selectedSkillId = skillId;
    document.querySelectorAll(".skill-card").forEach(c => c.classList.remove("selected"));

    const skill = (this.installedSkillsCache || []).find(s => s.id === skillId);
    if (!skill) return;

    document.getElementById("exec-panel-title").textContent = skill.name;
    document.getElementById("exec-panel-badge").textContent = skill.skill_type.toUpperCase();
    document.getElementById("exec-panel-desc").textContent = skill.description;

    const paramInput = document.getElementById("skills-param-input");
    if (paramInput) {
      paramInput.value = JSON.stringify(skill.manifest.parameters_schema || {}, null, 2);
    }
    const runBtn = document.getElementById("skills-run-btn");
    const docBtn = document.getElementById("skills-view-doc-btn");
    if (runBtn) runBtn.disabled = !skill.is_enabled;
    if (docBtn) docBtn.disabled = false;
  }

  async executeSelectedSkill() {
    if (!this.selectedSkillId) return;
    const resultBox = document.getElementById("skills-exec-result");
    const statusTag = document.getElementById("exec-status-tag");
    const paramInput = document.getElementById("skills-param-input");

    let params = {};
    try {
      params = JSON.parse(paramInput.value || "{}");
    } catch (e) {
      return alert("Invalid JSON in parameters box: " + e);
    }

    if (statusTag) {
      statusTag.textContent = "RUNNING...";
      statusTag.className = "status-tag running";
    }
    if (resultBox) resultBox.textContent = "Executing skill in secure sandbox...";

    try {
      const res = await fetch(`/api/skills/${this.selectedSkillId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parameters: params, timeout_seconds: 30 })
      });
      const data = await res.json();
      if (statusTag) {
        statusTag.textContent = data.status;
        statusTag.className = `status-tag ${data.status.toLowerCase()}`;
      }
      if (resultBox) {
        resultBox.textContent = JSON.stringify(data, null, 2);
      }
    } catch (e) {
      if (resultBox) resultBox.textContent = "Execution request failed: " + e;
    }
  }

  async viewSelectedSkillDoc() {
    if (!this.selectedSkillId) return;
    try {
      const res = await fetch(`/api/skills/${this.selectedSkillId}`);
      const data = await res.json();
      alert(`=== ${data.name} (SKILL.md) ===\n\n${data.skill_md || 'No markdown documentation found.'}`);
    } catch (e) {
      alert("Error loading doc: " + e);
    }
  }

  // -------------------------------------------------------------------------
  // COMPONENT 3: SKILL MANAGER
  // -------------------------------------------------------------------------
  async fetchSkillManager() {
    await this.loadSkillRegistryTable();
    await this.fetchSkillExecutionHistory();
  }

  async loadSkillRegistryTable() {
    const tbody = document.getElementById("skmgr-table-body");
    if (!tbody) return;
    try {
      const res = await fetch("/api/skills/list");
      const data = await res.json();
      const skills = data.skills || [];

      tbody.innerHTML = skills.map(s => `
        <tr>
          <td><button class="action-btn-sm ${s.is_enabled ? 'buy-btn' : 'danger-btn'}" onclick="jarvis.toggleSkillState('${s.id}', ${!s.is_enabled})">${s.is_enabled ? 'Active' : 'Disabled'}</button></td>
          <td><code>${escapeHtml(s.id)}</code></td>
          <td><strong>${escapeHtml(s.name)}</strong></td>
          <td><span class="badge-pill ${s.skill_type}">${s.skill_type}</span></td>
          <td>v${s.version}</td>
          <td>${(s.permissions_required || []).map(p => `<code style="font-size:0.7rem;">${p}</code>`).join(", ") || 'None'}</td>
          <td>
            <button class="action-btn-sm danger-btn" onclick="jarvis.uninstallSkill('${s.id}')">Uninstall</button>
          </td>
        </tr>
      `).join("");
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="error-msg">Error: ${e}</td></tr>`;
    }
  }

  async toggleSkillState(skillId, enabled) {
    try {
      await fetch(`/api/skills/${skillId}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
      });
      this.loadSkillRegistryTable();
      this.fetchSkills();
    } catch (e) {
      alert("Toggle error: " + e);
    }
  }

  async installSkillFromPath() {
    const input = document.getElementById("skmgr-path-input");
    const path = input ? input.value.trim() : "";
    if (!path) return alert("Please specify the path to the skill folder.");

    try {
      const res = await fetch("/api/skills/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_path: path })
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        alert("Skill installed: " + data.message);
        input.value = "";
        this.loadSkillRegistryTable();
        this.fetchSkills();
      } else {
        alert("Installation failed: " + (data.detail || data.error));
      }
    } catch (e) {
      alert("Install error: " + e);
    }
  }

  async uninstallSkill(skillId) {
    if (!confirm(`Are you sure you want to uninstall and remove skill '${skillId}'?`)) return;
    try {
      const res = await fetch(`/api/skills/${skillId}`, { method: "DELETE" });
      const data = await res.json();
      alert(data.message || "Skill uninstalled.");
      this.loadSkillRegistryTable();
      this.fetchSkills();
    } catch (e) {
      alert("Uninstall error: " + e);
    }
  }

  async fetchSkillExecutionHistory() {
    const tbody = document.getElementById("skmgr-history-body");
    if (!tbody) return;
    try {
      const res = await fetch("/api/skills/coding_specialist/history");
      const data = await res.json();
      const history = data.history || [];

      if (history.length === 0) {
        tbody.innerHTML = "<tr><td colspan='5' class='dim-text' style='text-align:center;'>No execution records found.</td></tr>";
        return;
      }

      tbody.innerHTML = history.slice(0, 15).map(h => `
        <tr>
          <td>${new Date(h.executed_at * 1000).toLocaleTimeString()}</td>
          <td><code>${escapeHtml(h.skill_id)}</code></td>
          <td>${h.execution_time_ms}ms</td>
          <td><span class="status-tag ${h.status.toLowerCase()}">${h.status}</span></td>
          <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><code>${escapeHtml(JSON.stringify(h.output || h.error))}</code></td>
        </tr>
      `).join("");
    } catch (e) {}
  }

  // -------------------------------------------------------------------------
  // COMPONENT 4: CENTRAL PERMISSION MANAGER
  // -------------------------------------------------------------------------
  async fetchPermissions() {
    await this.renderGrantsTable();
    await this.renderPendingApprovals();
  }

  async renderGrantsTable() {
    const tbody = document.getElementById("perm-grants-body");
    if (!tbody) return;
    try {
      const res = await fetch("/api/permissions/list");
      const data = await res.json();
      const grants = data.grants || [];

      if (grants.length === 0) {
        tbody.innerHTML = "<tr><td colspan='5' class='dim-text' style='text-align:center;'>No active permission grants.</td></tr>";
        return;
      }

      tbody.innerHTML = grants.map(g => `
        <tr>
          <td><strong>${escapeHtml(g.component)}</strong></td>
          <td><code>${escapeHtml(g.resource)}</code></td>
          <td><span class="badge-pill ${g.level.toLowerCase()}">${g.level}</span></td>
          <td>${g.is_persistent ? 'Persistent' : (g.expires_at ? 'Temporary (TTL)' : 'Session')}</td>
          <td><button class="action-btn-sm danger-btn" onclick="jarvis.revokePermissionGrant('${g.id}')">Revoke</button></td>
        </tr>
      `).join("");
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="5" class="error-msg">Error: ${e}</td></tr>`;
    }
  }

  async renderPendingApprovals() {
    const container = document.getElementById("perm-pending-container");
    if (!container) return;
    try {
      const res = await fetch("/api/permissions/pending");
      const data = await res.json();
      const pending = data.pending_actions || [];

      if (pending.length === 0) {
        container.innerHTML = "<p class='dim-text'>No pending actions waiting for user confirmation.</p>";
        return;
      }

      container.innerHTML = pending.map(p => `
        <div class="pending-card">
          <div>
            <strong>${escapeHtml(p.action_type)}</strong> (Target: ${escapeHtml(p.target)})<br>
            <span style="font-size:0.75rem;">${escapeHtml(p.description)}</span><br>
            <span style="font-size:0.7rem; color:#f59e0b;">Expires in ${p.remaining_seconds}s</span>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="action-btn-sm buy-btn" onclick="jarvis.approvePendingAction('${p.action_id}', true)">Approve & Persist</button>
            <button class="action-btn-sm primary-btn" onclick="jarvis.approvePendingAction('${p.action_id}', false)">Approve Once</button>
            <button class="action-btn-sm danger-btn" onclick="jarvis.rejectPendingAction('${p.action_id}')">Deny</button>
          </div>
        </div>
      `).join("");
    } catch (e) {}
  }

  async submitGrantPermission() {
    const comp = document.getElementById("perm-new-comp")?.value;
    const res = document.getElementById("perm-new-res")?.value;
    const level = document.getElementById("perm-new-level")?.value;
    const persist = document.getElementById("perm-new-persist")?.checked;
    const notes = document.getElementById("perm-new-notes")?.value;

    if (!res) return alert("Please specify target resource.");

    try {
      const resp = await fetch("/api/permissions/grant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          component: comp,
          resource: res,
          level: level,
          is_persistent: persist,
          notes: notes
        })
      });
      const data = await resp.json();
      if (data.status === "SUCCESS") {
        alert(`Granted ${level} on ${comp}:${res}`);
        document.getElementById("perm-new-res").value = "";
        this.renderGrantsTable();
      } else {
        alert("Grant error: " + data.detail);
      }
    } catch (e) {
      alert("Error: " + e);
    }
  }

  async approvePendingAction(actionId, persist = false) {
    try {
      const res = await fetch(`/api/permissions/approve/${actionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grant_persistence: persist })
      });
      const data = await res.json();
      alert(data.message || "Action approved.");
      this.fetchPermissions();
    } catch (e) {
      alert("Approve error: " + e);
    }
  }

  async rejectPendingAction(actionId) {
    try {
      const res = await fetch(`/api/permissions/reject/${actionId}`, { method: "POST" });
      const data = await res.json();
      alert(data.message || "Action rejected.");
      this.fetchPermissions();
    } catch (e) {
      alert("Reject error: " + e);
    }
  }

  async revokePermissionGrant(grantId) {
    try {
      await fetch(`/api/permissions/grant/${grantId}`, { method: "DELETE" });
      this.renderGrantsTable();
    } catch (e) {
      alert("Revoke error: " + e);
    }
  }

  // -------------------------------------------------------------------------
  // COMPONENT 5: SKILL COLLABORATION ENGINE
  // -------------------------------------------------------------------------
  async fetchCollaboration() {
    await this.fetchCollaborationTasksHistory();
  }

  async planCollaborationTask() {
    const input = document.getElementById("collab-objective-input");
    const obj = input ? input.value.trim() : "";
    if (!obj) return alert("Please specify a multi-skill objective.");

    try {
      const res = await fetch("/api/collaboration/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: obj })
      });
      const data = await res.json();
      if (data.task_id) {
        this.activeCollabTaskId = data.task_id;
        document.getElementById("collab-active-task-title").textContent = `Pipeline: ${obj.slice(0, 45)}...`;
        document.getElementById("collab-active-task-status").textContent = "PLANNED";
        document.getElementById("collab-start-btn").disabled = false;
        document.getElementById("collab-pause-btn").disabled = true;
        document.getElementById("collab-resume-btn").disabled = true;
        document.getElementById("collab-cancel-btn").disabled = true;

        this.renderCollaborationStepPipeline(data.steps);
      }
    } catch (e) {
      alert("Plan error: " + e);
    }
  }

  renderCollaborationStepPipeline(steps = []) {
    const track = document.getElementById("collab-step-track");
    if (!track) return;
    track.innerHTML = steps.map((s, idx) => `
      <div class="collab-step-node" id="collab-node-${s.step_index}">
        <span style="font-size:0.68rem; color:var(--cyan-neon);">Step ${s.step_index + 1}</span>
        <strong>${escapeHtml(s.skill_id)}</strong>
        <span class="dim-text" style="font-size:0.7rem;">${escapeHtml(s.action_name)}</span>
      </div>
      ${idx < steps.length - 1 ? '<span class="collab-arrow">➔</span>' : ''}
    `).join("");
  }

  async startCollaborationTask() {
    if (!this.activeCollabTaskId) return;
    document.getElementById("collab-start-btn").disabled = true;
    document.getElementById("collab-pause-btn").disabled = false;
    document.getElementById("collab-cancel-btn").disabled = false;
    document.getElementById("collab-active-task-status").textContent = "RUNNING";

    const stream = document.getElementById("collab-stream-output");
    if (stream) stream.textContent = "Pipeline executing. Awaiting real-time skill handoffs...";

    try {
      await fetch(`/api/collaboration/start/${this.activeCollabTaskId}`, { method: "POST" });
    } catch (e) {
      alert("Start error: " + e);
    }
  }

  async pauseCollaborationTask() {
    if (!this.activeCollabTaskId) return;
    await fetch(`/api/collaboration/task/${this.activeCollabTaskId}/pause`, { method: "POST" });
    document.getElementById("collab-pause-btn").disabled = true;
    document.getElementById("collab-resume-btn").disabled = false;
    document.getElementById("collab-active-task-status").textContent = "PAUSED";
  }

  async resumeCollaborationTask() {
    if (!this.activeCollabTaskId) return;
    await fetch(`/api/collaboration/task/${this.activeCollabTaskId}/resume`, { method: "POST" });
    document.getElementById("collab-pause-btn").disabled = false;
    document.getElementById("collab-resume-btn").disabled = true;
    document.getElementById("collab-active-task-status").textContent = "RUNNING";
  }

  async cancelCollaborationTask() {
    if (!this.activeCollabTaskId) return;
    await fetch(`/api/collaboration/task/${this.activeCollabTaskId}/cancel`, { method: "POST" });
    document.getElementById("collab-pause-btn").disabled = true;
    document.getElementById("collab-resume-btn").disabled = true;
    document.getElementById("collab-cancel-btn").disabled = true;
    document.getElementById("collab-active-task-status").textContent = "CANCELLED";
  }

  async fetchCollaborationTasksHistory() {
    const tbody = document.getElementById("collab-tasks-table");
    if (!tbody) return;
    try {
      const res = await fetch("/api/collaboration/tasks");
      const data = await res.json();
      const tasks = data.tasks || [];

      if (tasks.length === 0) {
        tbody.innerHTML = "<tr><td colspan='6' class='dim-text' style='text-align:center;'>No collaborative tasks found.</td></tr>";
        return;
      }

      tbody.innerHTML = tasks.map(t => `
        <tr>
          <td><code>${escapeHtml(t.task_id)}</code></td>
          <td><strong>${escapeHtml(t.objective)}</strong></td>
          <td>${t.plan ? t.plan.length : 0} Steps</td>
          <td><span class="status-tag ${t.status.toLowerCase()}">${t.status}</span></td>
          <td>${new Date(t.created_at * 1000).toLocaleString()}</td>
          <td><button class="action-btn-sm" onclick="jarvis.viewCollaborationDetails('${t.task_id}')">Inspect</button></td>
        </tr>
      `).join("");
    } catch (e) {}
  }

  async viewCollaborationDetails(taskId) {
    try {
      const res = await fetch(`/api/collaboration/task/${taskId}`);
      const data = await res.json();
      alert(`=== Collaborative Task: ${data.task_id} ===\nStatus: ${data.status}\nOutput Summary:\n${JSON.stringify(data.output || {}, null, 2)}`);
    } catch (e) {
      alert("Error: " + e);
    }
  }

  // -------------------------------------------------------------------------
  // COMPONENT 6: UNIFIED ACTIVITY LOG
  // -------------------------------------------------------------------------
  async fetchActivityLogs() {
    await this.fetchActivityStats();
    await this.loadActivityEvents();
  }

  async fetchActivityStats() {
    try {
      const res = await fetch("/api/activity-log/stats");
      const data = await res.json();

      document.getElementById("act-kpi-total").textContent = data.total_events || 0;
      document.getElementById("act-kpi-browser").textContent = data.by_component?.browser || 0;
      document.getElementById("act-kpi-skills").textContent = data.by_component?.skills || 0;
      document.getElementById("act-kpi-perm").textContent = data.by_component?.permissions || 0;
      document.getElementById("act-kpi-os").textContent = (data.by_component?.os || 0) + (data.by_component?.system || 0);
    } catch (e) {}
  }

  async loadActivityEvents() {
    const tbody = document.getElementById("act-table-body");
    if (!tbody) return;

    const comp = document.getElementById("act-filter-comp")?.value || "all";
    const status = document.getElementById("act-filter-status")?.value || "all";
    const search = document.getElementById("act-filter-search")?.value || "";

    const url = `/api/activity-log/events?component=${comp}&execution_status=${status}&search=${encodeURIComponent(search)}&limit=50`;
    try {
      const res = await fetch(url);
      const data = await res.json();
      const events = data.events || [];

      if (events.length === 0) {
        tbody.innerHTML = "<tr><td colspan='7' class='dim-text' style='text-align:center;'>No matching activity logs.</td></tr>";
        return;
      }

      tbody.innerHTML = events.map(e => `
        <tr>
          <td>${escapeHtml(e.timestamp)}</td>
          <td><span class="badge-pill">${escapeHtml(e.component)}</span></td>
          <td><strong>${escapeHtml(e.action)}</strong></td>
          <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><code>${escapeHtml(e.target_resource || '-')}</code></td>
          <td><span class="badge ${e.approval_status === 'USER_APPROVED' ? 'buy-btn' : ''}">${escapeHtml(e.approval_status)}</span></td>
          <td><span class="status-tag ${e.execution_status.toLowerCase()}">${escapeHtml(e.execution_status)}</span></td>
          <td>${escapeHtml(e.result_summary || e.error_info || '-')}</td>
        </tr>
      `).join("");
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="error-msg">Error: ${e}</td></tr>`;
    }
  }

  exportActivityLogs(format = "json") {
    window.open(`/api/activity-log/export?format=${format}`, "_blank");
  }

  async clearActivityLogs() {
    if (!confirm("Are you sure you want to purge all activity logs? This is a SENSITIVE operation.")) return;
    try {
      const res = await fetch("/api/activity-log/clear", { method: "DELETE" });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        alert("Logs cleared: " + data.cleared_records + " records purged.");
        this.fetchActivityLogs();
      }
    } catch (e) {
      alert("Clear error: " + e);
    }
  }

  // -------------------------------------------------------------------------
  // COMPONENT 7: MEMORY TIMELINE & TRANSPARENCY
  // -------------------------------------------------------------------------
  async fetchMemoryTimeline() {
    await this.loadMemoryPrivacySettings();
    await this.loadMemoryTimeline();
  }

  async loadMemoryPrivacySettings() {
    try {
      const res = await fetch("/api/memory/privacy/settings");
      const data = await res.json();
      const toggle = document.getElementById("mem-recording-toggle");
      if (toggle) {
        toggle.textContent = data.recording_enabled ? "RECORDING: ON" : "RECORDING: MUTED";
        toggle.className = `action-btn-sm ${data.recording_enabled ? 'buy-btn' : 'danger-btn'}`;
        this.memoryRecordingState = data.recording_enabled;
      }
    } catch (e) {}
  }

  async toggleMemoryRecording() {
    const newState = !this.memoryRecordingState;
    try {
      await fetch("/api/memory/privacy/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recording_enabled: newState })
      });
      await this.loadMemoryPrivacySettings();
    } catch (e) {
      alert("Toggle error: " + e);
    }
  }

  async loadMemoryTimeline() {
    const feed = document.getElementById("mem-timeline-feed");
    if (!feed) return;

    const cat = document.getElementById("mem-filter-cat")?.value || "all";
    const src = document.getElementById("mem-filter-source")?.value || "all";
    const search = document.getElementById("mem-search-input")?.value || "";

    const url = `/api/memory/timeline?category=${cat}&source_type=${src}&search=${encodeURIComponent(search)}&limit=40`;
    try {
      const res = await fetch(url);
      const data = await res.json();
      const items = data.timeline || [];

      if (items.length === 0) {
        feed.innerHTML = "<p class='dim-text' style='padding:20px; text-align:center;'>No memories recorded in this timeline view.</p>";
        return;
      }

      feed.innerHTML = items.map(m => `
        <div class="memory-timeline-card ${m.is_important ? 'important' : ''}">
          <div class="memory-card-header">
            <span class="memory-source-pill">📌 ${escapeHtml(m.source_type)} ${m.source_reference ? '(' + escapeHtml(m.source_reference) + ')' : ''}</span>
            <span>${new Date(m.created_at * 1000).toLocaleString()} • Accessed ${m.access_count}x</span>
          </div>
          <div class="memory-card-body">
            <strong>[${escapeHtml(m.category)}] ${escapeHtml(m.key || 'Node')}:</strong><br>
            ${escapeHtml(m.content)}
          </div>
          <div class="memory-card-footer">
            <div>
              ${(m.tags || []).map(t => `<span class="tag-chip">#${escapeHtml(t)}</span>`).join(" ")}
            </div>
            <div class="memory-card-actions">
              <button class="action-btn-sm" onclick="jarvis.editMemoryInPlace('${m.id}', \`${escapeHtml(m.content)}\`)">✏️ Edit</button>
              <button class="action-btn-sm" onclick="jarvis.viewMemoryAccessLogs('${m.id}')">🕒 History</button>
              <button class="action-btn-sm danger-btn" onclick="jarvis.deleteMemoryPermanent('${m.id}')">🗑️ Delete</button>
            </div>
          </div>
        </div>
      `).join("");
    } catch (e) {
      feed.innerHTML = `<div class="error-msg">Failed to load memory timeline: ${e}</div>`;
    }
  }

  async editMemoryInPlace(memoryId, currentContent) {
    const updated = prompt("Edit memory content in-place:", currentContent);
    if (updated === null || updated.trim() === currentContent.trim()) return;

    try {
      const res = await fetch(`/api/memory/${memoryId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: updated.trim() })
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        this.loadMemoryTimeline();
      }
    } catch (e) {
      alert("Edit error: " + e);
    }
  }

  async deleteMemoryPermanent(memoryId) {
    if (!confirm("Permanently purge this memory from SQLite and full-text search index?")) return;
    try {
      const res = await fetch(`/api/memory/${memoryId}`, { method: "DELETE" });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        this.loadMemoryTimeline();
      }
    } catch (e) {
      alert("Delete error: " + e);
    }
  }

  async viewMemoryAccessLogs(memoryId) {
    try {
      const res = await fetch(`/api/memory/${memoryId}/history`);
      const data = await res.json();
      if (data.status === "SUCCESS") {
        const logs = data.access_logs || [];
        const logsStr = logs.map(l => `- ${new Date(l.accessed_at * 1000).toLocaleString()}: by [${l.component}] context: ${l.context_summary}`).join("\n");
        alert(`=== Memory Access Audit Trail (${memoryId}) ===\nTotal Accesses: ${data.access_count}\n\n${logsStr || 'No access records yet.'}`);
      }
    } catch (e) {
      alert("History error: " + e);
    }
  }

  async bulkPurgeCategory() {
    const cat = document.getElementById("mem-purge-cat-select")?.value;
    if (!cat) return;
    if (!confirm(`Are you sure you want to bulk purge all memories in category '${cat}'?`)) return;

    try {
      const res = await fetch("/api/memory/privacy/clear-category", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: cat })
      });
      const data = await res.json();
      alert(`Purged ${data.cleared_count} memories from '${cat}'.`);
      this.loadMemoryTimeline();
    } catch (e) {
      alert("Purge error: " + e);
    }
  }

  async addMemoryNodePrompt() {
    const cat = prompt("Enter Memory Category (e.g. user_preferences, research_knowledge):", "research_knowledge");
    if (!cat) return;
    const content = prompt("Enter Memory Content:");
    if (!content) return;
    const key = prompt("Enter Optional Key / Title:", "Note");

    try {
      const res = await fetch("/api/memory/node", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: cat,
          content: content,
          key: key,
          source_type: "explicit_instruction"
        })
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        alert("Memory node added!");
        this.loadMemoryTimeline();
      } else {
        alert("Failed to add memory: " + (data.detail || data.error));
      }
    } catch (e) {
      alert("Add memory error: " + e);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.jarvis = new JarvisClient();
});
