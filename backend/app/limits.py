from __future__ import annotations

import ipaddress
import time
from collections import OrderedDict, deque
from functools import lru_cache
from threading import RLock

from fastapi import HTTPException
from starlette.requests import Request


def _parse_host(value: str) -> str | None:
    candidate = value.strip().strip('"')
    if candidate.lower() == "unknown" or not candidate:
        return None
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    else:
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            if candidate.count(":") == 1:
                candidate = candidate.rsplit(":", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


@lru_cache(maxsize=32)
def _proxy_networks(raw: tuple[str, ...]) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in raw:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def client_ip(request: Request, trusted_proxy_cidrs: list[str] | tuple[str, ...] = ()) -> str:
    """Resolve a client IP without trusting spoofable forwarding headers by default."""

    peer = _parse_host(request.client.host if request.client else "") or "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    networks = _proxy_networks(tuple(trusted_proxy_cidrs))
    if not any(peer_ip in network for network in networks):
        return peer

    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        chain = [part.strip() for part in forwarded_for.split(",")]
    else:
        chain = []
        for hop in request.headers.get("forwarded", "").split(","):
            for parameter in hop.split(";"):
                name, separator, value = parameter.strip().partition("=")
                if separator and name.lower() == "for":
                    chain.append(value.strip())
                    break
    parsed = [address for part in chain if (address := _parse_host(part))]
    parsed.append(peer)
    for address in reversed(parsed):
        ip = ipaddress.ip_address(address)
        if not any(ip in network for network in networks):
            return address
    return parsed[0] if parsed else peer


class SlidingWindowLimiter:
    def __init__(self, max_keys: int = 10_000) -> None:
        self.max_keys = max_keys
        self.hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = RLock()

    def reset(self) -> None:
        with self._lock:
            self.hits.clear()

    def hit(self, key: str, limit: int, window: float, *, max_keys: int | None = None) -> None:
        if limit <= 0:
            return
        if window <= 0:
            raise ValueError("Rate-limit window must be positive")
        now = time.monotonic()
        cutoff = now - window
        capacity = max(1, max_keys if max_keys is not None else self.max_keys)
        with self._lock:
            while self.hits:
                oldest_key, oldest = next(iter(self.hits.items()))
                while oldest and oldest[0] <= cutoff:
                    oldest.popleft()
                if oldest:
                    break
                self.hits.pop(oldest_key, None)

            q = self.hits.get(key)
            if q is None:
                while len(self.hits) >= capacity:
                    self.hits.popitem(last=False)
                q = deque()
                self.hits[key] = q
            else:
                while q and q[0] <= cutoff:
                    q.popleft()
                self.hits.move_to_end(key)

            if len(q) >= limit:
                retry_after = max(1, int(window - (now - q[0]) + 0.999))
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            q.append(now)


limiter = SlidingWindowLimiter()
