(() => {
  const API = "/api/v1/member";
  const dialog = document.querySelector("#member-dialog");
  const body = document.querySelector("#member-dialog-body");
  const signupButton = document.querySelector("#member-signup");
  const ssoButton = document.querySelector("#member-sso");
  const accountButton = document.querySelector("#member-account");
  let csrfToken = "";
  let profile = null;

  const MESSAGES = {
    account_locked: "บัญชีหรืออุปกรณ์นี้ถูกล็อคเพื่อความปลอดภัย กรุณาติดต่อเจ้าหน้าที่",
    sso_not_configured: "ระบบ SSO ยังไม่พร้อมใช้งาน",
    sign_in_failed: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่",
    state_invalid: "เซสชันหมดอายุ กรุณาลองใหม่",
    email_unverified: "อีเมลนี้ยังไม่ได้รับการยืนยันกับ Google",
    invalid_device: "ไม่สามารถระบุอุปกรณ์ได้",
    member_storage_unavailable: "ระบบสมาชิกยังไม่พร้อมใช้งาน",
  };

  function deviceId() {
    let id = localStorage.getItem("godelivery-device-id");
    if (!id || !/^[A-Za-z0-9-]{16,64}$/.test(id)) {
      id = crypto.randomUUID();
      localStorage.setItem("godelivery-device-id", id);
    }
    return id;
  }

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.assign(node, props);
    node.append(...children);
    return node;
  }

  function field(label, name, props = {}) {
    return el("label", {}, label, el("input", { name, ...props }));
  }

  function honeypot() {
    const wrapper = el("div", { className: "member-hp" });
    wrapper.setAttribute("aria-hidden", "true");
    wrapper.append(el("input", { name: "website", tabIndex: -1, autocomplete: "off" }));
    return wrapper;
  }

  async function api(path, options = {}) {
    const response = await fetch(API + path, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        ...(options.headers || {}),
      },
    });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      const error = new Error(
        (detail && (detail.message || (typeof detail === "string" ? detail : ""))) ||
          "ดำเนินการไม่สำเร็จ",
      );
      error.code = detail && detail.code;
      throw error;
    }
    return data;
  }

  function open(...nodes) {
    body.replaceChildren(...nodes);
    if (!dialog.open) dialog.showModal();
  }

  function message(text) {
    open(
      el("p", { className: "member-note" }, text),
      el("button", { className: "member-btn", type: "button", onclick: () => dialog.close() }, "ปิด"),
    );
  }

  function pinInput(label, name, autocomplete) {
    return field(label, name, {
      type: "password", inputMode: "numeric", pattern: "[0-9]{6}", maxLength: 6,
      required: true, autocomplete,
    });
  }

  function pinForm({ title, intro, confirm, onSubmit, submitLabel }) {
    const state = el("p", { className: "member-state", role: "status" });
    const form = el(
      "form",
      { className: "member-form" },
      el("h3", { id: "member-dialog-title" }, title),
      el("p", { className: "member-note" }, intro),
      pinInput("PIN 6 หลัก", "pin", confirm ? "new-password" : "current-password"),
    );
    if (confirm) form.append(pinInput("ยืนยัน PIN 6 หลัก", "confirm_pin", "new-password"));
    form.append(
      honeypot(),
      state,
      el("button", { className: "member-btn member-btn-primary", type: "submit" }, submitLabel),
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form));
      state.textContent = "กำลังดำเนินการ…";
      try {
        await onSubmit(data);
      } catch (error) {
        state.textContent = error.message;
        state.classList.add("member-state-error");
        if (error.code === "account_locked") {
          setTimeout(() => location.assign("/?member_error=account_locked"), 1200);
        }
      }
    });
    return form;
  }

  function showSetupPin() {
    open(pinForm({
      title: "สร้าง PIN 6 หลัก",
      intro: "ต้องสร้าง PIN ก่อนเริ่มใช้งาน PIN นี้ใช้ยืนยันเมื่อเข้าสู่ระบบจากอุปกรณ์ใหม่",
      confirm: true,
      submitLabel: "บันทึก PIN",
      onSubmit: async (data) => {
        if (data.pin !== data.confirm_pin) throw new Error("PIN ที่ยืนยันไม่ตรงกัน");
        const result = await api("/pin/setup", { method: "POST", body: JSON.stringify(data) });
        csrfToken = result.csrf_token;
        dialog.close();
        await refresh();
      },
    }));
  }

  function showVerifyPin() {
    open(pinForm({
      title: "ยืนยันตัวตนบนอุปกรณ์ใหม่",
      intro: "กรอก PIN 6 หลักเดิมที่เคยสร้างไว้",
      confirm: false,
      submitLabel: "ยืนยัน PIN",
      onSubmit: async (data) => {
        const result = await api("/pin/verify", { method: "POST", body: JSON.stringify(data) });
        csrfToken = result.csrf_token;
        dialog.close();
        await refresh();
      },
    }));
  }

  function prefillOrderForm() {
    const form = document.querySelector("#order-form");
    if (!form || !profile) return;
    const map = { customer: "name", address: "address", address1: "address1", postcode: "postcode", phone_number: "phone" };
    for (const [inputName, key] of Object.entries(map)) {
      const input = form.elements[inputName];
      if (input && !input.value && profile[key]) input.value = profile[key];
    }
  }

  async function refresh() {
    const me = await api("/me", { method: "GET" }).catch(() => ({ authenticated: false }));
    if (!me.authenticated) {
      accountButton.hidden = true;
      signupButton.hidden = ssoButton.hidden = false;
      if (me.error === "account_locked") message(MESSAGES.account_locked);
      return;
    }
    csrfToken = me.csrf_token;
    signupButton.hidden = ssoButton.hidden = true;
    accountButton.hidden = false;
    accountButton.textContent = me.customer_no;
    accountButton.dataset.href = `/user/${me.customer_no}`;
    if (me.stage === "setup_pin") return showSetupPin();
    if (me.stage === "verify_pin") return showVerifyPin();
    profile = me.profile;
    prefillOrderForm();
  }

  function startSso() {
    location.assign(`${API}/auth/google/login?device_id=${encodeURIComponent(deviceId())}`);
  }

  function reportBotIfAutomated() {
    if (navigator.webdriver !== true) return;
    fetch(`${API}/security/bot-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId(), signal: "webdriver" }),
    }).finally(() => message(MESSAGES.account_locked));
  }

  signupButton.addEventListener("click", startSso);
  ssoButton.addEventListener("click", startSso);
  accountButton.addEventListener("click", () => {
    if (accountButton.dataset.href) location.assign(accountButton.dataset.href);
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  reportBotIfAutomated();
  const params = new URLSearchParams(location.search);
  const errorCode = params.get("member_error");
  if (params.has("member") || errorCode) history.replaceState(null, "", location.pathname);
  refresh();
  if (errorCode) message(MESSAGES[errorCode] || MESSAGES.sign_in_failed);
})();
