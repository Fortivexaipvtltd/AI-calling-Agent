from __future__ import annotations


def decide_next_action(insights: dict, final_state: str, score: int) -> str:
    """Determine the next sales action after the call."""
    if final_state == "CLOSE" and score >= 85:
        return "human_call_now"
    if insights.get("sentiment") == "negative":
        return "nurture_email"
    if "price" in insights.get("objections", []):
        return "send_pricing_and_followup"
    if score >= 60:
        return "book_meeting"
    if score >= 40:
        return "followup_call_48h"
    return "long_term_nurture"
