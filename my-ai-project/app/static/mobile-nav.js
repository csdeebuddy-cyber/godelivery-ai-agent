(() => {
  const ICONS = {
    home: '<path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    catalog: '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    chat: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01"/>',
    cart: '<path d="M4 5h2l2 11h10l2-8H7"/><circle cx="10" cy="20" r="1"/><circle cx="17" cy="20" r="1"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  };
  const path = location.pathname;
  const items = [
    { key: "home", label: "หน้าแรก", href: "/", active: path === "/" },
    { key: "catalog", label: "แคตตาล็อก", href: "/product", active: path.startsWith("/product") },
    { key: "chat", label: "Chat & Shop", href: "/chatandshop", center: true },
    { key: "cart", label: "ตะกร้า", href: "/cart", active: path === "/cart", badge: true },
    { key: "user", label: "สมาชิก", href: "/user-profile", active: path.startsWith("/user") },
  ];

  function basketCount() {
    try {
      const saved = JSON.parse(localStorage.getItem("godelivery-basket") || "[]");
      return Array.isArray(saved)
        ? saved.reduce((total, entry) => total + (Array.isArray(entry) && Number.isInteger(entry[1]) && entry[1] > 0 ? entry[1] : 0), 0)
        : 0;
    } catch (error) {
      return 0;
    }
  }

  const nav = document.createElement("nav");
  nav.className = "bottom-nav";
  nav.setAttribute("aria-label", "เมนูมือถือ");
  const count = basketCount();
  nav.innerHTML = items.map((item) => `
    <a href="${item.href}" class="${item.center ? "bottom-nav-center" : ""}${item.active ? " active" : ""}"${item.active ? ' aria-current="page"' : ""}>
      <span class="bottom-nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[item.key]}</svg>${item.badge && count > 0 ? `<b class="bottom-nav-badge">${count > 99 ? "99+" : count}</b>` : ""}</span>
      <span class="bottom-nav-label">${item.label}</span>
    </a>`).join("");
  document.body.append(nav);
})();
