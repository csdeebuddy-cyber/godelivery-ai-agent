const productGrid = document.querySelector("#product-grid");
const productsEmpty = document.querySelector("#products-empty");
const promotionList = document.querySelector("#promotion-list");


const basketCount = document.querySelector("#basket-count");
const productById = new Map();
let basket = new Map();

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
    return true;
  } catch (error) {
    console.error("Could not save the shopping basket.", error);
    return false;
  }
}

function addToBasket(productId) {
  const product = productById.get(productId);
  const quantity = basket.get(productId) || 0;
  if (!product || quantity >= product.stock_quantity) return;
  basket.set(productId, quantity + 1);
  if (persistBasket()) window.location.assign("/cart");
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

function updateBasketCount() {
  basketCount.textContent = String(Array.from(basket.values()).reduce((total, quantity) => total + quantity, 0));
}

function renderSiteContent(content) {
  for (const sectionName of ["company", "terms", "security", "shipping", "returns"]) {
    const section = content[sectionName] || {};
    const title = document.querySelector(`#${sectionName}-title`);
    const body = document.querySelector(`#${sectionName}-body`);
    title.textContent = section.title || "";
    body.textContent = section.body || "";
  }

  renderProducts(content.products || []);
  renderPromotions(content.promotions || []);
  updateBasketCount();
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

updateBasketCount();
loadSiteContent();
