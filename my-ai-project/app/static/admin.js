const dashboardError = document.querySelector("#dashboard-error");
const sheetsForm = document.querySelector("#sheets-settings-form");
const sheetsState = document.querySelector("#sheets-settings-state");
const saveSheetsButton = document.querySelector("#save-sheets-settings");
const previewSheetsButton = document.querySelector("#preview-sheets-settings");
const sheetsPreviewResult = document.querySelector("#sheets-preview-result");
const widgetSitesState = document.querySelector("#widget-sites-state");
const widgetSitesList = document.querySelector("#widget-sites-list");
const widgetSiteForm = document.querySelector("#widget-site-form");
const saveWidgetSiteButton = document.querySelector("#save-widget-site");
const cancelWidgetEditButton = document.querySelector("#cancel-widget-edit");
let editingWidgetSiteId = null;
let adminCsrfToken = "";
let sheetsSettingsConfigured = false;

function responseErrorMessage(body, fallback) {
  if (typeof body.detail === "string") return body.detail;
  return body.detail?.message || fallback;
}

async function loadSheetsSettings() {
  const response = await fetch("/api/v1/admin/settings/google-sheets");
  if (!response.ok) {
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(responseErrorMessage(body, "ยังเชื่อม Firestore ไม่ได้ จึงยังบันทึกการตั้งค่าไม่ได้"));
  }
  const data = await response.json();
  document.querySelector("#spreadsheet-id").value = data.spreadsheet_id || "";
  document.querySelector("#sheet-range").value = data.range || "product!A2:E";
  const productColumns = data.product_columns || {
    product_id: 1,
    product_name: 2,
    regular_price: 3,
    selling_price: 4,
    stock_quantity: 5,
  };
  document.querySelector("#sheet-column-id").value = productColumns.product_id;
  document.querySelector("#sheet-column-name").value = productColumns.product_name;
  document.querySelector("#sheet-column-regular-price").value = productColumns.regular_price;
  document.querySelector("#sheet-column-selling-price").value = productColumns.selling_price;
  document.querySelector("#sheet-column-stock").value = productColumns.stock_quantity;
  document.querySelector("#promotion-sheet-range").value =
    data.promotion_range || "promotion!A2:C";
  const promotionColumns = data.promotion_columns || {
    promotion_id: 1,
    promotion_name: 2,
    conditions: 3,
  };
  document.querySelector("#sheet-column-promotion-id").value = promotionColumns.promotion_id;
  document.querySelector("#sheet-column-promotion-name").value = promotionColumns.promotion_name;
  document.querySelector("#sheet-column-promotion-conditions").value = promotionColumns.conditions;
  document.querySelector("#orders-sheet-range").value = data.orders_range || "orders!A2:Z";
  document.querySelector("#member-sheet-range").value = data.member_range || "MEMBER!A2:Z";
  sheetsState.textContent = data.configured
    ? "โหลดการตั้งค่าจาก Firestore แล้ว"
    : "ยังไม่มีการตั้งค่า Spreadsheet";
  sheetsSettingsConfigured = data.configured;
  saveSheetsButton.disabled = !adminCsrfToken;
  previewSheetsButton.disabled = !adminCsrfToken || !sheetsSettingsConfigured;
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
        product_columns: {
          product_id: Number(document.querySelector("#sheet-column-id").value),
          product_name: Number(document.querySelector("#sheet-column-name").value),
          regular_price: Number(document.querySelector("#sheet-column-regular-price").value),
          selling_price: Number(document.querySelector("#sheet-column-selling-price").value),
          stock_quantity: Number(document.querySelector("#sheet-column-stock").value),
        },
        promotion_range: document.querySelector("#promotion-sheet-range").value.trim(),
        promotion_columns: {
          promotion_id: Number(document.querySelector("#sheet-column-promotion-id").value),
          promotion_name: Number(document.querySelector("#sheet-column-promotion-name").value),
          conditions: Number(document.querySelector("#sheet-column-promotion-conditions").value),
        },
        orders_range: document.querySelector("#orders-sheet-range").value.trim(),
        member_range: document.querySelector("#member-sheet-range").value.trim(),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message || "บันทึกการตั้งค่าไม่สำเร็จ");
    sheetsSettingsConfigured = true;
    previewSheetsButton.disabled = !adminCsrfToken;
    sheetsState.textContent = result.message;
  } catch (error) {
    sheetsState.textContent = error.message;
  } finally {
    saveSheetsButton.disabled = !adminCsrfToken;
  }
});

previewSheetsButton.addEventListener("click", async () => {
  previewSheetsButton.disabled = true;
  sheetsState.textContent = "กำลังอ่านแท็บสินค้าและโปรโมชั่นจาก Google Sheets…";
  sheetsPreviewResult.hidden = true;
  try {
    const response = await fetch("/api/v1/admin/settings/google-sheets/preview");
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    const result = await response.json();
    if (!response.ok) {
      throw new Error(responseErrorMessage(result, "อ่านตัวอย่างจาก Google Sheets ไม่สำเร็จ"));
    }
    sheetsPreviewResult.textContent = JSON.stringify(result, null, 2);
    sheetsPreviewResult.hidden = false;
    sheetsState.textContent =
      `ทดสอบสำเร็จ: สินค้า ${result.products.length} รายการ, โปรโมชั่น ${result.promotions.length} รายการ; ` +
      "ข้อมูลยังไม่ถูกบันทึก และไม่ได้อ่าน orders/MEMBER";
  } catch (error) {
    sheetsState.textContent = error.message;
  } finally {
    previewSheetsButton.disabled = !adminCsrfToken || !sheetsSettingsConfigured;
  }
});

function setWidgetEditMode(site) {
  editingWidgetSiteId = site ? site.site_id : null;
  document.querySelector("#widget-form-title").textContent = site ? "แก้ไขเว็บไซต์" : "เพิ่มเว็บไซต์";
  saveWidgetSiteButton.textContent = site ? "บันทึกการแก้ไขและสร้างโค้ดใหม่" : "บันทึกเว็บไซต์และสร้างโค้ด";
  cancelWidgetEditButton.hidden = !site;
  if (!site) {
    widgetSiteForm.reset();
    return;
  }
  document.querySelector("#widget-site-name").value = site.name;
  document.querySelector("#widget-site-domains").value = site.allowed_domains.join("\n");
  document.querySelector("#widget-title").value = site.title;
  document.querySelector("#widget-assistant").value = site.assistant_name;
  document.querySelector("#widget-launch").value = site.launch_text;
  document.querySelector("#widget-placeholder").value = site.placeholder;
  document.querySelector("#widget-color").value = site.primary_color;
  document.querySelector("#widget-language").value = site.speech_language;
  widgetSiteForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderWidgetSite(site) {
  const card = document.createElement("article");
  card.className = "widget-site-card";
  const heading = document.createElement("h3");
  heading.textContent = site.name;
  const domains = document.createElement("p");
  domains.textContent = `โดเมนที่อนุญาต: ${site.allowed_domains.join(", ")}`;
  const siteIdentifier = document.createElement("p");
  siteIdentifier.textContent = `Site ID: ${site.site_id}`;
  const code = document.createElement("textarea");
  code.readOnly = true;
  code.setAttribute("aria-label", `โค้ดติดตั้งสำหรับ ${site.name}`);
  code.value = site.embed_code;

  const actions = document.createElement("div");
  actions.className = "widget-site-actions";
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "primary-button";
  copyButton.textContent = "คัดลอกโค้ดติดตั้ง";
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code.value);
      widgetSitesState.textContent = `คัดลอกโค้ดของ ${site.name} แล้ว`;
    } catch (error) {
      code.focus();
      code.select();
      widgetSitesState.textContent = "คัดลอกอัตโนมัติไม่ได้ กรุณาคัดลอกโค้ดที่เลือกไว้";
    }
  });
  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "secondary-button";
  editButton.textContent = "แก้ไข";
  editButton.addEventListener("click", () => setWidgetEditMode(site));
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "secondary-button";
  deleteButton.textContent = "ปิดใช้งาน";
  deleteButton.addEventListener("click", async () => {
    if (!window.confirm(`ยืนยันปิดใช้งาน widget ของ ${site.name}? โค้ดที่ติดตั้งไว้จะเชื่อมต่อไม่ได้`)) return;
    deleteButton.disabled = true;
    try {
      const response = await fetch(`/api/v1/admin/widget-sites/${encodeURIComponent(site.site_id)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": adminCsrfToken },
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(responseErrorMessage(body, "ปิดใช้งานเว็บไซต์ไม่สำเร็จ"));
      }
      if (editingWidgetSiteId === site.site_id) setWidgetEditMode(null);
      await loadWidgetSites();
      widgetSitesState.textContent = `ปิดใช้งาน ${site.name} แล้ว`;
    } catch (error) {
      widgetSitesState.textContent = error.message;
      deleteButton.disabled = false;
    }
  });
  actions.append(copyButton, editButton, deleteButton);
  card.append(heading, domains, siteIdentifier, code, actions);
  return card;
}

async function loadWidgetSites() {
  const response = await fetch("/api/v1/admin/widget-sites");
  if (!response.ok) {
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(responseErrorMessage(body, "โหลดรายการเว็บไซต์ไม่สำเร็จ"));
  }
  const data = await response.json();
  widgetSitesList.replaceChildren(...data.sites.map(renderWidgetSite));
  widgetSitesState.textContent = data.sites.length
    ? `มีเว็บไซต์ที่ตั้งค่าแล้ว ${data.sites.length} รายการ`
    : "ยังไม่มีเว็บไซต์ เพิ่มเว็บไซต์ด้านล่างเพื่อสร้างโค้ดติดตั้ง";
  saveWidgetSiteButton.disabled = !adminCsrfToken;
}

widgetSiteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveWidgetSiteButton.disabled = true;
  widgetSitesState.textContent = "กำลังบันทึกการตั้งค่าเว็บไซต์…";
  const configuration = {
    name: document.querySelector("#widget-site-name").value.trim(),
    allowed_domains: document.querySelector("#widget-site-domains").value
      .split(/\r?\n/).map((domain) => domain.trim()).filter(Boolean),
    title: document.querySelector("#widget-title").value.trim(),
    assistant_name: document.querySelector("#widget-assistant").value.trim(),
    launch_text: document.querySelector("#widget-launch").value.trim(),
    placeholder: document.querySelector("#widget-placeholder").value.trim(),
    primary_color: document.querySelector("#widget-color").value,
    speech_language: document.querySelector("#widget-language").value,
    voice: "all-day",
  };
  const url = editingWidgetSiteId
    ? `/api/v1/admin/widget-sites/${encodeURIComponent(editingWidgetSiteId)}`
    : "/api/v1/admin/widget-sites";
  try {
    const response = await fetch(url, {
      method: editingWidgetSiteId ? "PUT" : "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": adminCsrfToken,
      },
      body: JSON.stringify(configuration),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(responseErrorMessage(result, "บันทึกเว็บไซต์ไม่สำเร็จ"));
    setWidgetEditMode(null);
    await loadWidgetSites();
    widgetSitesState.textContent = "บันทึกแล้ว ส่งโค้ดติดตั้งให้เจ้าของเว็บไซต์";
    const createdCard = Array.from(widgetSitesList.querySelectorAll(".widget-site-card"))
      .find((card) => card.querySelectorAll("p")[1]?.textContent?.includes(result.site_id));
    if (createdCard) createdCard.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    widgetSitesState.textContent = error.message;
  } finally {
    saveWidgetSiteButton.disabled = !adminCsrfToken;
  }
});

cancelWidgetEditButton.addEventListener("click", () => setWidgetEditMode(null));

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
    loadWidgetSites().catch((error) => {
      widgetSitesState.textContent = error.message;
      saveWidgetSiteButton.disabled = true;
    });
  })
  .catch((error) => {
    dashboardError.textContent = error.message;
    dashboardError.hidden = false;
  });
