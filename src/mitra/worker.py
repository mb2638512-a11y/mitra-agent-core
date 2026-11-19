"""Supervised local worker for explicitly registered workspace adapters."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from mitra.adapters import AdapterRegistry, authorize_adapter_execution
from mitra.config import InstanceConfig
from mitra.filesystem import FilesystemReadAdapter, FilesystemWriteAdapter
from mitra.store import Store


class Worker:
    """Runs only the small set of local adapters explicitly registered here."""

    def __init__(self, config: InstanceConfig | None = None):
        self.config = config or InstanceConfig.load()
        self.store = Store(self.config.data_dir / "mitra.sqlite3")
        self.adapters = AdapterRegistry()
        self.adapters.register(FilesystemReadAdapter())
        self.adapters.register(FilesystemWriteAdapter())

    @staticmethod
    def _parse_intent(task: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        try:
            intent = json.loads(task["details"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("worker task details must be valid JSON") from exc
        if not isinstance(intent, dict):
            raise ValueError("worker task details must be a JSON object")
        capability = intent.get("capability")
        operation = intent.get("operation")
        path = intent.get("path")
        if not isinstance(capability, str) or not isinstance(operation, str) or not isinstance(path, str):
            raise ValueError("task intent requires string capability, operation and path")
        if capability == "filesystem-read" and operation in {"read", "list"}:
            allowed = {"capability", "operation", "path"}
            if operation == "list":
                allowed.add("limit")
            if set(intent) != allowed:
                raise ValueError("read task intent contains unexpected or missing fields")
            arguments = {"path": path}
            if operation == "list":
                limit = intent["limit"]
                if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
                    raise ValueError("list task limit must be between 1 and 100")
                arguments["limit"] = limit
            return capability, operation, arguments
        if capability == "filesystem-write" and operation == "write":
            if set(intent) != {"capability", "operation", "path", "content"}:
                raise ValueError("write task intent contains unexpected or missing fields")
            if not isinstance(intent["content"], str):
                raise ValueError("write content must be text")
            return capability, operation, {"path": path, "content": intent["content"]}
        raise ValueError("no supervised worker handler is installed for this capability and operation")

    def _execute(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = task["id"]
        lease_token = task["lease_token"]
        capability, operation, arguments = self._parse_intent(task)
        permit = authorize_adapter_execution(
            store=self.store,
            registry=self.adapters,
            instance_id=self.config.instance_id,
            data_dir=self.config.data_dir,
            task_id=task_id,
            lease_token=lease_token,
            capability_id=capability,
            operation=operation,
        )
        canonical = json.dumps(
            {"capability": capability, "operation": operation, **arguments},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        request_hash = hashlib.sha256(canonical).hexdigest()
        receipt = self.store.begin_execution_receipt(
            task_id, lease_token, capability_id=capability, operation=operation,
            idempotency_key="worker:" + task_id, request_hash=request_hash,
        )
        if not receipt.get("_created"):
            if receipt["status"] == "completed":
                return {"task_id": task_id, "status": "completed", "receipt_id": receipt["id"],
                        "replayed": True}
            return {"task_id": task_id, "status": "uncertain", "receipt_id": receipt["id"],
                    "message": "An unfinished receipt requires manual reconciliation."}
        try:
            result = permit.adapter.execute(operation, arguments, permit.context)
            if not result.success:
                raise RuntimeError(result.error or "adapter reported failure")
            # Read results are retained in the local receipt only; the store enforces a 20 KB cap.
            finalized = self.store.finish_execution_receipt(
                task_id, lease_token, receipt["id"], result=result.data,
            )
            self.store.begin_verification(task_id, lease_token)
            completed = self.store.finish_task(
                task_id, lease_token, success=True,
                detail="Verified local adapter operation; receipt=" + finalized["id"],
            )
            return {"task_id": task_id, "status": completed["status"],
                    "receipt_id": finalized["id"], "result": result.data}
        except Exception as exc:
            try:
                self.store.finish_execution_receipt(
                    task_id, lease_token, receipt["id"], error=str(exc)[:2000],
                )
            except (ValueError, PermissionError):
                pass
            try:
                self.store.retry_task(task_id, delay_seconds=30, reason=str(exc)[:2000])
            except (ValueError, PermissionError):
                pass
            return {"task_id": task_id, "status": "retry_or_failed", "error": str(exc)[:500]}

    def run_once(self) -> dict[str, Any]:
        self.store.recover_expired_leases()
        task = self.store.claim_task()
        if task is not None:
            task = self.store.start_task(task["id"], task["lease_token"])
            if task["status"] == "awaiting_approval":
                return {"task_id": task["id"], "status": "awaiting_approval"}
            if task["status"] != "running":
                return {"task_id": task["id"], "status": task["status"]}
            return self._execute(task)

        approved = self.store.claim_approved_task()
        if approved is None:
            return {"status": "idle"}
        return self._execute(approved)

    def run_forever(self, *, poll_seconds: float = 2.0, max_tasks: int = 0) -> None:
        if not 0.2 <= poll_seconds <= 60:
            raise ValueError("poll_seconds must be between 0.2 and 60")
        processed = 0
        while max_tasks <= 0 or processed < max_tasks:
            result = self.run_once()
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
            if result.get("status") != "idle":
                processed += 1
            else:
                time.sleep(poll_seconds)
