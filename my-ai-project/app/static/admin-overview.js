(() => {
  const LOW_STOCK_LIMIT = 5;
  const set = (id, value) => {
    const node = document.querySelector(id);
    if (node) node.textContent = String(value);
  };

  async function loadOverview() {
    try {
      const response = await fetch("/api/v1/site/content", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const content = await response.json();
      const products = (content.products || []).filter((product) => product.active);
      set("#kpi-active-products", products.length);
      set("#kpi-sold-out", products.filter((product) => product.stock_quantity < 1).length);
      set("#kpi-low-stock", products.filter(
        (product) => product.stock_quantity > 0 && product.stock_quantity <= LOW_STOCK_LIMIT,
      ).length);
      set("#kpi-promotions", (content.promotions || []).filter((promotion) => promotion.active).length);
      set("#kpi-faqs", (content.faqs || []).filter((faq) => faq.active !== false).length);
    } catch (error) {
      console.error("Could not load the dashboard overview.", error);
    }
  }

  const links = Array.from(document.querySelectorAll(".admin-sidebar a[href^='#']"));
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      for (const link of links) link.classList.toggle("active", link.hash === `#${entry.target.id}`);
    }
  }, { rootMargin: "-30% 0px -60% 0px" });
  for (const link of links) {
    const target = document.querySelector(link.hash);
    if (target) observer.observe(target);
  }

  loadOverview();
})();
