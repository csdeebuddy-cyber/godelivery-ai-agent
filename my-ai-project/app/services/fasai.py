"""Fasai (ฟ้าใส) agent logic: turn timing, session state, and tool handling."""

import logging
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from app.config import settings
from app.services.site_content import get_site_content

logger = logging.getLogger(__name__)

PERSONA_NAME = "ฟ้าใส"
LISTEN_DELAY_S = 1.8
IDLE_TIMEOUT_S = 120.0
CHECKOUT_URL = "/cart"
MAX_LINE_QUANTITY = 10

WAIT_NOTICE_PROMPT = (
    "[ระบบ] ลูกค้าพูดจบแล้วแต่ยังประมวลผลคำตอบไม่ได้ "
    "ให้พูดเพียงประโยคเดียวว่า “รอซักครู่นะคะลูกค้า” แล้วหยุดพูด"
)
ASK_REPEAT_PROMPT = (
    "[ระบบ] ยังประมวลผลคำพูดของลูกค้าไม่ได้ "
    "ให้พูดเพียงประโยคเดียวว่า “รบกวนลูกค้าแจ้งอีกครั้งได้ไหมคะ” แล้วหยุดพูด"
)
UNANSWERED_HINT = (
    "[ระบบ] คำพูดของลูกค้าที่ยังไม่ได้ตอบ: “{text}” "
    "เมื่อลูกค้าพูดครั้งถัดไป ให้ตีความรวมกับข้อความนี้เป็นชุดเดียวกันก่อนตอบ"
)


class TurnWatchdog:
    """Tracks an unanswered customer turn.

    Live VAD already waits LISTEN_DELAY_S of silence before the model answers.
    If the model has not started answering one further LISTEN_DELAY_S later we
    ask the customer to wait, and one window after that we ask them to repeat.
    """

    def __init__(self, delay_s: float = LISTEN_DELAY_S) -> None:
        self.delay_s = delay_s
        self._last_speech: float | None = None
        self._notice_sent = False
        self._repeat_sent = False
        self._filler_turn = False
        self._pending: list[str] = []

    @property
    def unanswered_text(self) -> str:
        return "".join(self._pending).strip()

    def on_user_speech(self, text: str, now: float) -> None:
        self._pending.append(text)
        self._last_speech = now
        self._notice_sent = False
        self._repeat_sent = False

    def on_model_output(self) -> None:
        if self._filler_turn:
            return
        self._last_speech = None
        self._pending.clear()

    def on_turn_complete(self) -> None:
        self._filler_turn = False

    def poll(self, now: float) -> str | None:
        if self._last_speech is None:
            return None
        elapsed = now - self._last_speech
        if not self._notice_sent and elapsed >= 2 * self.delay_s:
            self._notice_sent = True
            self._filler_turn = True
            return "wait_notice"
        if self._notice_sent and not self._repeat_sent and elapsed >= 3 * self.delay_s:
            self._repeat_sent = True
            self._filler_turn = True
            return "ask_repeat"
        return None


class IdleTimer:
    def __init__(self, timeout_s: float = IDLE_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s
        self._last_activity = 0.0

    def touch(self, now: float) -> None:
        self._last_activity = now

    def expired(self, now: float) -> bool:
        return now - self._last_activity >= self.timeout_s


@dataclass
class AgentSession:
    ticket_no: str | None = None
    cart: dict[str, int] = field(default_factory=dict)
    transcript: list[dict[str, str]] = field(default_factory=list)
    pending_redirect: str | None = None
    callback_logged: bool = False

    def add_transcript(self, role: str, text: str, at: str) -> None:
        if not text.strip():
            return
        if self.transcript and self.transcript[-1]["role"] == role:
            self.transcript[-1]["text"] += text
        else:
            self.transcript.append({"role": role, "text": text, "at": at})

    def cart_lines(self, products: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        lines = []
        for product_id, quantity in self.cart.items():
            product = products.get(product_id, {})
            price = product.get("sale_price") or product.get("regular_price") or 0
            lines.append(
                {
                    "product_id": product_id,
                    "name": product.get("name", product_id),
                    "quantity": quantity,
                    "unit_price": price,
                    "line_total": price * quantity,
                }
            )
        return lines


def published_products() -> dict[str, dict[str, Any]]:
    try:
        products = get_site_content().get("products", [])
    except Exception:
        logger.warning("Could not load the published catalog for Fasai.", exc_info=True)
        return {}
    return {p["product_id"]: p for p in products if p.get("active")}


def catalog_prompt() -> str:
    products = published_products()
    if not products:
        return "รายการสินค้าที่หยิบใส่ตะกร้าได้: ยังไม่มีสินค้าที่เผยแพร่ ห้ามเสนอขายหรือเรียก add_to_cart"
    lines = []
    for product in products.values():
        price = product.get("sale_price") or product.get("regular_price")
        lines.append(
            f"- รหัส {product['product_id']} | {product['name']} | ราคา {price} บาท | "
            f"คงเหลือ {product.get('stock_quantity', 0)} | รายละเอียด: {product.get('description', '')}"
        )
    return "รายการสินค้าที่หยิบใส่ตะกร้าได้ (ข้อมูลต้นทางเท่านั้น):\n" + "\n".join(lines)


def tool_config() -> list[types.Tool]:
    schema = types.Schema
    kind = types.Type
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="add_to_cart",
                    description="หยิบสินค้าใส่ตะกร้าให้ลูกค้าเมื่อลูกค้ายืนยันว่าจะรับสินค้า",
                    parameters=schema(
                        type=kind.OBJECT,
                        properties={
                            "product_id": schema(type=kind.STRING, description="รหัสสินค้าจากรายการ"),
                            "quantity": schema(type=kind.INTEGER, description="จำนวนที่ลูกค้าต้องการ"),
                        },
                        required=["product_id", "quantity"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="go_checkout",
                    description="พาลูกค้าไปหน้าชำระเงิน เรียกหลังทวนรายการสินค้าและแจ้งลูกค้าแล้วเท่านั้น",
                ),
                types.FunctionDeclaration(
                    name="log_callback",
                    description="บันทึกเรื่องให้หน่วยงานที่เกี่ยวข้องติดต่อกลับ เมื่อข้อมูลไม่เพียงพอจะตอบ",
                    parameters=schema(
                        type=kind.OBJECT,
                        properties={
                            "reason": schema(type=kind.STRING, description="หัวข้อที่ลูกค้าสอบถาม"),
                            "details": schema(type=kind.STRING, description="รายละเอียดที่ลูกค้าแจ้ง"),
                        },
                        required=["reason"],
                    ),
                ),
            ]
        )
    ]


def run_tool(
    name: str,
    args: dict[str, Any],
    session: AgentSession,
    *,
    save_callback: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Execute a model tool call. Returns (response for the model, event for the browser)."""
    products = published_products()
    if name == "add_to_cart":
        product_id = str(args.get("product_id", "")).strip()
        product = products.get(product_id)
        try:
            quantity = int(args.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 0
        if product is None:
            return {"ok": False, "error": "ไม่พบสินค้านี้ในรายการที่เผยแพร่"}, None
        if not 1 <= quantity <= MAX_LINE_QUANTITY:
            return {"ok": False, "error": f"จำนวนต้องอยู่ระหว่าง 1 ถึง {MAX_LINE_QUANTITY}"}, None
        stock = int(product.get("stock_quantity", 0))
        already = session.cart.get(product_id, 0)
        if already + quantity > stock:
            return {"ok": False, "error": f"สินค้าคงเหลือ {stock} ชิ้น"}, None
        session.cart[product_id] = already + quantity
        lines = session.cart_lines(products)
        return (
            {"ok": True, "cart": lines, "total": sum(line["line_total"] for line in lines)},
            {"type": "cart_add", "product_id": product_id, "quantity": quantity},
        )
    if name == "go_checkout":
        if not session.cart:
            return {"ok": False, "error": "ตะกร้ายังว่างอยู่"}, None
        session.pending_redirect = CHECKOUT_URL
        return {"ok": True, "message": "ระบบจะพาลูกค้าไปหน้าชำระเงินหลังพูดจบ"}, None
    if name == "log_callback":
        reason = str(args.get("reason", "")).strip()
        if not reason or session.ticket_no is None:
            return {"ok": False, "error": "ยังไม่มีเลขตั๋วหรือไม่มีหัวข้อ"}, None
        save_callback(session.ticket_no, reason, str(args.get("details", "")))
        session.callback_logged = True
        return {"ok": True, "message": "บันทึกเรื่องให้เจ้าหน้าที่ติดต่อกลับแล้ว"}, None
    return {"ok": False, "error": "ไม่รู้จักเครื่องมือนี้"}, None


def live_input_config() -> types.RealtimeInputConfig:
    return types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            silence_duration_ms=int(LISTEN_DELAY_S * 1000),
        )
    )


def trial_price() -> int:
    return settings.FASAI_TRIAL_PRICE_THB


CHECKOUT_VOICE_SECTION = """## การขอข้อมูลจัดส่ง (หน้าชำระเงิน)

ก่อนขอข้อมูลทุกครั้งต้องแจ้งว่า "สายนี้มีการบันทึกบทสนทนา เพื่อพัฒนาการให้บริการของฟ้าใสด้วยนะคะ" จากนั้นถามทีละข้อ:
1. ชื่อผู้รับ  2. ที่อยู่ บ้านเลขที่  3. ตำบล/อำเภอ/จังหวัด  4. รหัสไปรษณีย์  5. เบอร์โทร
เมื่อครบ แจ้งยอดเก็บเงินปลายทางและว่ารอรับสินค้า 1-3 วัน ขนส่งแฟลช แล้วแจ้งให้ลูกค้าตรวจรายการสั่งซื้อและกดใส่รหัสผ่าน 6 ตัวบนหน้าจอ (ห้ามให้พูดรหัสออกเสียง)"""

CHECKOUT_PAGE_SECTION = """## หลังพาลูกค้าไปหน้าชำระเงิน

ระบบยังไม่รองรับการรับที่อยู่ทางเสียง ให้แจ้งลูกค้าว่ากรอกชื่อ ที่อยู่ รหัสไปรษณีย์ และเบอร์โทรเองบนหน้าจอได้เลย ชำระเงินปลายทาง ห้ามขอที่อยู่หรือเบอร์โทรทางเสียง"""


def build_instructions(base: str) -> str:
    section = CHECKOUT_VOICE_SECTION if settings.FASAI_CHECKOUT_VOICE_ENABLED else CHECKOUT_PAGE_SECTION
    return base.replace("{{TRIAL_PRICE}}", str(trial_price())).replace("{{CHECKOUT_SECTION}}", section)
