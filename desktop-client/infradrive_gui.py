#!/usr/bin/env python3
"""Tiny cross-Unix Tk client for InfraDrive (stdlib only)."""

from __future__ import annotations

import http.client
import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, urlsplit


APP_TITLE = "InfraDrive"
DEFAULT_API_URL = os.getenv("INFRADRIVE_API_URL", "http://127.0.0.1:8000")
IO_BLOCK_SIZE = 1024 * 1024


class ApiError(RuntimeError):
    pass


def _connection_for(base_url: str, timeout: int = 60):
    parsed = urlsplit(base_url.strip().rstrip("/"))
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ApiError("API URL must start with http:// or https://")
    if parsed.username or parsed.password:
        raise ApiError("Do not put credentials in the API URL; use the token field")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    prefix = parsed.path.rstrip("/")
    return connection, prefix, parsed.query


def _auth_headers(token: str) -> dict[str, str]:
    token = token.strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


class InfraDriveApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("640x390")
        self.minsize(560, 350)

        self.api_url = tk.StringVar(value=DEFAULT_API_URL)
        self.api_token = tk.StringVar(value=os.getenv("INFRADRIVE_API_TOKEN", ""))
        self.file_id = tk.StringVar()
        self.status = tk.StringVar(value="Not connected")
        self.progress_text = tk.StringVar(value="Ready")
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        ttk.Label(outer, text="Backend URL").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(outer, textvariable=self.api_url).grid(row=0, column=1, sticky="ew", pady=5)
        self.health_button = ttk.Button(outer, text="Check", command=self.check_health)
        self.health_button.grid(row=0, column=2, padx=(8, 0), pady=5)

        ttk.Label(outer, text="API token").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(outer, textvariable=self.api_token, show="•").grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)

        ttk.Separator(outer).grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)

        ttk.Label(outer, text="File ID").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(outer, textvariable=self.file_id).grid(row=3, column=1, sticky="ew", pady=5)
        self.copy_button = ttk.Button(outer, text="Copy", command=self.copy_file_id)
        self.copy_button.grid(row=3, column=2, padx=(8, 0), pady=5)

        actions = ttk.Frame(outer)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 8))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.upload_button = ttk.Button(actions, text="Upload file…", command=self.choose_upload)
        self.upload_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.download_button = ttk.Button(actions, text="Download by ID…", command=self.choose_download)
        self.download_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 4))
        ttk.Label(outer, textvariable=self.progress_text).grid(row=6, column=0, columnspan=3, sticky="w")

        ttk.Separator(outer).grid(row=7, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(outer, text="Status").grid(row=8, column=0, sticky="w", padx=(0, 12))
        ttk.Label(outer, textvariable=self.status, wraplength=450).grid(row=8, column=1, columnspan=2, sticky="w")
        ttk.Label(
            outer,
            text="A tiny HTTP client. Binary data is stored by the backend, not on this computer.",
            foreground="#666666",
            wraplength=560,
        ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.health_button, self.upload_button, self.download_button):
            button.configure(state=state)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _kind, current, total, label = event
                    percent = (current / total * 100) if total else 0
                    self.progress.configure(value=percent)
                    self.progress_text.set(label)
                elif kind == "status":
                    self.status.set(event[1])
                elif kind == "success":
                    self._set_busy(False)
                    self.progress.configure(value=100)
                    self.progress_text.set(event[1])
                    self.status.set("Connected / operation completed")
                    if event[2] is not None:
                        self.file_id.set(event[2])
                    messagebox.showinfo("InfraDrive", event[1])
                elif kind == "error":
                    self._set_busy(False)
                    self.progress_text.set("Failed")
                    self.status.set("Request failed")
                    messagebox.showerror("InfraDrive", event[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _start_worker(self, target, *args) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self.progress.configure(value=0)
        self.progress_text.set("Working…")
        threading.Thread(target=target, args=args, daemon=True).start()

    def check_health(self) -> None:
        self._start_worker(self._health_worker, self.api_url.get(), self.api_token.get())

    def _health_worker(self, base_url: str, token: str) -> None:
        connection = None
        try:
            connection, prefix, query = _connection_for(base_url, timeout=10)
            path = f"{prefix}/health" + (f"?{query}" if query else "")
            connection.request("GET", path, headers=_auth_headers(token))
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise ApiError(f"Health check returned HTTP {response.status}: {body.decode('utf-8', 'replace')}")
            data = json.loads(body.decode("utf-8"))
            self.events.put(("success", f"Backend is healthy. Available storage nodes: {data.get('available_storage_nodes', '?')}", None))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            if connection:
                connection.close()

    def choose_upload(self) -> None:
        filename = filedialog.askopenfilename(title="Choose a file to upload")
        if filename:
            self._start_worker(self._upload_worker, self.api_url.get(), self.api_token.get(), filename)

    def _upload_worker(self, base_url: str, token: str, filename: str) -> None:
        connection = None
        try:
            path = Path(filename)
            total = path.stat().st_size
            connection, prefix, query = _connection_for(base_url)
            boundary = "----InfraDriveBoundary7MA4YWxkTrZu0gW"
            fallback_name = path.name.encode("ascii", "ignore").decode("ascii") or "upload.bin"
            fallback_name = fallback_name.replace('"', "_").replace("\\", "_")
            part_header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{fallback_name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode("ascii")
            closing = f"\r\n--{boundary}--\r\n".encode("ascii")
            content_length = len(part_header) + total + len(closing)
            request_path = f"{prefix}/files" + (f"?{query}" if query else "")
            headers = {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(content_length),
                "Connection": "close",
                **_auth_headers(token),
            }
            connection.putrequest("POST", request_path)
            for key, value in headers.items():
                connection.putheader(key, value)
            connection.endheaders()
            connection.send(part_header)

            sent = 0
            with path.open("rb") as source:
                while True:
                    block = source.read(IO_BLOCK_SIZE)
                    if not block:
                        break
                    connection.send(block)
                    sent += len(block)
                    self.events.put(("progress", sent, max(total, 1), f"Uploading {sent:,} / {total:,} bytes"))
            connection.send(closing)
            response = connection.getresponse()
            body = response.read()
            if response.status not in (200, 201):
                raise ApiError(f"Upload returned HTTP {response.status}: {body.decode('utf-8', 'replace')}")
            result = json.loads(body.decode("utf-8"))
            message = (
                f"Uploaded {result.get('filename', path.name)}\n"
                f"File ID: {result['file_id']}\n"
                f"Size: {result['size']:,} bytes\n"
                f"SHA-256: {result['sha256']}\n"
                f"Chunks: {result['chunks']} · RF={result['replication_factor']}"
            )
            self.events.put(("success", message, result["file_id"]))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            if connection:
                connection.close()

    def choose_download(self) -> None:
        file_id = self.file_id.get().strip()
        if not file_id:
            messagebox.showwarning("InfraDrive", "Enter a File ID first")
            return
        destination = filedialog.asksaveasfilename(
            title="Save downloaded file",
            initialfile="infradrive-download.bin",
        )
        if destination:
            self._start_worker(
                self._download_worker,
                self.api_url.get(),
                self.api_token.get(),
                file_id,
                destination,
            )

    def _download_worker(self, base_url: str, token: str, file_id: str, destination: str) -> None:
        connection = None
        temporary = Path(destination + ".infradrive-part")
        try:
            connection, prefix, query = _connection_for(base_url)
            request_path = f"{prefix}/files/{quote(file_id, safe='')}" + (f"?{query}" if query else "")
            connection.request("GET", request_path, headers=_auth_headers(token))
            response = connection.getresponse()
            if response.status != 200:
                body = response.read()
                raise ApiError(f"Download returned HTTP {response.status}: {body.decode('utf-8', 'replace')}")

            total_header = response.getheader("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else 0
            received = 0
            with temporary.open("wb") as target:
                while True:
                    block = response.read(IO_BLOCK_SIZE)
                    if not block:
                        break
                    target.write(block)
                    received += len(block)
                    self.events.put(("progress", received, total or received, f"Downloading {received:,} bytes"))
            os.replace(temporary, destination)
            self.events.put(("success", f"Downloaded {received:,} bytes to:\n{destination}", None))
        except Exception as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            self.events.put(("error", str(exc)))
        finally:
            if connection:
                connection.close()

    def copy_file_id(self) -> None:
        value = self.file_id.get().strip()
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status.set("File ID copied to clipboard")


if __name__ == "__main__":
    InfraDriveApp().mainloop()
