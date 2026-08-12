from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .image_loader import (
    LoadedImage,
    load_new_image_bytes,
    normalized_png_bytes,
    rotated_png_bytes,
)


CaptureSource = Literal["phone", "webcam"]


@dataclass(slots=True)
class PendingCapture:
    id: str
    source: CaptureSource
    filename: str
    captured_at: datetime
    loaded: LoadedImage
    quarter_turns: int = 0


@dataclass(frozen=True, slots=True)
class PromotionPayload:
    filename: str
    raw: bytes


class CaptureSessionService:
    def __init__(self) -> None:
        self._items: list[PendingCapture] = []
        self._selected_id: str | None = None

    def _find(self, pending_id: str) -> PendingCapture:
        for item in self._items:
            if item.id == pending_id:
                return item
        raise KeyError(f"Unknown pending capture: {pending_id}")

    def add_bytes(
        self,
        source: CaptureSource,
        raw: bytes,
        filename: str,
    ) -> PendingCapture:
        if source not in ("phone", "webcam"):
            raise ValueError("Unknown capture source")
        pending_id = str(uuid4())
        loaded = load_new_image_bytes(raw, filename, pending_id)
        item = PendingCapture(
            id=pending_id,
            source=source,
            filename=loaded.asset.filename,
            captured_at=datetime.now(timezone.utc),
            loaded=loaded,
        )
        self._items.append(item)
        self._selected_id = pending_id
        return item

    def items(self) -> tuple[PendingCapture, ...]:
        return tuple(self._items)

    def select(self, pending_id: str) -> None:
        self._find(pending_id)
        self._selected_id = pending_id

    def selected(self) -> PendingCapture:
        if self._selected_id is None:
            raise ValueError("Select a pending capture")
        return self._find(self._selected_id)

    def rotate(self, pending_id: str, clockwise: bool = True) -> PendingCapture:
        item = self._find(pending_id)
        delta = 1 if clockwise else -1
        item.quarter_turns = (item.quarter_turns + delta) % 4
        return item

    def delete(self, pending_id: str) -> None:
        item = self._find(pending_id)
        self._items.remove(item)
        if self._selected_id == pending_id:
            self._selected_id = self._items[-1].id if self._items else None

    def preview_png(self, pending_id: str) -> bytes:
        item = self._find(pending_id)
        if item.quarter_turns % 4 == 0:
            return normalized_png_bytes(item.loaded)
        return rotated_png_bytes(item.loaded, item.quarter_turns)

    def promotion_bytes(self, pending_id: str) -> PromotionPayload:
        item = self._find(pending_id)
        if item.quarter_turns % 4 == 0:
            return PromotionPayload(filename=item.filename, raw=item.loaded.original_bytes)
        name = f"{Path(item.filename).stem or 'capture'}.png"
        return PromotionPayload(
            filename=name,
            raw=rotated_png_bytes(item.loaded, item.quarter_turns),
        )
