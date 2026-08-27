from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field

from ..config import settings


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass
class PhoneNumber:
    e164: str
    provider: str = "local"
    capabilities: tuple[str, ...] = ("voice", "sms")
    id: str = field(default_factory=lambda: _id("num"))
    status: str = "active"


@dataclass
class NumberPool:
    name: str
    strategy: str = "round_robin"  # round_robin | sticky | area_match
    id: str = field(default_factory=lambda: _id("pool"))
    numbers: list[PhoneNumber] = field(default_factory=list)
    _cycle: object = None

    def add(self, number: PhoneNumber) -> None:
        self.numbers.append(number)
        self._cycle = itertools.cycle(self.numbers)

    def pick(self, dest_e164: str = "") -> PhoneNumber | None:
        if not self.numbers:
            return None
        if self.strategy == "area_match" and dest_e164:
            prefix = dest_e164[:4]
            for n in self.numbers:
                if n.e164.startswith(prefix):
                    return n
        if self.strategy == "sticky":
            return self.numbers[hash(dest_e164) % len(self.numbers)]
        if self._cycle is None:
            self._cycle = itertools.cycle(self.numbers)
        return next(self._cycle)


class NumberService:
    """In-memory number inventory. Real providers plug in via `provision`."""

    def __init__(self) -> None:
        self.numbers: dict[str, PhoneNumber] = {}
        self.pools: dict[str, NumberPool] = {}
        if settings.twilio_from_number:
            self.provision(settings.twilio_from_number, provider="twilio")

    def provision(self, e164: str, provider: str = "local",
                  capabilities: tuple[str, ...] = ("voice", "sms")) -> PhoneNumber:
        num = PhoneNumber(e164=e164, provider=provider, capabilities=capabilities)
        self.numbers[num.id] = num
        return num

    def release(self, number_id: str) -> bool:
        n = self.numbers.pop(number_id, None)
        return n is not None

    def create_pool(self, name: str, strategy: str = "round_robin") -> NumberPool:
        pool = NumberPool(name=name, strategy=strategy)
        self.pools[pool.id] = pool
        return pool

    def add_to_pool(self, pool_id: str, number_id: str) -> bool:
        pool, num = self.pools.get(pool_id), self.numbers.get(number_id)
        if not pool or not num:
            return False
        pool.add(num)
        return True

    def caller_id_for(self, pool_id: str, dest_e164: str) -> str:
        pool = self.pools.get(pool_id)
        if not pool:
            return settings.twilio_from_number
        picked = pool.pick(dest_e164)
        return picked.e164 if picked else settings.twilio_from_number


numbers = NumberService()
