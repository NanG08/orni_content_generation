"""
The contract. This is the most important file in the repo after the intent
prompt: it is the shared language between the voice brain, the router, the
generators, and the frontend. Four people can build in parallel as long as
they respect these shapes.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Action = Literal["create", "edit", "animate", "localize", "wardrobe", "unknown"]
Aspect = Literal["9:16", "1:1", "16:9"]
Energy = Literal["low", "medium", "high"]


Energy = Literal["low", "medium", "high"]

class Intent(BaseModel):
    action: Action = "unknown"
    target_asset_id: Optional[str] = None
    product: Optional[str] = None
    background: Optional[str] = None
    copy_text: Optional[str] = None
    style: Optional[str] = None
    motion: Optional[str] = None
    language: Optional[str] = None
    aspect: Aspect = "9:16"
    wardrobe: Optional[str] = None
    interrupt: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    energy: Energy = "medium"  # detected from vocal emphasis in transcript


# ---- WebSocket messages: client -> server -----------------------------------
class Utterance(BaseModel):
    type: Literal["utterance"] = "utterance"
    text: str
    final: bool = True                          # partial vs settled transcript


class Interrupt(BaseModel):
    type: Literal["interrupt"] = "interrupt"


class SelectAsset(BaseModel):
    type: Literal["select_asset"] = "select_asset"
    asset_id: str


# ---- WebSocket messages: server -> client -----------------------------------
# Sent as plain dicts (see main.py) so we keep one obvious wire format:
#   {"type": "intent",      "intent": {...}}
#   {"type": "status",      "stage": "image", "message": "...", "budget_ms": 4000}
#   {"type": "placeholder", "asset_id": "...", "aspect": "9:16"}
#   {"type": "asset",       "asset_id": "...", "src": "<data-uri>", "overlay": {...}}
#   {"type": "video",       "asset_id": "...", "src": "<url>", "poster": "<data-uri>"}
#   {"type": "audio",       "asset_id": "...", "src": "<data-uri>"}
#   {"type": "error",       "message": "..."}
