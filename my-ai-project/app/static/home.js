const productGrid = document.querySelector("#product-grid");
const productsEmpty = document.querySelector("#products-empty");
const promotionList = document.querySelector("#promotion-list");
const faqList = document.querySelector("#faq-list");
const faqsEmpty = document.querySelector("#faqs-empty");
const basketItems = document.querySelector("#basket-items");
const basketEmpty = document.querySelector("#basket-empty");
const orderArea = document.querySelector("#order-area");
const orderForm = document.querySelector("#order-form");
const orderState = document.querySelector("#order-state");
const memberForm = document.querySelector("#member-form");
const memberState = document.querySelector("#member-state");
const basketCount = document.querySelector("#basket-count");
const productById = new Map();
let basket = new Map();
let privacyPolicyConfigured = false;

function showState(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("form-state-error", isError);
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function getPrice(product) {
  return product.sale_price ?? product.regular_price;
}

function formatPrice(value) {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    maximumFractionDigits: 2,
  }).format(value);
}

function persistBasket() {
  try {
    localStorage.setItem("godelivery-basket", JSON.stringify(Array.from(basket.entries())));
  } catch (error) {
    showState(orderState, "บันทึกตะกร้าในอุปกรณ์นี้ไม่ได้ กรุณาคงหน้าเว็บไว้จนกว่าจะส่งรายการ", true);
  }
}

function addToBasket(productId) {
  const product = productById.get(productId);
  const quantity = basket.get(productId) || 0;
  if (!product || quantity >= product.stock_quantity) return;
  basket.set(productId, quantity + 1);
  persistBasket();
  renderProducts(Array.from(productById.values()));
  renderBasket();
  document.querySelector("#basket").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderProducts(products) {
  const activeProducts = products.filter((product) => product.active);
  productById.clear();
  for (const product of activeProducts) productById.set(product.product_id, product);
  productsEmpty.hidden = activeProducts.length > 0;
  productGrid.replaceChildren(...activeProducts.slice(0, 4).map((product) => {
    const card = makeElement("article", "product-card");
    const media = makeElement("div", "home-product-media");
    if (product.image_url) {
      const image = document.createElement("img");
      image.className = "product-image";
      image.src = product.image_url;
      image.alt = product.name;
      image.loading = "lazy";
      media.append(image);
    } else {
      media.append(makeElement("span", "home-product-placeholder", "GO"));
    }
    const discount = product.sale_price !== null
      && product.sale_price !== undefined
      && product.regular_price > 0
      && product.sale_price < product.regular_price
      ? Math.round((1 - product.sale_price / product.regular_price) * 100)
      : 0;
    if (discount > 0) media.append(makeElement("span", "home-product-discount", `-${discount}%`));
    card.append(media);
    card.append(makeElement("small", "product-id", `รหัส ${product.product_id}`));
    card.append(makeElement("h3", "", product.name));
    if (product.description) card.append(makeElement("p", "", product.description));
    const stockText = product.stock_quantity > 0
      ? `คงเหลือ ${product.stock_quantity} ชิ้น`
      : "สินค้าหมดชั่วคราว";
    card.append(makeElement("small", "product-stock", stockText));
    const price = makeElement("div", "product-price");
    price.append(makeElement("strong", "", formatPrice(getPrice(product))));
    if (product.sale_price !== null && product.sale_price !== undefined) {
      price.append(makeElement("del", "", formatPrice(product.regular_price)));
    }
    card.append(price);
    const alreadyInBasket = basket.get(product.product_id) || 0;
    const canAddToBasket = product.stock_quantity > alreadyInBasket;
    const addButton = makeElement(
      "button",
      "add-to-basket",
      canAddToBasket ? "เพิ่มลงตะกร้า" : "สินค้าเต็มจำนวนในตะกร้า",
    );
    addButton.type = "button";
    addButton.disabled = !canAddToBasket;
    addButton.addEventListener("click", () => addToBasket(product.product_id));
    card.append(addButton);
    return card;
  }));
}

function renderPromotions(promotions) {
  const activePromotions = promotions.filter((promotion) => promotion.active);
  const cards = activePromotions.map((promotion) => {
    const card = makeElement("article", "promotion-card");
    card.append(makeElement("small", "", `รหัส ${promotion.promotion_id}`));
    card.append(makeElement("h3", "", promotion.title));
    card.append(makeElement("p", "", promotion.details));
    return card;
  });
  if (!cards.length) {
    cards.push(makeElement("p", "catalog-empty", "ขณะนี้ยังไม่มีโปรโมชันที่เผยแพร่"));
  }
  promotionList.replaceChildren(...cards);
}

function renderFAQs(faqs) {
  const activeFAQs = faqs.filter((faq) => faq.active !== false);
  faqsEmpty.hidden = activeFAQs.length > 0;
  faqList.replaceChildren(...activeFAQs.map((faq) => {
    const item = document.createElement("details");
    item.append(makeElement("summary", "", faq.question));
    item.append(makeElement("p", "", faq.answer));
    return item;
  }));
}

function renderBasket() {
  let totalItems = 0;
  let totalPrice = 0;
  const lines = [];
  let hasUnavailableProduct = false;
  for (const [productId, quantity] of basket.entries()) {
    totalItems += quantity;
    const product = productById.get(productId);
    const line = makeElement("div", "basket-line");
    const description = document.createElement("div");
    if (!product) {
      hasUnavailableProduct = true;
      description.append(makeElement("strong", "", `สินค้า ${productId} ไม่พร้อมจำหน่าย`));
      description.append(makeElement("small", "", "นำรายการออกจากตะกร้าก่อนส่งคำสั่งซื้อ"));
    } else {
      description.append(makeElement("strong", "", product.name));
      if (quantity > product.stock_quantity) {
        hasUnavailableProduct = true;
        description.append(makeElement("small", "", `จำนวนเกินสต็อกที่เหลือ ${product.stock_quantity} ชิ้น`));
      }
      const linePrice = getPrice(product) * quantity;
      totalPrice += linePrice;
      description.append(makeElement("small", "", `${formatPrice(getPrice(product))} × ${quantity} = ${formatPrice(linePrice)}`));
    }
    line.append(description);

    const decrease = makeElement("button", "", "−");
    decrease.type = "button";
    decrease.setAttribute("aria-label", `ลดจำนวน ${product?.name || productId}`);
    decrease.addEventListener("click", () => {
      if (quantity <= 1) basket.delete(productId);
      else basket.set(productId, quantity - 1);
      persistBasket();
      renderBasket();
    });
    const quantityLabel = makeElement("span", "", String(quantity));
    const increase = makeElement("button", "", "+");
    increase.type = "button";
    increase.setAttribute("aria-label", `เพิ่มจำนวน ${product?.name || productId}`);
    increase.disabled = !product || quantity >= product.stock_quantity;
    increase.addEventListener("click", () => {
      basket.set(productId, quantity + 1);
      persistBasket();
      renderBasket();
    });
    const remove = makeElement("button", "remove-item", "นำออก");
    remove.type = "button";
    remove.addEventListener("click", () => {
      basket.delete(productId);
      persistBasket();
      renderBasket();
    });
    line.append(decrease, quantityLabel, increase, remove);
    lines.push(line);
  }
  basketItems.replaceChildren(...lines);
  basketEmpty.hidden = basket.size > 0;
  orderArea.hidden = basket.size === 0;
  basketCount.textContent = String(totalItems);
  document.querySelector("#basket-total").textContent = formatPrice(totalPrice);
  orderForm.querySelector('button[type="submit"]').disabled =
    hasUnavailableProduct || !privacyPolicyConfigured;
}

function renderSiteContent(content) {
  for (const sectionName of ["company", "terms", "security", "shipping", "returns"]) {
    const section = content[sectionName] || {};
    const title = document.querySelector(`#${sectionName}-title`);
    const body = document.querySelector(`#${sectionName}-body`);
    title.textContent = section.title || "";
    body.textContent = section.body || "";
  }
  renderFAQs(content.faqs || []);
  renderProducts(content.products || []);
  renderPromotions(content.promotions || []);
  privacyPolicyConfigured = Boolean(content.security?.body?.trim());
  for (const form of [orderForm, memberForm]) {
    form.querySelector('input[name="privacy_consent"]').disabled = !privacyPolicyConfigured;
    form.querySelector('button[type="submit"]').disabled = !privacyPolicyConfigured;
  }
  renderBasket();
}

async function loadSiteContent() {
  try {
    const response = await fetch("/api/v1/site/content", { cache: "no-store" });
    if (!response.ok) throw new Error("โหลดเนื้อหาล่าสุดไม่สำเร็จ กรุณาลองใหม่ภายหลัง");
    const content = await response.json();
    renderSiteContent(content);
  } catch (error) {
    console.error("Could not load published homepage content.", error);
  }
}

try {
  const savedBasket = JSON.parse(localStorage.getItem("godelivery-basket") || "[]");
  if (Array.isArray(savedBasket)) {
    basket = new Map(savedBasket.filter((entry) =>
      Array.isArray(entry) && typeof entry[0] === "string" &&
      Number.isInteger(entry[1]) && entry[1] > 0
    ));
  }
} catch (error) {
  console.error("Could not restore the saved shopping basket.", error);
}

orderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = orderForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  showState(orderState, "กำลังส่งคำสั่งซื้อ…");
  const formData = new FormData(orderForm);
  const payload = {
    customer: String(formData.get("customer") || "").trim(),
    address: String(formData.get("address") || "").trim(),
    address1: String(formData.get("address1") || "").trim(),
    postcode: String(formData.get("postcode") || "").trim(),
    phone_number: String(formData.get("phone_number") || "").trim(),
    remark: String(formData.get("remark") || "").trim(),
    privacy_consent: formData.get("privacy_consent") === "on",
    items: Array.from(basket, ([product_id, quantity]) => ({ product_id, quantity })),
  };
  try {
    const response = await fetch("/api/v1/site/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "ส่งคำสั่งซื้อไม่สำเร็จ");
    basket.clear();
    persistBasket();
    orderForm.reset();
    renderBasket();
    showState(orderState, `${result.message} เลขที่รายการ ${result.ordernumber}`);
  } catch (error) {
    showState(orderState, error.message, true);
  } finally {
    submitButton.disabled = basket.size === 0;
  }
});

memberForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = memberForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  showState(memberState, "กำลังบันทึกข้อมูลสมาชิก…");
  const formData = new FormData(memberForm);
  const email = String(formData.get("email") || "").trim();
  const payload = {
    customer: String(formData.get("customer") || "").trim(),
    phone_number: String(formData.get("phone_number") || "").trim(),
    email: email || null,
    privacy_consent: formData.get("privacy_consent") === "on",
  };
  try {
    const response = await fetch("/api/v1/site/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "สมัครสมาชิกไม่สำเร็จ");
    memberForm.reset();
    showState(memberState, `บันทึกข้อมูลสมาชิกแล้ว เลขสมาชิก ${result.membernumber}`);
  } catch (error) {
    showState(memberState, error.message, true);
  } finally {
    submitButton.disabled = false;
  }
});

renderBasket();
loadSiteContent();
