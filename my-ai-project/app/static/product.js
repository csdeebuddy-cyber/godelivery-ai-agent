const productGrid = document.querySelector("#product-grid");
const searchInput = document.querySelector("#product-search");
const sortSelect = document.querySelector("#product-sort");
const catalogCount = document.querySelector("#catalog-count");
const catalogEmpty = document.querySelector("#catalog-empty");
const catalogError = document.querySelector("#catalog-error");
const basketCount = document.querySelector("#basket-count");
const catalogBasketCount = document.querySelector("#catalog-basket-count");
let publishedProducts = [];

function priceFor(product) {
  return product.sale_price ?? product.regular_price;
}

function discountFor(product) {
  if (!product.sale_price || product.regular_price <= 0 || product.sale_price >= product.regular_price) {
    return 0;
  }
  return Math.round((1 - product.sale_price / product.regular_price) * 100);
}

function formatPrice(value) {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    maximumFractionDigits: 2,
  }).format(value);
}

function readBasket() {
  try {
    const saved = JSON.parse(localStorage.getItem("godelivery-basket") || "[]");
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
  const basket = readBasket();
  const count = Array.from(basket.values()).reduce((total, quantity) => total + quantity, 0);
  basketCount.textContent = String(count);
  catalogBasketCount.textContent = String(count);
}

function buyProduct(product) {
  const basket = readBasket();
  const quantity = basket.get(product.product_id) || 0;
  if (quantity >= product.stock_quantity) {
    renderProducts();
    return;
  }
  basket.set(product.product_id, quantity + 1);
  try {
    localStorage.setItem("godelivery-basket", JSON.stringify(Array.from(basket.entries())));
  } catch (error) {
    console.error("Could not save the shopping basket.", error);
    catalogError.hidden = false;
    catalogError.textContent = "บันทึกตะกร้าสินค้าไม่ได้ กรุณาอนุญาตการจัดเก็บข้อมูลในเบราว์เซอร์";
    return;
  }
  window.location.assign("/#basket");
}

function createProductCard(product, basket) {
  const card = document.createElement("article");
  card.className = "store-product-card";
  const media = document.createElement("div");
  media.className = "store-product-media";
  if (product.image_url) {
    const image = document.createElement("img");
    image.src = product.image_url;
    image.alt = product.name;
    image.loading = "lazy";
    image.onerror = () => {
      image.remove();
      const placeholder = document.createElement("span");
      placeholder.className = "store-product-placeholder";
      placeholder.textContent = "GO";
      placeholder.setAttribute("aria-hidden", "true");
      media.prepend(placeholder);
    };
    media.append(image);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "store-product-placeholder";
    placeholder.textContent = "GO";
    placeholder.setAttribute("aria-hidden", "true");
    media.append(placeholder);
  }
  const discount = discountFor(product);
  if (discount > 0) {
    const badge = document.createElement("span");
    badge.className = "store-discount";
    badge.textContent = `-${discount}%`;
    media.append(badge);
  }
  card.append(media);

  const info = document.createElement("div");
  info.className = "store-product-info";
  const productId = document.createElement("small");
  productId.className = "store-product-id";
  productId.textContent = `รหัสสินค้า ${product.product_id}`;
  info.append(productId);
  const name = document.createElement("h3");
  name.textContent = product.name;
  info.append(name);
  const description = document.createElement("p");
  description.className = "store-product-description";
  description.textContent = product.description || "สินค้าแนะนำจาก GoDelivery";
  info.append(description);

  const stock = document.createElement("small");
  stock.className = product.stock_quantity > 0 ? "store-stock" : "store-stock sold-out";
  stock.textContent = product.stock_quantity > 0
    ? `พร้อมส่ง · เหลือ ${product.stock_quantity} ชิ้น`
    : "สินค้าหมดชั่วคราว";
  info.append(stock);

  const price = document.createElement("div");
  price.className = "store-price";
  const oldPrice = document.createElement("small");
  oldPrice.className = "store-old-price";
  if (discount > 0) {
    const crossedPrice = document.createElement("del");
    crossedPrice.textContent = formatPrice(product.regular_price);
    oldPrice.append(crossedPrice);
  }
  price.append(oldPrice);
  const currentPrice = document.createElement("strong");
  currentPrice.className = "store-current-price";
  currentPrice.textContent = `เริ่มต้น ${formatPrice(priceFor(product))}`;
  price.append(currentPrice);
  info.append(price);

  const buyButton = document.createElement("button");
  buyButton.type = "button";
  buyButton.className = "store-buy-button";
  const currentQuantity = basket.get(product.product_id) || 0;
  const canBuy = product.stock_quantity > currentQuantity;
  buyButton.textContent = product.stock_quantity < 1
    ? "สินค้าหมด"
    : canBuy
      ? "ซื้อเลย"
      : "สินค้าเต็มจำนวนในตะกร้า";
  buyButton.disabled = !canBuy;
  buyButton.addEventListener("click", () => buyProduct(product));
  info.append(buyButton);
  card.append(info);
  return card;
}

function renderProducts() {
  const query = searchInput.value.trim().toLocaleLowerCase("th");
  const products = publishedProducts.filter((product) =>
    `${product.product_id} ${product.name} ${product.description}`
      .toLocaleLowerCase("th")
      .includes(query)
  );
  const sortBy = sortSelect.value;
  if (sortBy === "price-low") {
    products.sort((first, second) => priceFor(first) - priceFor(second));
  } else if (sortBy === "price-high") {
    products.sort((first, second) => priceFor(second) - priceFor(first));
  } else if (sortBy === "discount") {
    products.sort((first, second) => discountFor(second) - discountFor(first));
  }

  catalogCount.textContent = `แสดง ${products.length} จาก ${publishedProducts.length} รายการ`;
  catalogEmpty.hidden = products.length > 0;
  catalogEmpty.textContent = query
    ? "ไม่พบสินค้าที่ตรงกับคำค้น ลองค้นหาด้วยชื่อหรือรหัสสินค้าอื่น"
    : "ขณะนี้ยังไม่มีสินค้าที่เผยแพร่";
  const basket = readBasket();
  productGrid.replaceChildren(...products.map((product) => createProductCard(product, basket)));
}

async function loadProducts() {
  try {
    const response = await fetch("/api/v1/site/content", { cache: "no-store" });
    if (!response.ok) throw new Error(`Catalog request failed (${response.status}).`);
    const content = await response.json();
    publishedProducts = Array.isArray(content.products)
      ? content.products.filter((product) => product.active)
      : [];
    renderProducts();
  } catch (error) {
    console.error("Could not load the published product catalog.", error);
    catalogCount.textContent = "โหลดรายการสินค้าไม่สำเร็จ";
    catalogError.textContent = "ไม่สามารถเชื่อมต่อรายการสินค้าได้ในขณะนี้ กรุณาลองใหม่ภายหลัง";
    catalogError.hidden = false;
  }
}

searchInput.addEventListener("input", renderProducts);
sortSelect.addEventListener("change", renderProducts);
window.addEventListener("storage", updateBasketCount);
updateBasketCount();
loadProducts();
