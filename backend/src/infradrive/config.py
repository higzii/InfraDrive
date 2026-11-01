from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from urllib.parse import quote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True, slots=True)
class StorageNode:
    name: str
    url: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFRADRIVE_",
        case_sensitive=False,
        extra="ignore",
    )

    valkey_host: str = "infradrive-valkey"
    valkey_port: int = 6379
    valkey_db: int = 0
    valkey_password: str = ""

    # Comma-separated name=URL pairs; the defaults match the Ansible inventory.
    storage_nodes: str = (
        "storage-1=http://storage-1:8001,"
        "storage-2=http://storage-2:8001,"
        "storage-3=http://storage-3:8001"
    )
    chunk_size_bytes: int = 4 * 1024 * 1024
    max_file_bytes: int = 10 * 1024 * 1024 * 1024
    replication_factor: int = 2
    storage_timeout_seconds: float = 10.0
    storage_connect_timeout_seconds: float = 3.0
    api_token: str = ""

    @field_validator("valkey_port")
    @classmethod
    def validate_valkey_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("INFRADRIVE_VALKEY_PORT must be between 1 and 65535")
        return value

    @field_validator("chunk_size_bytes", "max_file_bytes")
    @classmethod
    def validate_positive_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("chunk and file size limits must be greater than zero")
        return value

    @field_validator("replication_factor")
    @classmethod
    def validate_replication_factor(cls, value: int) -> int:
        if value < 1:
            raise ValueError("INFRADRIVE_REPLICATION_FACTOR must be at least 1")
        return value

    @field_validator("storage_timeout_seconds", "storage_connect_timeout_seconds")
    @classmethod
    def validate_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("storage timeouts must be greater than zero")
        return value

    @cached_property
    def nodes(self) -> tuple[StorageNode, ...]:
        parsed: list[StorageNode] = []
        seen: set[str] = set()
        for raw_item in self.storage_nodes.split(","):
            item = raw_item.strip()
            if not item:
                continue
            if "=" not in item:
                raise ValueError(
                    "INFRADRIVE_STORAGE_NODES entries must use name=http://host:port"
                )
            name, url = item.split("=", 1)
            name, url = name.strip(), url.strip().rstrip("/")
            if not name or not url.startswith(("http://", "https://")):
                raise ValueError(f"invalid storage node entry: {item!r}")
            if name in seen:
                raise ValueError(f"duplicate storage node name: {name}")
            seen.add(name)
            parsed.append(StorageNode(name=name, url=url))
        if not parsed:
            raise ValueError("at least one storage node must be configured")
        if self.replication_factor > len(parsed):
            raise ValueError("replication factor cannot exceed the number of storage nodes")
        return tuple(parsed)

    @property
    def valkey_url(self) -> str:
        password_part = f":{quote(self.valkey_password, safe='')}@" if self.valkey_password else ""
        return f"redis://{password_part}{self.valkey_host}:{self.valkey_port}/{self.valkey_db}"
