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

function createProductCard(product) {
  const detailUrl = `/products/${encodeURIComponent(product.product_id)}`;
  const price = getPrice(product);
  const discount = product.sale_price && product.regular_price > 0 && product.sale_price < product.regular_price
    ? Math.round((1 - product.sale_price / product.regular_price) * 100)
    : 0;
  const card = makeElement("article", "store-product-card");

  const top = makeElement("div", "store-card-top");
  top.append(
    makeElement("span", "store-code", `รหัส ${product.product_id}`),
    makeElement(
      "span",
      product.stock_quantity > 0 ? "store-stock" : "store-stock sold-out",
      product.stock_quantity > 0 ? "พร้อมส่ง" : "สินค้าหมด",
    ),
  );
  card.append(top);

  const media = makeElement("a", "store-product-media");
  media.href = detailUrl;
  media.setAttribute("aria-label", `ดูรายละเอียด ${product.name}`);
  const placeholder = () => {
    const span = makeElement("span", "store-product-placeholder", "GO");
    span.setAttribute("aria-hidden", "true");
    return span;
  };
  if (product.image_url) {
    const image = document.createElement("img");
    image.src = product.image_url;
    image.alt = product.name;
    image.loading = "lazy";
    image.onerror = () => { image.remove(); media.prepend(placeholder()); };
    media.append(image);
  } else {
    media.append(placeholder());
  }
  if (discount > 0) media.append(makeElement("span", "store-discount", `-${discount}%`));
  card.append(media);

  const name = makeElement("h3");
  const nameLink = makeElement("a", "", product.name);
  nameLink.href = detailUrl;
  name.append(nameLink);
  card.append(name);

  const priceBox = makeElement("div", "store-price");
  priceBox.append(makeElement("strong", "store-current-price", formatPrice(price)));
  if (discount > 0) priceBox.append(makeElement("del", "store-old-price", formatPrice(product.regular_price)));
  card.append(priceBox);

  const actions = makeElement("div", "store-actions");
  const detailLink = makeElement("a", "store-detail-button", "รายละเอียด");
  detailLink.href = detailUrl;
  const inBasket = basket.get(product.product_id) || 0;
  const canBuy = product.stock_quantity > inBasket;
  const buyButton = makeElement(
    "button",
    "store-buy-button",
    product.stock_quantity < 1 ? "สินค้าหมด" : canBuy ? "ใส่ตะกร้า" : "เต็มจำนวนแล้ว",
  );
  buyButton.type = "button";
  buyButton.disabled = !canBuy;
  buyButton.addEventListener("click", () => addToBasket(product.product_id));
  actions.append(detailLink, buyButton);
  card.append(actions);
  return card;
}

function renderProducts(products) {
  const activeProducts = products.filter((product) => product.active);
  productById.clear();
  for (const product of activeProducts) productById.set(product.product_id, product);
  productsEmpty.hidden = activeProducts.length > 0;
  productGrid.replaceChildren(...activeProducts.slice(0, 8).map(createProductCard));
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
  for (const sectionName of ["company"]) {
    const section = content[sectionName] || {};
    const title = document.querySelector(`#${sectionName}-title`);
    const body = document.querySelector(`#${sectionName}-body`);
    if (title) title.textContent = section.title || "";
    if (body) body.textContent = section.body || "";
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
