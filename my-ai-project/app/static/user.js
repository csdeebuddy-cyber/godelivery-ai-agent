(() => {
  const API = "/api/v1/member";
  const form = document.querySelector("#user-form");
  const state = document.querySelector("#user-state");
  const editButton = document.querySelector("#user-edit");
  const saveButton = document.querySelector("#user-save");
  const cancelButton = document.querySelector("#user-cancel");
  const FIELDS = ["name", "address", "address1", "postcode", "phone"];
  let csrfToken = "";
  let profile = null;

  async function request(path, options = {}) {
    const response = await fetch(API + path, {
      credentials: "same-origin",
      ...options,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      throw new Error((detail && (detail.message || detail)) || "ดำเนินการไม่สำเร็จ");
    }
    return data;
  }

  function render(editing) {
    for (const name of FIELDS) {
      const input = form.elements[name];
      input.value = profile[name] || "";
      input.disabled = !editing;
    }
    editButton.hidden = editing;
    saveButton.hidden = cancelButton.hidden = !editing;
  }

  function say(text, isError = false) {
    state.textContent = text;
    state.classList.toggle("member-state-error", isError);
  }

  editButton.addEventListener("click", () => { say(""); render(true); });
  cancelButton.addEventListener("click", () => { say(""); render(false); });
  document.querySelector("#user-logout").addEventListener("click", async () => {
    await request("/logout", { method: "POST" }).catch(() => {});
    location.assign("/");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    say("กำลังบันทึก…");
    try {
      const result = await request("/profile", { method: "PUT", body: JSON.stringify(data) });
      profile = result.profile;
      render(false);
      say("บันทึกข้อมูลแล้ว");
    } catch (error) {
      say(error.message, true);
    }
  });

  (async () => {
    const me = await request("/me", { method: "GET" }).catch(() => null);
    const expected = location.pathname.split("/").filter(Boolean).pop();
    if (!me || !me.authenticated || me.stage !== "active" || me.customer_no !== expected) {
      location.replace("/");
      return;
    }
    csrfToken = me.csrf_token;
    profile = me.profile;
    document.querySelector("#user-customer-no").textContent = me.customer_no;
    document.querySelector("#user-email").value = me.email;
    render(false);
  })();
})();
