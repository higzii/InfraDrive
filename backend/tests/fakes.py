from __future__ import annotations

import asyncio
from collections import defaultdict

from infradrive.storage.client import StorageNodeError


class _FakeLock:
    def __init__(self, lock: asyncio.Lock) -> None:
        self.lock = lock

    async def __aenter__(self):
        await self.lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.lock.release()


class _FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.operations = []

    def set(self, key: str, value: str):
        self.operations.append(("set", key, value))
        return self

    def sadd(self, key: str, value: str):
        self.operations.append(("sadd", key, value))
        return self

    def srem(self, key: str, value: str):
        self.operations.append(("srem", key, value))
        return self

    def scard(self, key: str):
        self.operations.append(("scard", key))
        return self

    async def execute(self):
        results = []
        for operation in self.operations:
            name, *args = operation
            method = getattr(self.redis, name)
            results.append(await method(*args))
        self.operations.clear()
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = defaultdict(set)
        self.locks: dict[str, asyncio.Lock] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str):
        self.values[key] = value
        return True

    async def sadd(self, key: str, value: str):
        before = len(self.sets[key])
        self.sets[key].add(value)
        return len(self.sets[key]) - before

    async def srem(self, key: str, value: str):
        existed = value in self.sets[key]
        self.sets[key].discard(value)
        return int(existed)

    async def scard(self, key: str):
        return len(self.sets[key])

    async def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                removed += 1
            if key in self.sets:
                del self.sets[key]
                removed += 1
        return removed

    def lock(self, name: str, **kwargs):
        return _FakeLock(self.locks.setdefault(name, asyncio.Lock()))

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)


class FakeStorage:
    def __init__(self, node_names: list[str]) -> None:
        self.nodes = {name: object() for name in node_names}
        self.data: dict[str, dict[str, bytes]] = {name: {} for name in node_names}
        self.online = set(node_names)

    def node_names(self) -> list[str]:
        return list(self.nodes)

    async def health(self, node_name: str) -> bool:
        return node_name in self.online

    async def put_chunk(self, node_name: str, chunk_id: str, data: bytes) -> None:
        if node_name not in self.online:
            raise StorageNodeError(f"{node_name} offline")
        self.data[node_name][chunk_id] = data

    async def get_chunk(self, node_name: str, chunk_id: str) -> bytes:
        if node_name not in self.online:
            raise StorageNodeError(f"{node_name} offline")
        try:
            return self.data[node_name][chunk_id]
        except KeyError as exc:
            raise StorageNodeError(f"{chunk_id} missing on {node_name}") from exc

    async def delete_chunk(self, node_name: str, chunk_id: str) -> None:
        self.data[node_name].pop(chunk_id, None)

    async def close(self) -> None:
        return None
