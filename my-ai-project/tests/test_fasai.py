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

    def test_idle_timer(self) -> None:
        idle = fasai.IdleTimer(120)
        idle.touch(0.0)
        self.assertFalse(idle.expired(119.0))
        self.assertTrue(idle.expired(120.0))


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

    def test_checkout_requires_cart(self) -> None:
        session = AgentSession()
        (empty, _), _ = self.run_tool("go_checkout", {}, session)
        self.assertFalse(empty["ok"])
        session.cart["p1"] = 1
        (ok, _), _ = self.run_tool("go_checkout", {}, session)
        self.assertTrue(ok["ok"])
        self.assertEqual(session.pending_redirect, fasai.CHECKOUT_URL)

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
