const faqList = document.querySelector("#faq-list");
const faqsEmpty = document.querySelector("#faqs-empty");
const basketCount = document.querySelector("#basket-count");

function makeElement(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

function renderFAQs(faqs) {
  const activeFAQs = faqs.filter((faq) => faq.active !== false);
  faqsEmpty.hidden = activeFAQs.length > 0;
  faqList.replaceChildren(...activeFAQs.map((faq) => {
    const item = document.createElement("details");
    item.append(makeElement("summary", faq.question), makeElement("p", faq.answer));
    return item;
  }));
}

try {
  const saved = JSON.parse(localStorage.getItem("godelivery-basket") || "[]");
  if (Array.isArray(saved)) {
    basketCount.textContent = String(saved.reduce(
      (total, entry) => total + (Array.isArray(entry) && Number.isInteger(entry[1]) && entry[1] > 0 ? entry[1] : 0),
      0,
    ));
  }
} catch (error) {
  console.error("Could not read the saved shopping basket.", error);
}

async function loadFAQs() {
  try {
    const response = await fetch("/api/v1/site/content", { cache: "no-store" });
    if (!response.ok) throw new Error("load failed");
    renderFAQs((await response.json()).faqs || []);
  } catch (error) {
    console.error("Could not load FAQs.", error);
  }
}

loadFAQs();
