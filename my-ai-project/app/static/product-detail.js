const BASKET_KEY = "godelivery-basket";
const $ = (selector) => document.querySelector(selector);

function formatPrice(value) {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    maximumFractionDigits: 2,
  }).format(value);
}

function readBasket() {
  try {
    const saved = JSON.parse(localStorage.getItem(BASKET_KEY) || "[]");
    if (!Array.isArray(saved)) return new Map();
    return new Map(saved.filter((entry) =>
      Array.isArray(entry) && typeof entry[0] === "string" &&
      Number.isInteger(entry[1]) && entry[1] > 0
    ));
  } catch (error) {
    console.error("Could not read the saved shopping basket.", error);
    return new Map();
  }
}

function updateBasketCount() {
  const count = Array.from(readBasket().values()).reduce((total, quantity) => total + quantity, 0);
  $("#basket-count").textContent = String(count);
}

function productIdFromPath() {
  const raw = window.location.pathname.replace(/^\/products\//, "").replace(/\/$/, "");
  try {
    return decodeURIComponent(raw);
  } catch (error) {
    return "";
  }
}

function showMessage(text) {
  const message = $("#detail-message");
  message.textContent = text;
  message.hidden = !text;
}

function refreshBuyButton(product) {
  const button = $("#detail-buy");
  const inBasket = readBasket().get(product.product_id) || 0;
  const canBuy = product.stock_quantity > inBasket;
  button.disabled = !canBuy;
  button.textContent = product.stock_quantity < 1 ? "สินค้าหมด" : canBuy ? "ใส่ตะกร้า" : "เต็มจำนวนแล้ว";
}

function renderProduct(product) {
  document.title = `${product.name} | 711SHOPPING`;
  $("#detail-crumb").textContent = product.name;
  $("#detail-code").textContent = `รหัส ${product.product_id}`;
  const stock = $("#detail-stock");
  stock.textContent = product.stock_quantity > 0 ? `พร้อมส่ง · เหลือ ${product.stock_quantity} ชิ้น` : "สินค้าหมด";
  stock.classList.toggle("sold-out", product.stock_quantity < 1);
  $("#detail-name").textContent = product.name;
  const onSale = product.sale_price != null && product.sale_price < product.regular_price;
  $("#detail-price").textContent = formatPrice(onSale ? product.sale_price : product.regular_price);
  const old = $("#detail-old");
  old.hidden = !onSale;
  old.textContent = onSale ? formatPrice(product.regular_price) : "";
  $("#detail-description").textContent = product.description || "สินค้าแนะนำจาก 711SHOPPING";

  const media = $("#detail-media");
  media.replaceChildren();
  if (product.image_url) {
    const image = document.createElement("img");
    image.src = product.image_url;
    image.alt = product.name;
    media.append(image);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "store-product-placeholder";
    placeholder.textContent = "GO";
    media.append(placeholder);
  }

  refreshBuyButton(product);
  $("#detail-buy").onclick = () => {
    const basket = readBasket();
    const quantity = basket.get(product.product_id) || 0;
    if (quantity >= product.stock_quantity) return;
    basket.set(product.product_id, quantity + 1);
    try {
      localStorage.setItem(BASKET_KEY, JSON.stringify(Array.from(basket.entries())));
    } catch (error) {
      console.error("Could not save the shopping basket.", error);
      showMessage("บันทึกตะกร้าสินค้าไม่ได้ กรุณาอนุญาตการจัดเก็บข้อมูลในเบราว์เซอร์");
      return;
    }
    showMessage("");
    updateBasketCount();
    refreshBuyButton(product);
  };
  $("#detail").hidden = false;
  $("#detail-status").hidden = true;
}

async function load() {
  const status = $("#detail-status");
  try {
    const response = await fetch("/api/v1/site/content", { cache: "no-store" });
    if (!response.ok) throw new Error(`Catalog request failed (${response.status}).`);
    const content = await response.json();
    const id = productIdFromPath();
    const product = (content.products || []).find((item) => item.active && item.product_id === id);
    if (!product) {
      status.textContent = "ไม่พบสินค้านี้ หรือสินค้าถูกนำออกจากหน้าเว็บแล้ว";
      return;
    }
    renderProduct(product);
  } catch (error) {
    console.error("Could not load the product.", error);
    status.textContent = "โหลดข้อมูลสินค้าไม่สำเร็จ กรุณาลองใหม่ภายหลัง";
  }
}

window.addEventListener("storage", updateBasketCount);
updateBasketCount();
load();
