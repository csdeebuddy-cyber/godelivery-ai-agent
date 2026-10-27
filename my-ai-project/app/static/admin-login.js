const setupNotice = document.querySelector("#setup-notice");
const loginButton = document.querySelector("#google-login");
const loginAlert = document.querySelector("#login-alert");

const errors = {
  sign_in_failed: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
  state_invalid: "เซสชันเข้าสู่ระบบหมดอายุหรือไม่ถูกต้อง กรุณาเริ่มใหม่",
  not_authorized: "บัญชีนี้ไม่ได้รับอนุญาตให้เข้าหลังบ้าน",
};

const errorCode = new URLSearchParams(window.location.search).get("error");
if (errorCode && errors[errorCode]) {
  loginAlert.textContent = errors[errorCode];
  loginAlert.hidden = false;
}

fetch("/api/v1/admin/status")
  .then(async (response) => {
    if (!response.ok) throw new Error("ไม่สามารถตรวจสอบการตั้งค่า SSO ได้");
    return response.json();
  })
  .then((status) => {
    if (status.sso_configured) {
      setupNotice.textContent = "Google SSO พร้อมใช้งาน และอนุญาตเฉพาะ smpmfast@gmail.com";
      setupNotice.classList.add("notice-warning");
      loginButton.classList.remove("disabled");
      loginButton.removeAttribute("aria-disabled");
      return;
    }
    setupNotice.textContent =
      "ยังไม่ได้ตั้งค่า Google OAuth Client และ session secret ใน Secret Manager จึงยังเข้าสู่ระบบไม่ได้";
  })
  .catch((error) => {
    setupNotice.textContent = error.message;
    setupNotice.classList.add("notice-error");
  });
