(function () {
  const globalConfig = window.GodeliveryChatConfig || {};
  const widgetId = globalConfig.widgetId || "godelivery-chat-widget";
  if (window.__godelivery_chat_widget_loaded__) {
    return;
  }
  window.__godelivery_chat_widget_loaded__ = true;

  const scriptElement = document.currentScript || Array.from(document.querySelectorAll("script[src*='widget.js']")).pop();
  const scriptOrigin = scriptElement && scriptElement.src ? new URL(scriptElement.src).origin : "";
  const apiBaseUrl = (globalConfig.apiBaseUrl || scriptOrigin || window.location.origin || "").replace(/\/$/, "");
  const title = globalConfig.title || "AI Agent Voice Allday";
  const assistantName = globalConfig.assistantName || "AI Assistant";
  const siteId = globalConfig.siteId || "";
  const launchText = globalConfig.launchText || "ถามเราได้เลย";
  const placeholder = globalConfig.placeholder || "พิมพ์ข้อความถึงเจ้าหน้าที่ AI...";
  const primaryColor = /^#[\da-f]{6}$/i.test(globalConfig.primaryColor || "")
    ? globalConfig.primaryColor
    : "#7c3aed";
  const speechLanguage = globalConfig.speechLanguage || "th-TH";
  const voice = globalConfig.voice || "all-day";
  const userId = globalConfig.userId || null;

  const css = `
    .godelivery-chat-widget {
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 2147483646;
      font-family: Arial, Helvetica, sans-serif;
      color: #111827;
    }
    .godelivery-chat-widget * { box-sizing: border-box; }
    .godelivery-chat-widget__launcher {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      border: none;
      cursor: pointer;
      border-radius: 999px;
      background: ${primaryColor};
      color: #ffffff;
      box-shadow: 0 12px 28px rgba(17, 24, 39, 0.18);
      padding: 0.9rem 1.2rem;
      font-size: 0.95rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }
    .godelivery-chat-widget__launcher:hover { filter: brightness(1.04); }
    .godelivery-chat-widget__launcher-badge {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #ffffff;
      box-shadow: 0 0 0 6px rgba(255,255,255,0.18);
    }
    .godelivery-chat-widget__panel {
      width: min(360px, calc(100vw - 32px));
      max-height: min(560px, calc(100vh - 120px));
      display: none;
      background: #ffffff;
      border: 1px solid rgba(17, 24, 39, 0.08);
      border-radius: 20px;
      box-shadow: 0 22px 55px rgba(17, 24, 39, 0.18);
      overflow: hidden;
      margin-bottom: 12px;
    }
    .godelivery-chat-widget__panel.is-open { display: block; }
    .godelivery-chat-widget__header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: ${primaryColor};
      color: #fff;
      padding: 0.9rem 1rem;
    }
    .godelivery-chat-widget__title {
      font-size: 0.96rem;
      font-weight: 700;
    }
    .godelivery-chat-widget__close {
      background: transparent;
      border: none;
      color: #fff;
      font-size: 1.3rem;
      cursor: pointer;
      line-height: 1;
      padding: 0.1rem 0.25rem;
    }
    .godelivery-chat-widget__conversation {
      max-height: 320px;
      overflow-y: auto;
      padding: 0.9rem;
      background: #f9fafb;
    }
    .godelivery-chat-widget__message {
      display: flex;
      margin-bottom: 0.75rem;
    }
    .godelivery-chat-widget__message--user { justify-content: flex-end; }
    .godelivery-chat-widget__bubble {
      max-width: 85%;
      padding: 0.7rem 0.8rem;
      border-radius: 14px;
      font-size: 0.92rem;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .godelivery-chat-widget__message--assistant .godelivery-chat-widget__bubble {
      background: #ffffff;
      border: 1px solid rgba(17, 24, 39, 0.08);
      color: #111827;
    }
    .godelivery-chat-widget__message--user .godelivery-chat-widget__bubble {
      background: ${primaryColor};
      color: #fff;
    }
    .godelivery-chat-widget__composer {
      padding: 0.8rem;
      border-top: 1px solid rgba(17, 24, 39, 0.08);
      background: #fff;
    }
    .godelivery-chat-widget__composer textarea {
      width: 100%;
      min-height: 72px;
      resize: vertical;
      border: 1px solid rgba(17, 24, 39, 0.12);
      border-radius: 12px;
      padding: 0.75rem 0.8rem;
      font: inherit;
      color: #111827;
    }
    .godelivery-chat-widget__composer textarea:focus {
      outline: 2px solid rgba(124, 58, 237, 0.2);
      border-color: ${primaryColor};
    }
    .godelivery-chat-widget__actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 0.6rem;
    }
    .godelivery-chat-widget__status {
      font-size: 0.75rem;
      color: #6b7280;
      min-height: 1em;
    }
    .godelivery-chat-widget__send {
      border: none;
      background: ${primaryColor};
      color: #fff;
      border-radius: 10px;
      padding: 0.7rem 0.9rem;
      font-size: 0.85rem;
      font-weight: 700;
      cursor: pointer;
    }
    .godelivery-chat-widget__send:disabled {
      opacity: 0.7;
      cursor: wait;
    }
    @media (max-width: 480px) {
      .godelivery-chat-widget {
        right: 12px;
        bottom: 12px;
      }
      .godelivery-chat-widget__launcher {
        padding: 0.8rem 1rem;
        font-size: 0.9rem;
      }
    }
  `;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function makeMessage(role, text) {
    const row = document.createElement("div");
    row.className = `godelivery-chat-widget__message godelivery-chat-widget__message--${role}`;
    const bubble = document.createElement("div");
    bubble.className = "godelivery-chat-widget__bubble";
    bubble.innerHTML = escapeHtml(text || "").replace(/\n/g, "<br>");
    row.appendChild(bubble);
    return row;
  }

  function getWidgetEndpoint() {
    return `${apiBaseUrl}/api/v1/widget/chat?site_id=${encodeURIComponent(siteId)}`;
  }

  function setStatus(text) {
    const status = document.querySelector(`#${widgetId}-status`);
    if (status) {
      status.textContent = text;
    }
  }

  function appendMessage(role, text) {
    const conversation = document.querySelector(`#${widgetId}-conversation`);
    if (!conversation) {
      return;
    }
    conversation.appendChild(makeMessage(role, text));
    conversation.scrollTop = conversation.scrollHeight;
  }

  async function sendChatMessage(messageText) {
    const trimmed = String(messageText || "").trim();
    if (!trimmed) {
      return;
    }
    if (!siteId) {
      setStatus("ยังไม่ได้ตั้งค่า site ID สำหรับ widget นี้");
      return;
    }
    const sendButton = document.querySelector(`#${widgetId}-send`);
    const input = document.querySelector(`#${widgetId}-input`);
    if (sendButton) sendButton.disabled = true;
    appendMessage("user", trimmed);
    setStatus("กำลังตอบกลับ...");
    if (input) input.value = "";

    try {
      const response = await fetch(getWidgetEndpoint(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: trimmed,
          context: JSON.stringify({
            source: "embeddable_widget",
            site: window.location.hostname,
            page: window.location.href,
            title: document.title,
          }),
          user_id: userId,
          voice,
          speech_language: speechLanguage,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail || "เกิดข้อผิดพลาดขณะส่งข้อความ");
      }
      appendMessage("assistant", data.reply || "ขออภัย ไม่มีคำตอบในตอนนี้");
      setStatus("พร้อมตอบคำถามถัดไป");
    } catch (error) {
      appendMessage("assistant", error instanceof Error ? error.message : "เกิดข้อผิดพลาดขณะเชื่อมต่อกับระบบ");
      setStatus("เกิดข้อผิดพลาด");
    } finally {
      if (sendButton) sendButton.disabled = false;
      if (input) input.focus();
    }
  }

  function buildWidget() {
    if (document.getElementById(widgetId)) {
      return;
    }

    const existingStyle = document.getElementById(`${widgetId}-styles`);
    if (!existingStyle) {
      const style = document.createElement("style");
      style.id = `${widgetId}-styles`;
      style.textContent = css;
      document.head.appendChild(style);
    }

    const root = document.createElement("div");
    root.id = widgetId;
    root.className = "godelivery-chat-widget";

    const panel = document.createElement("div");
    panel.id = `${widgetId}-panel`;
    panel.className = "godelivery-chat-widget__panel";
    panel.innerHTML = `
      <div class="godelivery-chat-widget__header">
        <div class="godelivery-chat-widget__title">${escapeHtml(title)}</div>
        <button class="godelivery-chat-widget__close" type="button" aria-label="ปิดแชท">×</button>
      </div>
      <div id="${widgetId}-conversation" class="godelivery-chat-widget__conversation">
        <div class="godelivery-chat-widget__message godelivery-chat-widget__message--assistant">
          <div class="godelivery-chat-widget__bubble">สวัสดีค่ะ ${escapeHtml(assistantName)} พร้อมให้คำแนะนำได้เลย</div>
        </div>
      </div>
      <div class="godelivery-chat-widget__composer">
        <textarea id="${widgetId}-input" placeholder="${escapeHtml(placeholder)}"></textarea>
        <div class="godelivery-chat-widget__actions">
          <span id="${widgetId}-status" class="godelivery-chat-widget__status">พร้อมใช้งาน</span>
          <button id="${widgetId}-send" class="godelivery-chat-widget__send" type="button">ส่ง</button>
        </div>
      </div>
    `;

    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.className = "godelivery-chat-widget__launcher";
    launcher.setAttribute("aria-label", launchText);
    launcher.innerHTML = `<span class="godelivery-chat-widget__launcher-badge" aria-hidden="true"></span><span>${escapeHtml(launchText)}</span>`;

    launcher.addEventListener("click", () => {
      panel.classList.toggle("is-open");
      if (panel.classList.contains("is-open")) {
        const input = document.querySelector(`#${widgetId}-input`);
        if (input) input.focus();
      }
    });

    panel.querySelector(".godelivery-chat-widget__close").addEventListener("click", () => {
      panel.classList.remove("is-open");
    });

    const input = panel.querySelector(`#${widgetId}-input`);
    const sendButton = panel.querySelector(`#${widgetId}-send`);
    const handleSend = () => sendChatMessage(input.value);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSend();
      }
    });
    sendButton.addEventListener("click", handleSend);

    root.appendChild(panel);
    root.appendChild(launcher);
    document.body.appendChild(root);

    if (globalConfig.startOpen) {
      panel.classList.add("is-open");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildWidget, { once: true });
  } else {
    buildWidget();
  }
})();
