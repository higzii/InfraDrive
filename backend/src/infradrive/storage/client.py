from __future__ import annotations

from collections.abc import Iterable

import httpx

from infradrive.config import StorageNode


class StorageNodeError(RuntimeError):
    pass


class StorageClient:
    def __init__(
        self,
        nodes: Iterable[StorageNode],
        timeout_seconds: float = 10.0,
        connect_timeout_seconds: float = 3.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.nodes = {node.name: node for node in nodes}
        self._owns_client = client is None
        self.http = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.http.aclose()

    def node_names(self) -> list[str]:
        return list(self.nodes)

    def _url(self, node_name: str, path: str) -> str:
        try:
            node = self.nodes[node_name]
        except KeyError as exc:
            raise StorageNodeError(f"unknown storage node: {node_name}") from exc
        return f"{node.url}{path}"

    async def health(self, node_name: str) -> bool:
        try:
            response = await self.http.get(self._url(node_name, "/health"))
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def put_chunk(self, node_name: str, chunk_id: str, data: bytes) -> None:
        try:
            response = await self.http.put(
                self._url(node_name, f"/chunks/{chunk_id}"),
                content=data,
                headers={"Content-Type": "application/octet-stream"},
            )
            if response.status_code not in (200, 201):
                raise StorageNodeError(
                    f"storage node {node_name} rejected PUT ({response.status_code})"
                )
            try:
                acknowledgement = response.json()
                acknowledged_size = int(acknowledgement.get("size", -1))
            except (ValueError, TypeError, AttributeError) as exc:
                raise StorageNodeError(
                    f"storage node {node_name} returned an invalid PUT acknowledgement"
                ) from exc
            if (
                acknowledgement.get("chunk_id") != chunk_id
                or acknowledgement.get("sha256") != chunk_id
                or acknowledged_size != len(data)
            ):
                raise StorageNodeError(
                    f"storage node {node_name} returned a mismatched PUT acknowledgement"
                )
        except httpx.HTTPError as exc:
            raise StorageNodeError(f"storage node {node_name} is unavailable") from exc

    async def get_chunk(self, node_name: str, chunk_id: str) -> bytes:
        try:
            response = await self.http.get(self._url(node_name, f"/chunks/{chunk_id}"))
            if response.status_code == 404:
                raise StorageNodeError(f"chunk is missing on {node_name}")
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise StorageNodeError(f"unable to read chunk from {node_name}") from exc

    async def delete_chunk(self, node_name: str, chunk_id: str) -> None:
        try:
            response = await self.http.delete(self._url(node_name, f"/chunks/{chunk_id}"))
            if response.status_code not in (200, 204, 404):
                raise StorageNodeError(
                    f"storage node {node_name} rejected DELETE ({response.status_code})"
                )
        except httpx.HTTPError as exc:
            raise StorageNodeError(f"unable to delete chunk from {node_name}") from exc
