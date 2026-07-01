"""The transport seam. The orchestrator depends on the `Notifier` protocol, never on
python-telegram-bot — so the future dashboard can drive the same approval flow with a
different Notifier. `telegram` is imported lazily so this module (and StubNotifier) work
without it installed (e.g. the Mac-side simulated test).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    async def send_approval_request(self, *, chat_id: str, text: str, approval_id: int) -> int:
        """Send an approval request with Approve/Reject affordances; return the message id."""
        ...

    async def update_resolved(self, *, chat_id: str, message_id: int, text: str) -> None:
        """Replace the request after a decision (affordances removed)."""
        ...


def approval_callback_data(approval_id: int, decision: str) -> str:
    return f"appr:{approval_id}:{decision}"


def parse_approval_callback(data: str) -> tuple[int, str] | None:
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[0] == "appr" and parts[2] in ("approve", "reject"):
        try:
            return int(parts[1]), parts[2]
        except ValueError:
            return None
    return None


class TelegramNotifier:
    """Notifier backed by a python-telegram-bot Bot."""

    def __init__(self, bot) -> None:
        self.bot = bot

    async def send_approval_request(self, *, chat_id: str, text: str, approval_id: int) -> int:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "✅ Approve", callback_data=approval_callback_data(approval_id, "approve")
                ),
                InlineKeyboardButton(
                    "❌ Reject", callback_data=approval_callback_data(approval_id, "reject")
                ),
            ]]
        )
        msg = await self.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=kb, parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return msg.message_id

    async def update_resolved(self, *, chat_id: str, message_id: int, text: str) -> None:
        await self.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML",
            disable_web_page_preview=True,
        )


class StubNotifier:
    """In-memory Notifier for the simulated test — records calls, invents message ids."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.resolutions: list[dict] = []
        self._next_id = 1000

    async def send_approval_request(self, *, chat_id: str, text: str, approval_id: int) -> int:
        self._next_id += 1
        self.requests.append(
            {"chat_id": chat_id, "text": text, "approval_id": approval_id, "message_id": self._next_id}
        )
        return self._next_id

    async def update_resolved(self, *, chat_id: str, message_id: int, text: str) -> None:
        self.resolutions.append({"chat_id": chat_id, "message_id": message_id, "text": text})
