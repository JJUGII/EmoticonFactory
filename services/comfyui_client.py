"""ComfyUI HTTP API client (queue prompt, poll history, download outputs)."""

from __future__ import annotations

import json
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlencode


class ComfyUIError(RuntimeError):
    """ComfyUI API or workflow failure."""


class ComfyUIClient:
    def __init__(self, base_url: str, *, poll_interval_s: float = 1.0, timeout_s: float = 900.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def _log(self, msg: str) -> None:
        print(f"[COMFYUI] {msg}", file=sys.stderr)

    def health_ok(self) -> bool:
        try:
            req = request.Request(f"{self.base_url}/system_stats", method="GET")
            with request.urlopen(req, timeout=5) as resp:
                return 200 <= resp.status < 300
        except (OSError, error.URLError, error.HTTPError):
            return False

    def fetch_object_info(self) -> dict[str, Any]:
        """ComfyUI ``/object_info`` — available node class types."""
        req = request.Request(f"{self.base_url}/object_info", method="GET")
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict):
            return data
        return {}

    def upload_image(self, image_path: Path, *, subfolder: str = "") -> str:
        """Upload to ComfyUI input; returns filename for LoadImage node."""
        boundary = f"----KakaoEmoticonFactory{uuid.uuid4().hex}"
        name = image_path.name
        data = image_path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
                    f"Content-Type: image/png\r\n\r\n"
                ).encode(),
                data,
                b"\r\n",
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="subfolder"\r\n\r\n',
                subfolder.encode(),
                b"\r\n",
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="type"\r\n\r\n',
                b"input\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        req = request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        uploaded = str(payload.get("name") or name)
        self._log(f"uploaded reference image={uploaded}")
        return uploaded

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        body = json.dumps({"prompt": workflow}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/prompt",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except OSError:
                detail = str(exc)
            if "ckpt_name" in detail or "CheckpointLoader" in detail:
                raise ComfyUIError(
                    "ComfyUI invalid prompt (checkpoint). "
                    "Set COMFYUI_CHECKPOINT in .env to a file under "
                    "ComfyUI/models/checkpoints, or install an SDXL checkpoint.\n"
                    f"HTTP {exc.code}: {detail[:2000]}"
                ) from exc
            raise ComfyUIError(f"ComfyUI /prompt failed: HTTP {exc.code}: {detail[:2000]}") from exc
        prompt_id = str(data.get("prompt_id") or "")
        if not prompt_id:
            raise ComfyUIError(f"ComfyUI /prompt 응답에 prompt_id 없음: {data!r}")
        self._log("prompt submitted")
        self._log(f"prompt_id={prompt_id}")
        return prompt_id

    def wait_history(self, prompt_id: str) -> dict[str, Any]:
        self._log("polling history")
        deadline = time.monotonic() + self.timeout_s
        last_err: str | None = None
        while time.monotonic() < deadline:
            try:
                req = request.Request(f"{self.base_url}/history/{prompt_id}", method="GET")
                with request.urlopen(req, timeout=30) as resp:
                    hist = json.loads(resp.read().decode("utf-8"))
            except error.HTTPError as exc:
                last_err = str(exc)
                time.sleep(self.poll_interval_s)
                continue
            entry = hist.get(prompt_id) if isinstance(hist, dict) else None
            if not entry and isinstance(hist, dict) and len(hist) == 1:
                entry = next(iter(hist.values()))
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    msgs = status.get("messages") or entry.get("messages") or []
                    raise ComfyUIError(f"ComfyUI workflow 오류: {msgs}")
                outputs = entry.get("outputs") or {}
                if outputs:
                    return entry
            time.sleep(self.poll_interval_s)
        raise ComfyUIError(
            f"ComfyUI history 타임아웃 ({self.timeout_s}s, prompt_id={prompt_id}"
            + (f", last_err={last_err}" if last_err else "")
            + ")"
        )

    def first_output_image(self, history_entry: dict[str, Any]) -> dict[str, str]:
        images = self.output_images(history_entry)
        if not images:
            raise ComfyUIError("ComfyUI history에 출력 이미지가 없습니다.")
        return images[0]

    def output_images(
        self,
        history_entry: dict[str, Any],
        *,
        save_node_order: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Collect output images; optional ``save_node_order`` preserves cut mapping."""
        outputs = history_entry.get("outputs") or {}
        if save_node_order:
            out: list[dict[str, str]] = []
            for node_id in save_node_order:
                node_out = outputs.get(node_id)
                if not isinstance(node_out, dict):
                    continue
                for img in node_out.get("images") or []:
                    if isinstance(img, dict) and img.get("filename"):
                        out.append(
                            {
                                "filename": str(img["filename"]),
                                "subfolder": str(img.get("subfolder") or ""),
                                "type": str(img.get("type") or "output"),
                            }
                        )
                        break
            if out:
                return out

        collected: list[dict[str, str]] = []
        for node_id in sorted(outputs.keys(), key=lambda x: int(x) if str(x).isdigit() else 99999):
            node_out = outputs.get(node_id)
            if not isinstance(node_out, dict):
                continue
            for img in node_out.get("images") or []:
                if isinstance(img, dict) and img.get("filename"):
                    collected.append(
                        {
                            "filename": str(img["filename"]),
                            "subfolder": str(img.get("subfolder") or ""),
                            "type": str(img.get("type") or "output"),
                        }
                    )
        return collected

    def download_image(self, meta: dict[str, str], dest: Path) -> Path:
        q = urlencode(
            {
                "filename": meta["filename"],
                "subfolder": meta.get("subfolder") or "",
                "type": meta.get("type") or "output",
            }
        )
        url = f"{self.base_url}/view?{q}"
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        self._log(f"output image={dest.resolve()}")
        return dest

    @staticmethod
    def random_seed() -> int:
        return random.randint(0, 2**32 - 1)
