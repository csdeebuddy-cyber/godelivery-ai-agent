const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const micButton = document.querySelector("#mic-button");
const conversation = document.querySelector("#conversation");
const statusMessage = document.querySelector("#status-message");
const languageSelect = document.querySelector("#speech-language");
const connection = document.querySelector(".connection");
const connectionLabel = document.querySelector("#connection-label");

let liveSocket = null;
let liveReadyPromise = null;
let audioContext = null;
let microphoneStream = null;
let microphoneSource = null;
let microphoneProcessor = null;
let microphoneMute = null;
let isListening = false;
let playbackTime = 0;
let playbackNodes = [];
let assistantTranscript = null;

function setStatus(message) {
  statusMessage.textContent = message;
}

function scrollConversationToBottom() {
  conversation.scrollTop = conversation.scrollHeight;
}

function appendMessage(role, text, { error = false, speak = false } = {}) {
  const row = document.createElement("div");
  row.className = `message ${role === "user" ? "user-message" : "assistant-message"}${error ? " message-error" : ""}`;

  if (role !== "user") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "✦";
    row.append(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  bubble.append(paragraph);

  if (role !== "user" && speak) {
    const button = document.createElement("button");
    button.className = "speak-button";
    button.type = "button";
    button.textContent = "▶ ฟังเสียง";
    button.setAttribute("aria-label", "อ่านคำตอบออกเสียง");
    button.addEventListener("click", () => speakText(text));
    bubble.append(button);
  }

  row.append(bubble);
  conversation.append(row);
  scrollConversationToBottom();
  return row;
}

function speakText(text) {
  if (!("speechSynthesis" in window)) {
    setStatus("เบราว์เซอร์นี้ไม่รองรับการอ่านออกเสียง");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = languageSelect.value;
  window.speechSynthesis.speak(utterance);
}

function setConnected(connected) {
  connection.classList.toggle("is-online", connected);
  connection.classList.toggle("is-offline", !connected);
  connectionLabel.textContent = connected ? "เชื่อมต่อ Gemini Live แล้ว" : "ไม่ได้เชื่อมต่อ Gemini Live";
}

function updateAssistantTranscript(text) {
  if (!assistantTranscript) {
    const row = document.createElement("div");
    row.className = "message assistant-message";
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "✦";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const paragraph = document.createElement("p");
    bubble.append(paragraph);
    row.append(avatar, bubble);
    conversation.append(row);
    assistantTranscript = paragraph;
  }
  assistantTranscript.textContent += text;
  scrollConversationToBottom();
}

function stopPlayback() {
  for (const node of playbackNodes) {
    try {
      node.stop();
    } catch {
      // The node may already have completed.
    }
  }
  playbackNodes = [];
  playbackTime = audioContext ? audioContext.currentTime : 0;
}

async function playPcmAudio(encodedAudio) {
  if (!audioContext) {
    audioContext = new AudioContext({ sampleRate: 16000 });
  }
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  const binary = atob(encodedAudio);
  const sampleCount = Math.floor(binary.length / 2);
  const audioBuffer = audioContext.createBuffer(1, sampleCount, 24000);
  const channel = audioBuffer.getChannelData(0);
  const data = new DataView(Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer);
  for (let index = 0; index < sampleCount; index += 1) {
    channel[index] = data.getInt16(index * 2, true) / 32768;
  }

  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  const startAt = Math.max(audioContext.currentTime, playbackTime);
  source.start(startAt);
  playbackTime = startAt + audioBuffer.duration;
  playbackNodes.push(source);
  source.onended = () => {
    playbackNodes = playbackNodes.filter((node) => node !== source);
  };
}

function handleLiveMessage(message) {
  if (message.type === "ready") {
    setConnected(true);
    setStatus("Gemini Live พร้อมแล้ว กำลังเชื่อมต่อเสียง...");
  } else if (message.type === "input_transcription") {
    if (message.text) appendMessage("user", message.text);
  } else if (message.type === "output_transcription") {
    if (message.text) updateAssistantTranscript(message.text);
  } else if (message.type === "audio") {
    playPcmAudio(message.data).catch(() => setStatus("เล่นเสียงตอบกลับไม่ได้"));
  } else if (message.type === "turn_complete") {
    assistantTranscript = null;
    setStatus(isListening ? "กำลังฟัง พูดได้เลย" : "ได้รับคำตอบจาก Gemini Live แล้ว");
  } else if (message.type === "interrupted") {
    stopPlayback();
    assistantTranscript = null;
  } else if (message.type === "error") {
    setStatus(message.message || "Gemini Live เกิดข้อผิดพลาด");
    appendMessage("assistant", message.message || "Gemini Live เกิดข้อผิดพลาด", { error: true });
  }
}

function openLiveSession() {
  if (liveSocket?.readyState === WebSocket.OPEN) {
    return Promise.resolve(liveSocket);
  }
  if (liveReadyPromise) return liveReadyPromise;

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const language = encodeURIComponent(languageSelect.value);
  const socket = new WebSocket(`${protocol}//${window.location.host}/api/v1/live?language=${language}`);
  liveSocket = socket;

  liveReadyPromise = new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      reject(new Error("หมดเวลารอเชื่อมต่อ Gemini Live"));
      socket.close();
    }, 20000);

    socket.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        setStatus("ได้รับข้อมูลที่อ่านไม่ได้จาก Gemini Live");
        return;
      }

      handleLiveMessage(message);
      if (message.type === "ready") {
        window.clearTimeout(timeout);
        resolve(socket);
      } else if (message.type === "error") {
        window.clearTimeout(timeout);
        reject(new Error(message.message || "Gemini Live connection failed"));
      }
    };

    socket.onerror = () => {
      window.clearTimeout(timeout);
      reject(new Error("เชื่อมต่อ Gemini Live ไม่สำเร็จ ตรวจสอบว่าเซิร์ฟเวอร์กำลังทำงาน"));
    };

    socket.onclose = () => {
      window.clearTimeout(timeout);
      if (liveSocket === socket) {
        liveSocket = null;
        liveReadyPromise = null;
        setConnected(false);
        if (isListening) stopMicrophone();
      }
      if (socket.readyState !== WebSocket.OPEN) {
        reject(new Error("การเชื่อมต่อ Gemini Live ถูกปิด"));
      }
    };
  }).finally(() => {
    liveReadyPromise = null;
  });

  return liveReadyPromise;
}

function floatToPcm16(samples, inputSampleRate) {
  const outputSampleRate = 16000;
  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.floor(samples.length / ratio);
  const pcm = new Int16Array(outputLength);

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const start = Math.floor(outputIndex * ratio);
    const end = Math.min(Math.floor((outputIndex + 1) * ratio), samples.length);
    let total = 0;
    for (let inputIndex = start; inputIndex < end; inputIndex += 1) {
      total += samples[inputIndex];
    }
    const sample = end > start ? total / (end - start) : 0;
    pcm[outputIndex] = Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767);
  }
  return pcm;
}

function encodePcm16(pcm) {
  const bytes = new Uint8Array(pcm.buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function stopMicrophone() {
  if (microphoneProcessor) {
    microphoneProcessor.disconnect();
    microphoneProcessor.onaudioprocess = null;
    microphoneProcessor = null;
  }
  microphoneSource?.disconnect();
  microphoneSource = null;
  microphoneMute?.disconnect();
  microphoneMute = null;
  microphoneStream?.getTracks().forEach((track) => track.stop());
  microphoneStream = null;
  isListening = false;
  micButton.classList.remove("is-listening");
  micButton.title = "เริ่มเสียงเรียลไทม์";
  micButton.setAttribute("aria-label", "เริ่มเสียงเรียลไทม์");
}

async function startMicrophone() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("เบราว์เซอร์นี้ไม่รองรับไมโครโฟน ต้องใช้ HTTPS หรือ localhost");
  }
  microphoneStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
  });
  await openLiveSession();
  audioContext = audioContext || new AudioContext({ sampleRate: 16000 });
  await audioContext.resume();
  microphoneSource = audioContext.createMediaStreamSource(microphoneStream);
  microphoneProcessor = audioContext.createScriptProcessor(4096, 1, 1);
  microphoneMute = audioContext.createGain();
  microphoneMute.gain.value = 0;
  microphoneProcessor.onaudioprocess = (event) => {
    if (liveSocket?.readyState !== WebSocket.OPEN || liveSocket.bufferedAmount > 512000) return;
    const pcm = floatToPcm16(event.inputBuffer.getChannelData(0), audioContext.sampleRate);
    liveSocket.send(JSON.stringify({ type: "audio", data: encodePcm16(pcm) }));
  };
  microphoneSource.connect(microphoneProcessor);
  microphoneProcessor.connect(microphoneMute);
  microphoneMute.connect(audioContext.destination);
  isListening = true;
  micButton.classList.add("is-listening");
  micButton.title = "หยุดเสียงเรียลไทม์";
  micButton.setAttribute("aria-label", "หยุดเสียงเรียลไทม์");
  setStatus("กำลังฟัง พูดได้เลย");
}

async function stopLiveSession() {
  stopMicrophone();
  if (liveSocket?.readyState === WebSocket.OPEN) {
    liveSocket.send(JSON.stringify({ type: "stop_audio" }));
    liveSocket.close(1000, "User stopped live session");
  }
  liveSocket = null;
  liveReadyPromise = null;
  setConnected(false);
  setStatus("จบการสนทนาเสียงแล้ว");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || sendButton.disabled) return;

  appendMessage("user", message);
  input.value = "";
  sendButton.disabled = true;
  setStatus("กำลังส่งข้อความไปยัง Gemini Live...");
  try {
    audioContext = audioContext || new AudioContext({ sampleRate: 16000 });
    await audioContext.resume();
    const socket = await openLiveSession();
    socket.send(JSON.stringify({ type: "text", text: message }));
    setStatus("กำลังรอคำตอบเสียงจาก Gemini Live...");
  } catch (error) {
    appendMessage("assistant", error.message, { error: true });
    setStatus("เชื่อมต่อ Gemini Live ไม่สำเร็จ");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

micButton.addEventListener("click", async () => {
  if (isListening) {
    stopMicrophone();
    if (liveSocket?.readyState === WebSocket.OPEN) {
      liveSocket.send(JSON.stringify({ type: "stop_audio" }));
    }
    setStatus("หยุดไมโครโฟนแล้ว กดอีกครั้งเพื่อพูดต่อ");
    return;
  }

  micButton.disabled = true;
  setStatus("กำลังเชื่อมต่อ Gemini Live...");
  try {
    await startMicrophone();
  } catch (error) {
    stopMicrophone();
    setStatus(error.message || "เริ่มไมโครโฟนไม่สำเร็จ");
    if (liveSocket?.readyState === WebSocket.OPEN) liveSocket.close();
  } finally {
    micButton.disabled = false;
  }
});

languageSelect.addEventListener("change", async () => {
  const wasConnected = liveSocket?.readyState === WebSocket.OPEN;
  if (wasConnected) {
    await stopLiveSession();
    setStatus("เปลี่ยนภาษาแล้ว ส่งข้อความหรือเริ่มไมโครโฟนเพื่อเชื่อมต่อใหม่");
  }
});

async function checkApiStatus() {
  try {
    const response = await fetch("/api/v1/health");
    if (!response.ok) throw new Error("Health check failed");
    connection.classList.add("is-online");
    connectionLabel.textContent = "API พร้อมใช้งาน";
  } catch {
    connection.classList.add("is-offline");
    connectionLabel.textContent = "เชื่อมต่อ API ไม่ได้";
  }
}

checkApiStatus();
