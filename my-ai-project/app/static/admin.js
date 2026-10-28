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
const siteContentForm = document.querySelector("#site-content-form");
const siteContentState = document.querySelector("#site-content-state");
const saveSiteContentButton = document.querySelector("#save-site-content");
const siteFaqList = document.querySelector("#site-faq-list");
const siteProductList = document.querySelector("#site-product-list");
const sitePromotionList = document.querySelector("#site-promotion-list");
const catalogImageFile = document.querySelector("#catalog-image-file");
const catalogImageState = document.querySelector("#catalog-image-state");
const catalogImageGallery = document.querySelector("#catalog-image-gallery");
const uploadCatalogImageButton = document.querySelector("#upload-catalog-image");
let editingWidgetSiteId = null;
let adminCsrfToken = "";
let sheetsSettingsConfigured = false;
let catalogImages = [];

function responseErrorMessage(body, fallback) {
  if (typeof body.detail === "string") return body.detail;
  return body.detail?.message || fallback;
}

function contentField(labelText, name, value, { type = "text", wide = false, ...attributes } = {}) {
  const label = document.createElement("label");
  if (wide) label.className = "wide-field";
  label.append(document.createTextNode(labelText));
  const input = document.createElement(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") input.type = type;
  input.dataset.field = name;
  input.value = value ?? "";
  for (const [key, attributeValue] of Object.entries(attributes)) {
    input.setAttribute(key, attributeValue);
  }
  label.append(input);
  return label;
}

function updateProductOrderButtons() {
  const records = Array.from(siteProductList.querySelectorAll(".content-record"));
  records.forEach((record, index) => {
    record.querySelector('[data-action="move-up"]').disabled = index === 0;
    record.querySelector('[data-action="move-down"]').disabled = index === records.length - 1;
  });
}

function createContentRecord(kind, values = {}) {
  const record = document.createElement("fieldset");
  record.className = "content-record";
  record.dataset.kind = kind;
  const legend = document.createElement("legend");
  legend.textContent = kind === "faq"
    ? "คำถาม"
    : kind === "product"
      ? "สินค้า"
      : "โปรโมชัน";
  record.append(legend);

  const fields = document.createElement("div");
  fields.className = "content-record-grid";
  if (kind === "faq") {
    fields.append(
      contentField("คำถาม", "question", values.question, { required: "required", maxlength: "300" }),
      contentField("คำตอบ", "answer", values.answer, { type: "textarea", wide: true, required: "required", maxlength: "5000" }),
    );
  } else if (kind === "product") {
    const imageLabel = document.createElement("label");
    imageLabel.className = "wide-field";
    imageLabel.append(document.createTextNode("รูปสินค้า"));
    const imageSelect = document.createElement("select");
    imageSelect.dataset.field = "image_id";
    const noImageOption = document.createElement("option");
    noImageOption.value = "";
    noImageOption.textContent = "ไม่ใช้รูปภาพ";
    imageSelect.append(noImageOption);
    for (const image of catalogImages) {
      const option = document.createElement("option");
      option.value = image.asset_id;
      option.textContent = image.filename;
      imageSelect.append(option);
    }
    imageSelect.value = values.image_id || "";
    imageLabel.append(imageSelect);
    const linkLabel = document.createElement("label");
    linkLabel.className = "wide-field";
    linkLabel.append(document.createTextNode("ลิงก์ภาพจาก Firebase (วางแล้วระบบดึงภาพและบันทึกถาวรทันที)"));
    const linkInput = document.createElement("input");
    linkInput.type = "url";
    linkInput.dataset.field = "image_source_url";
    linkInput.maxLength = 2000;
    linkInput.placeholder = "https://firebasestorage.googleapis.com/v0/b/.../o/...?alt=media&token=...";
    linkInput.value = values.image_source_url || "";
    const linkStatus = document.createElement("small");
    linkStatus.className = "image-link-status";
    const linkPreview = document.createElement("img");
    linkPreview.className = "image-link-preview";
    linkPreview.alt = "";
    linkPreview.hidden = true;
    linkPreview.style.maxWidth = "120px";
    if (values.image_id) {
      linkPreview.src = `/api/v1/site/assets/${values.image_id}`;
      linkPreview.hidden = false;
    }
    linkLabel.append(linkInput, linkStatus, linkPreview);
    let importedUrl = linkInput.value.trim();
    const importLink = async () => {
      const url = linkInput.value.trim();
      if (!url || url === importedUrl) return;
      linkStatus.textContent = "กำลังดึงภาพและบันทึก…";
      try {
        const response = await fetch("/api/v1/admin/assets/import-link", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": adminCsrfToken },
          body: JSON.stringify({ url }),
        });
        const result = await response.json().catch(() => ({}));
        if (response.status === 401) {
          window.location.replace("/dashboard/admin/login");
          return;
        }
        if (!response.ok) throw new Error(responseErrorMessage(result, "ดึงภาพจากลิงก์ไม่สำเร็จ"));
        if (!Array.from(imageSelect.options).some((option) => option.value === result.asset_id)) {
          imageSelect.append(new Option(result.filename, result.asset_id));
        }
        if (!catalogImages.some((image) => image.asset_id === result.asset_id)) {
          catalogImages = [...catalogImages, result];
        }
        imageSelect.value = result.asset_id;
        importedUrl = url;
        linkPreview.src = result.url;
        linkPreview.hidden = false;
        linkStatus.textContent = "บันทึกภาพแล้ว กด “บันทึกและเผยแพร่” เพื่อใช้บนหน้าเว็บ";
      } catch (error) {
        linkStatus.textContent = error.message;
      }
    };
    linkInput.addEventListener("change", importLink);
    linkInput.addEventListener("paste", () => setTimeout(importLink, 0));
    fields.append(
      contentField("รหัสสินค้า", "product_id", values.product_id, { required: "required", maxlength: "80" }),
      contentField("ชื่อสินค้า", "name", values.name, { required: "required", maxlength: "180" }),
      imageLabel,
      linkLabel,
      contentField("รายละเอียด", "description", values.description, { type: "textarea", wide: true, maxlength: "3000" }),
      contentField("ราคาปกติ", "regular_price", values.regular_price ?? 0, { type: "number", min: "0", step: "0.01", required: "required" }),
      contentField("ราคาขาย (เว้นว่างถ้าไม่มี)", "sale_price", values.sale_price ?? "", { type: "number", min: "0", step: "0.01" }),
      contentField("จำนวนคงเหลือ", "stock_quantity", values.stock_quantity ?? 0, { type: "number", min: "0", step: "1", required: "required" }),
    );
  } else {
    fields.append(
      contentField("รหัสโปรโมชัน", "promotion_id", values.promotion_id, { required: "required", maxlength: "80" }),
      contentField("ชื่อโปรโมชัน", "title", values.title, { required: "required", maxlength: "180" }),
      contentField("เงื่อนไข/รายละเอียด", "details", values.details, { type: "textarea", wide: true, required: "required", maxlength: "5000" }),
    );
  }
  record.append(fields);

  if (kind !== "faq") {
    const activeLabel = document.createElement("label");
    activeLabel.className = "content-active";
    const activeInput = document.createElement("input");
    activeInput.type = "checkbox";
    activeInput.dataset.field = "active";
    activeInput.checked = values.active !== false;
    activeLabel.append(activeInput, document.createTextNode("เผยแพร่บนหน้าเว็บ"));
    record.append(activeLabel);
  }

  if (kind === "product") {
    const orderActions = document.createElement("div");
    orderActions.className = "product-order-actions";
    for (const [action, label] of [["move-up", "เลื่อนขึ้น"], ["move-down", "เลื่อนลง"]]) {
      const moveButton = document.createElement("button");
      moveButton.type = "button";
      moveButton.className = "secondary-button";
      moveButton.dataset.action = action;
      moveButton.textContent = label;
      moveButton.addEventListener("click", () => {
        const sibling = action === "move-up"
          ? record.previousElementSibling
          : record.nextElementSibling;
        if (!sibling) return;
        if (action === "move-up") siteProductList.insertBefore(record, sibling);
        else siteProductList.insertBefore(sibling, record);
        updateProductOrderButtons();
      });
      orderActions.append(moveButton);
    }
    record.append(orderActions);
  }

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "secondary-button content-remove-button";
  removeButton.textContent = "ลบรายการนี้";
  removeButton.addEventListener("click", () => {
    record.remove();
    if (kind === "product") updateProductOrderButtons();
  });
  record.append(removeButton);
  return record;
}

function renderContentRecords(container, kind, records) {
  container.replaceChildren(...records.map((record) => createContentRecord(kind, record)));
  if (kind === "product") updateProductOrderButtons();
}

function readContentRecords(container, kind) {
  return Array.from(container.querySelectorAll(".content-record")).map((record) => {
    const value = (name) => record.querySelector(`[data-field="${name}"]`).value.trim();
    if (kind === "faq") {
      return { question: value("question"), answer: value("answer") };
    }
    const active = record.querySelector('[data-field="active"]').checked;
    if (kind === "product") {
      const salePrice = value("sale_price");
      return {
        product_id: value("product_id"),
        name: value("name"),
        description: value("description"),
        image_id: value("image_id") || null,
        image_source_url: value("image_source_url") || null,
        regular_price: Number(value("regular_price")),
        sale_price: salePrice ? Number(salePrice) : null,
        stock_quantity: Number(value("stock_quantity")),
        active,
      };
    }
    return {
      promotion_id: value("promotion_id"),
      title: value("title"),
      details: value("details"),
      active,
    };
  });
}

function renderCatalogImages(images) {
  catalogImages = images;
  for (const productRecord of siteProductList.querySelectorAll(".content-record")) {
    const select = productRecord.querySelector('[data-field="image_id"]');
    const selectedId = select.value;
    const options = [
      new Option("ไม่ใช้รูปภาพ", ""),
      ...images.map((image) => new Option(image.filename, image.asset_id)),
    ];
    select.replaceChildren(...options);
    select.value = images.some((image) => image.asset_id === selectedId) ? selectedId : "";
  }
  catalogImageGallery.replaceChildren(...images.map((image) => {
    const card = document.createElement("article");
    card.className = "catalog-image-card";
    const preview = document.createElement("img");
    preview.src = image.url;
    preview.alt = image.filename;
    preview.loading = "lazy";
    card.append(preview);
    const filename = document.createElement("small");
    filename.textContent = image.filename;
    card.append(filename);
    return card;
  }));
}

async function loadCatalogImages() {
  const response = await fetch("/api/v1/admin/assets");
  if (!response.ok) {
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(responseErrorMessage(body, "โหลดคลังภาพไม่สำเร็จ"));
  }
  const result = await response.json();
  renderCatalogImages(result.assets || []);
  catalogImageState.textContent = result.assets?.length
    ? `มีภาพสินค้า ${result.assets.length} รายการใน Firebase Storage`
    : "ยังไม่มีภาพสินค้าในคลัง";
  uploadCatalogImageButton.disabled = !adminCsrfToken;
}

uploadCatalogImageButton.addEventListener("click", async () => {
  const file = catalogImageFile.files[0];
  if (!file) {
    catalogImageState.textContent = "กรุณาเลือกรูปภาพก่อนอัปโหลด";
    return;
  }
  uploadCatalogImageButton.disabled = true;
  catalogImageState.textContent = "กำลังอัปโหลดภาพไป Firebase Storage…";
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/v1/admin/assets/images", {
      method: "POST",
      headers: { "X-CSRF-Token": adminCsrfToken },
      body: formData,
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    if (!response.ok) throw new Error(responseErrorMessage(result, "อัปโหลดภาพไม่สำเร็จ"));
    catalogImageFile.value = "";
    await loadCatalogImages();
    catalogImageState.textContent = `อัปโหลด ${result.filename} แล้ว เลือกรูปนี้ในรายการสินค้าเพื่อเผยแพร่`;
  } catch (error) {
    catalogImageState.textContent = error.message;
  } finally {
    uploadCatalogImageButton.disabled = !adminCsrfToken;
  }
});

async function loadSiteContent() {
  const response = await fetch("/api/v1/admin/settings/site-content");
  if (!response.ok) {
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(responseErrorMessage(body, "โหลดเนื้อหาเว็บไซต์ไม่สำเร็จ"));
  }
  const content = await response.json();
  for (const sectionName of ["company", "terms", "security", "shipping", "returns"]) {
    document.querySelector(`#content-${sectionName}-title`).value = content[sectionName]?.title || "";
    document.querySelector(`#content-${sectionName}-body`).value = content[sectionName]?.body || "";
  }
  renderContentRecords(siteFaqList, "faq", content.faqs || []);
  renderContentRecords(siteProductList, "product", content.products || []);
  renderContentRecords(sitePromotionList, "promotion", content.promotions || []);
  siteContentState.textContent = "โหลดเนื้อหาจาก Firestore แล้ว";
  saveSiteContentButton.disabled = !adminCsrfToken;
}

for (const [buttonId, container, kind] of [
  ["#add-site-faq", siteFaqList, "faq"],
  ["#add-site-product", siteProductList, "product"],
  ["#add-site-promotion", sitePromotionList, "promotion"],
]) {
  document.querySelector(buttonId).addEventListener("click", () => {
    container.append(createContentRecord(kind));
    if (kind === "product") updateProductOrderButtons();
    container.lastElementChild.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

siteContentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveSiteContentButton.disabled = true;
  siteContentState.textContent = "กำลังบันทึกและเผยแพร่เนื้อหา…";
  const content = {};
  for (const sectionName of ["company", "terms", "security", "shipping", "returns"]) {
    content[sectionName] = {
      title: document.querySelector(`#content-${sectionName}-title`).value.trim(),
      body: document.querySelector(`#content-${sectionName}-body`).value.trim(),
    };
  }
  content.faqs = readContentRecords(siteFaqList, "faq");
  content.products = readContentRecords(siteProductList, "product");
  content.promotions = readContentRecords(sitePromotionList, "promotion");
  try {
    const response = await fetch("/api/v1/admin/settings/site-content", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": adminCsrfToken,
      },
      body: JSON.stringify(content),
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.location.replace("/dashboard/admin/login");
      return;
    }
    if (!response.ok) throw new Error(responseErrorMessage(result, "บันทึกเนื้อหาเว็บไซต์ไม่สำเร็จ"));
    siteContentState.textContent = result.message;
  } catch (error) {
    siteContentState.textContent = error.message;
  } finally {
    saveSiteContentButton.disabled = !adminCsrfToken;
  }
});

document.querySelector("#add-site-faq").disabled = false;
document.querySelector("#add-site-product").disabled = false;
document.querySelector("#add-site-promotion").disabled = false;

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
  document.querySelector("#orders-sheet-range").value = data.orders_range || "orders!A:O";
  document.querySelector("#member-sheet-range").value = data.member_range || "MEMBER!A:F";
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
    const firebaseStatus = data.firebase;
    const firestoreStatus = firebaseStatus.firestore_configured
      ? `Firestore: ${firebaseStatus.project_id}`
      : "Firestore: ยังไม่ตั้งค่า";
    const bucketStatus = firebaseStatus.storage_configured
      ? `Storage: ${firebaseStatus.storage_bucket}`
      : "Storage: ยังไม่ตั้งค่า bucket";
    document.querySelector("#storage-message").textContent =
      `${data.message} ${firestoreStatus} · ${bucketStatus}`;
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
    loadSiteContent().catch((error) => {
      siteContentState.textContent = error.message;
      saveSiteContentButton.disabled = true;
    });
    loadCatalogImages().catch((error) => {
      catalogImageState.textContent = error.message;
      uploadCatalogImageButton.disabled = true;
    });
  })
  .catch((error) => {
    dashboardError.textContent = error.message;
    dashboardError.hidden = false;
  });
