from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Arm:
    name: str
    pulls: int = 0
    reward: float = 0.0

    @property
    def mean(self) -> float:
        return self.reward / self.pulls if self.pulls else 0.0


class Bandit:
    """UCB1 multi-armed bandit. Picks the arm (a provider/voice/model config) that
    balances exploiting the current best against exploring under-tried options."""

    def __init__(self, arms: list[str]) -> None:
        self.arms: dict[str, Arm] = {a: Arm(a) for a in arms}
        self.t = 0

    def select(self) -> str:
        self.t += 1
        untried = [a for a in self.arms.values() if a.pulls == 0]
        if untried:
            return random.choice(untried).name
        def ucb(a: Arm) -> float:
            return a.mean + math.sqrt(2 * math.log(self.t) / a.pulls)
        return max(self.arms.values(), key=ucb).name

    def update(self, arm: str, reward: float) -> None:
        a = self.arms.get(arm)
        if a:
            a.pulls += 1
            a.reward += reward

    def best(self) -> dict:
        ranked = sorted(self.arms.values(), key=lambda a: a.mean, reverse=True)
        return {"best": ranked[0].name if ranked else None,
                "arms": {a.name: {"pulls": a.pulls, "mean_reward": round(a.mean, 3)}
                         for a in ranked}}


class Optimizer:
    """Runs a bandit per decision axis (llm / tts_voice / stt) and learns from
    call outcomes which combination converts best. Reward is any 0..1 signal —
    booked, paid, positive sentiment — reported back after each call."""

    AXES = {
        "llm": ["local", "anthropic", "byo"],
        "tts_voice": ["nova", "aarav", "meera"],
        "stt": ["local", "deepgram"],
    }

    def __init__(self) -> None:
        self.bandits = {axis: Bandit(options) for axis, options in self.AXES.items()}
        self.history: list[dict] = []

    def choose(self) -> dict:
        return {axis: b.select() for axis, b in self.bandits.items()}

    def report(self, choice: dict, reward: float) -> None:
        reward = max(0.0, min(1.0, reward))
        for axis, arm in choice.items():
            if axis in self.bandits:
                self.bandits[axis].update(arm, reward)
        self.history.append({"choice": choice, "reward": reward})

    def recommendation(self) -> dict:
        return {axis: b.best() for axis, b in self.bandits.items()}

    def simulate(self, trials: int = 200) -> dict:
        """Self-tune against a synthetic reward model so the API has data to show.
        The synthetic 'ground truth' favours anthropic + aarav + deepgram."""
        truth = {"llm": {"anthropic": 0.7, "byo": 0.55, "local": 0.5},
                 "tts_voice": {"aarav": 0.66, "nova": 0.6, "meera": 0.58},
                 "stt": {"deepgram": 0.68, "local": 0.55}}
        for _ in range(trials):
            choice = self.choose()
            base = sum(truth[a][choice[a]] for a in choice) / len(choice)
            self.report(choice, random.gauss(base, 0.1))
        return self.recommendation()


optimizer = Optimizer()
