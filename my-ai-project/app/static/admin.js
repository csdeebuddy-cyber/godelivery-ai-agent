const dashboardError = document.querySelector("#dashboard-error");
const sheetsForm = document.querySelector("#sheets-settings-form");
const sheetsState = document.querySelector("#sheets-settings-state");
const saveSheetsButton = document.querySelector("#save-sheets-settings");
let adminCsrfToken = "";

async function loadSheetsSettings() {
  const response = await fetch("/api/v1/admin/settings/google-sheets");
  if (!response.ok) {
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || "ยังเชื่อม Firestore ไม่ได้ จึงยังบันทึกการตั้งค่าไม่ได้");
  }
  const data = await response.json();
  document.querySelector("#spreadsheet-id").value = data.spreadsheet_id || "";
  document.querySelector("#sheet-range").value = data.range || "Products!A2:E";
  sheetsState.textContent = data.configured
    ? "โหลดการตั้งค่าจาก Firestore แล้ว"
    : "ยังไม่มีการตั้งค่า Spreadsheet";
  saveSheetsButton.disabled = !adminCsrfToken;
}

sheetsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveSheetsButton.disabled = true;
  sheetsState.textContent = "กำลังบันทึก…";
  try {
    const response = await fetch("/api/v1/admin/settings/google-sheets", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": adminCsrfToken,
      },
      body: JSON.stringify({
        spreadsheet_id: document.querySelector("#spreadsheet-id").value.trim(),
        range: document.querySelector("#sheet-range").value.trim(),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message || "บันทึกการตั้งค่าไม่สำเร็จ");
    sheetsState.textContent = result.message;
  } catch (error) {
    sheetsState.textContent = error.message;
  } finally {
    saveSheetsButton.disabled = !adminCsrfToken;
  }
});

fetch("/api/v1/admin/overview")
  .then(async (response) => {
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return null;
    }
    if (!response.ok) throw new Error("โหลดข้อมูลหลังบ้านไม่สำเร็จ");
    return response.json();
  })
  .then((data) => {
    if (!data) return;
    const knowledge = data.knowledge_base;
    adminCsrfToken = data.csrf_token;
    document.querySelector("#admin-email").textContent = data.admin_email;
    document.querySelector("#kb-state").textContent =
      knowledge.status === "ok" ? "พร้อมใช้งาน" : "ตรวจสอบไม่สำเร็จ";
    document.querySelector("#kb-detail").textContent =
      `แหล่งข้อมูล: ${knowledge.source?.url || "คลังข้อมูลในเครื่อง"}`;
    document.querySelector("#product-count").textContent = knowledge.products;
    document.querySelector("#verified-count").textContent =
      `ยืนยันแล้ว ${knowledge.verified_products} รายการ`;
    document.querySelector("#promotion-count").textContent = knowledge.active_promotions;
    document.querySelector("#storage-message").textContent = data.message;
    document.querySelector("#gemini-key-state").textContent =
      data.gemini_api_key_configured ? "ตั้งค่าแล้ว" : "ยังไม่ได้ตั้งค่า";
    loadSheetsSettings().catch((error) => {
      sheetsState.textContent = error.message;
      saveSheetsButton.disabled = true;
    });
  })
  .catch((error) => {
    dashboardError.textContent = error.message;
    dashboardError.hidden = false;
  });
