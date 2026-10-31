"""Общий формат ответа обработки для HTTP и файлового транспорта."""
from typing import Any, Optional
from pydantic import BaseModel


class CommandResult(BaseModel):
    """Result from 1C processing."""
    id: str
    success: bool
    data: Optional[Any] = None
    schema: Optional[Any] = None
    error: Optional[str] = None
    count: Optional[int] = None
    # Optional metadata fields for list/pagination responses (e.g., get_metadata list mode)
    truncated: Optional[bool] = None
    limit: Optional[int] = None
    returned: Optional[int] = None
    offset: Optional[int] = None
    has_more: Optional[bool] = None
    next_offset: Optional[int] = None
    configuration: Optional[Any] = None
    extension: Optional[str] = None
    # Cursor pagination fields for get_event_log
    last_date: Optional[str] = None                  # Cursor - last record date
    next_same_second_offset: Optional[int] = None    # Accumulated offset for next page
    # submit_for_deanonymization acknowledgement field
    received: Optional[bool] = None
    # Screenshot result fields for get_screenshot
    image_base64: Optional[str] = None
    mime_type: Optional[str] = None
    window_rect: Optional[Any] = None
    grid_coords: Optional[Any] = None
    overlays: Optional[Any] = None
    overlay_failures: Optional[Any] = None
    capture_complete: Optional[Any] = None
    foreground_window: Optional[Any] = None
