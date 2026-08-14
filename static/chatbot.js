(() => {
  const panel = document.querySelector("#chatbotPanel");
  const toggle = document.querySelector("#chatbotToggle");
  const closeButton = document.querySelector("#chatbotClose");
  const form = document.querySelector("#chatbotForm");
  const input = document.querySelector("#chatbotInput");
  const sendButton = document.querySelector("#chatbotSend");
  const messages = document.querySelector("#chatbotMessages");
  const errorBox = document.querySelector("#chatbotError");
  const conversationHistory = [];
  const maxHistoryMessages = 8;
  let serviceAvailable = true;

  if (!panel || !toggle || !closeButton || !form || !input || !sendButton || !messages || !errorBox) return;

  function setOpen(open) {
    panel.classList.toggle("chatbot-panel-open", open);
    panel.setAttribute("aria-hidden", String(!open));
    toggle.setAttribute("aria-expanded", String(open));
    toggle.hidden = open;
    if (open) input.focus();
  }

  function appendMessage(text, type) {
    const message = document.createElement("div");
    message.className = `chatbot-message chatbot-message-${type}`;
    message.textContent = text;
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
    return message;
  }

  function showError(message = "") {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  }

  function setLoading(loading) {
    input.disabled = loading;
    sendButton.disabled = loading;
    sendButton.textContent = loading ? "回覆中…" : "送出";
  }

  function setAvailable(available, message = "") {
    serviceAvailable = available;
    input.disabled = !available;
    sendButton.disabled = !available;
    sendButton.textContent = available ? "送出" : "暫停服務";
    if (!available) showError(message || "AI 客服目前暫停服務。");
  }

  async function loadStatus() {
    try {
      const response = await fetch("/api/chat/status", {
        credentials: "same-origin",
        cache: "no-store",
      });
      const data = await response.json().catch(() => ({}));
      if (Number.isInteger(data.max_message_length)) {
        input.maxLength = data.max_message_length;
      }
      setAvailable(Boolean(response.ok && data.ok && data.enabled), data.message);
    } catch {
      setAvailable(false, "AI 客服目前暫時無法使用。");
    }
  }

  async function sendMessage(message) {
    const response = await fetch("/api/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: conversationHistory.slice(-maxHistoryMessages),
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok || typeof data.reply !== "string") {
      throw new Error(data.error || "AI 客服目前暫時無法回覆，請稍後再試。");
    }
    return data.reply;
  }

  toggle.addEventListener("click", () => setOpen(true));
  closeButton.addEventListener("click", () => setOpen(false));

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!serviceAvailable || sendButton.disabled) return;
    const message = input.value.trim();
    if (!message) {
      showError("請輸入問題。");
      input.focus();
      return;
    }

    showError();
    appendMessage(message, "user");
    input.value = "";
    setLoading(true);
    const loadingMessage = appendMessage("正在整理回覆……", "loading");

    try {
      const reply = await sendMessage(message);
      loadingMessage.remove();
      appendMessage(reply, "ai");
      conversationHistory.push(
        { role: "user", content: message },
        { role: "assistant", content: reply }
      );
      if (conversationHistory.length > maxHistoryMessages) {
        conversationHistory.splice(0, conversationHistory.length - maxHistoryMessages);
      }
    } catch (error) {
      loadingMessage.remove();
      showError(error.message || "AI 客服目前暫時無法回覆，請稍後再試。");
    } finally {
      setLoading(false);
      input.focus();
    }
  });

  loadStatus();
})();
