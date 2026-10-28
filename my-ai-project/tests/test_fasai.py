import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.services import fasai, tickets
from app.services.fasai import AgentSession, TurnWatchdog, run_tool

PRODUCTS = {
    "p1": {"product_id": "p1", "name": "Jar", "sale_price": 590, "stock_quantity": 3, "active": True}
}


class WatchdogTests(unittest.TestCase):
    def test_wait_notice_then_ask_repeat(self) -> None:
        dog = TurnWatchdog(delay_s=1.8)
        dog.on_user_speech("hello", 0.0)
        self.assertIsNone(dog.poll(3.0))
        self.assertEqual(dog.poll(3.7), "wait_notice")
        self.assertIsNone(dog.poll(4.0))
        self.assertEqual(dog.poll(5.5), "ask_repeat")
        self.assertIsNone(dog.poll(9.0))
        self.assertEqual(dog.unanswered_text, "hello")

    def test_model_answer_clears_pending(self) -> None:
        dog = TurnWatchdog()
        dog.on_user_speech("hi", 0.0)
        dog.on_model_output()
        self.assertIsNone(dog.poll(10.0))
        self.assertEqual(dog.unanswered_text, "")

    def test_filler_turn_keeps_unanswered(self) -> None:
        dog = TurnWatchdog()
        dog.on_user_speech("hi", 0.0)
        self.assertEqual(dog.poll(3.7), "wait_notice")
        dog.on_model_output()
        dog.on_turn_complete()
        self.assertEqual(dog.unanswered_text, "hi")

    def test_silence_guard_hello_then_hangup(self) -> None:
        guard = fasai.SilenceGuard()
        guard.on_agent_audio(0.0, 48000)  # plays until t=1.0
        self.assertIsNone(guard.poll(0.5))
        guard.on_agent_turn_complete(0.5)
        self.assertIsNone(guard.poll(2.9))
        self.assertEqual(guard.poll(3.0), "hello")
        guard.on_agent_audio(3.1, 24000)  # hello plays until t=3.6
        guard.on_agent_turn_complete(3.2)
        self.assertIsNone(guard.poll(4.5))
        self.assertEqual(guard.poll(4.7), "hangup")
        self.assertIsNone(guard.poll(10.0))

    def test_silence_guard_resets_on_customer(self) -> None:
        guard = fasai.SilenceGuard()
        guard.on_agent_turn_complete(0.0)
        self.assertEqual(guard.poll(2.0), "hello")
        guard.on_customer_activity()
        guard.on_agent_turn_complete(5.0)
        self.assertIsNone(guard.poll(6.0))
        self.assertEqual(guard.poll(7.0), "hello")

    def test_silence_guard_hello_never_completes(self) -> None:
        guard = fasai.SilenceGuard()
        guard.on_agent_turn_complete(0.0)
        self.assertEqual(guard.poll(2.0), "hello")
        self.assertEqual(guard.poll(8.0), "hangup")

    def test_end_call_and_instructions(self) -> None:
        session = fasai.AgentSession()
        _, _ = fasai.run_tool("end_call", {}, session, save_callback=lambda *a, **k: None)
        self.assertEqual(session.pending_redirect, "/")
        self.assertEqual(session.close_reason, "customer_ended")
        text = fasai.build_instructions("{{GREETING}}|{{CLOSING}}")
        self.assertEqual(text, f"{fasai.GREETING_TEXT}|{fasai.CLOSING_TEXT}")
        self.assertEqual(fasai.CLOSING_TEXT, "ขอบคุณที่ใช้บริการนะคะ สวัสดีค่ะ")


class TicketTests(unittest.TestCase):
    def test_format(self) -> None:
        now = datetime(2025, 3, 4, 5, tzinfo=timezone.utc)
        self.assertEqual(tickets.format_ticket_no(now, 7), "FS-250304-0007")

    def test_memory_ticket_sequence_and_close(self) -> None:
        with patch.object(tickets, "_firestore", return_value=None):
            first = tickets.create_ticket("voice")
            second = tickets.create_ticket("voice")
            self.assertNotEqual(first["ticket_no"], second["ticket_no"])
            tickets.close_ticket(first["ticket_no"], "idle_timeout", [{"role": "agent", "text": "x"}], [])
            stored = tickets.get_ticket(first["ticket_no"])
            self.assertEqual(stored["status"], "closed")


class ToolTests(unittest.TestCase):
    def run_tool(self, name, args, session):
        saved = []
        with patch.object(fasai, "published_products", return_value=PRODUCTS):
            result = run_tool(name, args, session, save_callback=lambda *a: saved.append(a))
        return result, saved

    def test_add_to_cart(self) -> None:
        session = AgentSession()
        (result, event), _ = self.run_tool("add_to_cart", {"product_id": "p1", "quantity": 2}, session)
        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], 1180)
        self.assertEqual(event["type"], "cart_add")

    def test_add_to_cart_rejects_over_stock_and_unknown(self) -> None:
        session = AgentSession()
        (over, _), _ = self.run_tool("add_to_cart", {"product_id": "p1", "quantity": 4}, session)
        (unknown, _), _ = self.run_tool("add_to_cart", {"product_id": "zz", "quantity": 1}, session)
        self.assertFalse(over["ok"])
        self.assertFalse(unknown["ok"])
        self.assertEqual(session.cart, {})

    def test_shipping_validation(self) -> None:
        session = AgentSession()
        (bad, _), _ = self.run_tool("save_shipping_field", {"field": "postcode", "value": "123"}, session)
        (bad_phone, _), _ = self.run_tool("save_shipping_field", {"field": "phone", "value": "12345"}, session)
        (ok, event), _ = self.run_tool("save_shipping_field", {"field": "phone", "value": "081-234 5678"}, session)
        self.assertFalse(bad["ok"])
        self.assertFalse(bad_phone["ok"])
        self.assertEqual(session.shipping["phone"], "0812345678")
        self.assertEqual(event["type"], "shipping_field")
        self.assertFalse(ok["complete"])

    def test_confirm_order_needs_cart_and_complete_shipping(self) -> None:
        session = AgentSession()
        (empty, _), _ = self.run_tool("confirm_order", {}, session)
        self.assertFalse(empty["ok"])
        session.cart["p1"] = 1
        (partial, _), _ = self.run_tool("confirm_order", {}, session)
        self.assertFalse(partial["ok"])
        values = {
            "recipient_name": "Somchai Jaidee",
            "house_no": "12/3",
            "phone": "0812345678",
        }
        for key, value in values.items():
            (saved, _), _ = self.run_tool("save_shipping_field", {"field": key, "value": value}, session)
            self.assertTrue(saved["ok"])
        (blocked, _), _ = self.run_tool("save_shipping_field", {"field": "postcode", "value": "10260"}, session)
        self.assertFalse(blocked["ok"])
        (verified, events), _ = self.run_tool(
            "verify_address",
            {"subdistrict": "บางนาเหนือ", "district": "บางนา", "province": "กรุงเทพ", "postcode": "10260"},
            session,
        )
        self.assertTrue(verified["verified"])
        self.assertTrue(verified["complete"])
        self.assertEqual(len(events), 4)
        (done, _), _ = self.run_tool("confirm_order", {}, session)
        self.assertTrue(done["ok"])
        self.assertTrue(session.order_confirmed)
        self.assertEqual(session.pending_redirect, fasai.HOME_URL)

    def test_log_callback_needs_ticket(self) -> None:
        session = AgentSession()
        (no_ticket, _), saved = self.run_tool("log_callback", {"reason": "x"}, session)
        self.assertFalse(no_ticket["ok"])
        session.ticket_no = "FS-1"
        (ok, _), saved = self.run_tool("log_callback", {"reason": "x"}, session)
        self.assertTrue(ok["ok"])
        self.assertEqual(len(saved), 1)


if __name__ == "__main__":
    unittest.main()
