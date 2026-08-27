from __future__ import annotations


class RepairPolicy:
    """Handle 'what?', silence, interruption, misunderstanding and topic change."""

    CLARIFY = {"what", "sorry", "pardon", "come again", "repeat", "didn't catch"}

    def needs_repair(self, text: str) -> str | None:
        t = text.strip().lower()
        if not t:
            return "silence"
        if any(t == c or t.startswith(c + " ") or t.rstrip("?") in self.CLARIFY for c in self.CLARIFY):
            return "clarify"
        return None

    def repair_line(self, kind: str, last_agent_line: str) -> str:
        if kind == "silence":
            return "Are you still there? I can keep it brief."
        if kind == "clarify":
            return f"Of course — {last_agent_line}"
        return "Let me put that more simply."
