const dashboardError = document.querySelector("#dashboard-error");

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
  })
  .catch((error) => {
    dashboardError.textContent = error.message;
    dashboardError.hidden = false;
  });
