"""Общий формат ответа обработки для HTTP и файлового транспорта."""
from typing import Any, Optional, Literal
from .operation_progress import valid_progress
from pydantic import BaseModel, StrictBool, StrictInt, model_validator


class CommandResult(BaseModel):
    """Result from 1C processing."""
    id: str
    success: bool
    lifecycle_event: Optional[Literal['awaiting_approval', 'running', 'progress']] = None
    lifecycle_seq: Optional[StrictInt] = None
    progress: Optional[dict[str, Any]] = None
    lifecycle_outcome: Optional[Literal['rejected', 'unknown']] = None
    rejection_reason: Optional[Literal['mode_deny', 'user_declined', 'approval_stale']] = None
    execution_error: Optional[Literal[
        'application_error', 'platform_runtime_error', 'permission_denied', 'connection_lost', 'toolkit_denied',
    ]] = None
    error_location: Optional[dict[str, Any]] = None
    output_permission: Optional[StrictBool] = None
    execution_ms: Optional[StrictInt] = None
    error_chain: Optional[list[dict[str, Any]]] = None
    stack: Optional[list[dict[str, Any]]] = None
    hidden_toolkit_frames: Optional[StrictInt] = None

    @model_validator(mode='after')
    def validate_lifecycle(self):
        if self.lifecycle_event is not None:
            expected = 1 if self.lifecycle_event == 'awaiting_approval' else 2
            valid = (self.lifecycle_seq is not None and 3 <= self.lifecycle_seq <= 100000 and valid_progress(self.progress)) if self.lifecycle_event == 'progress' else (self.lifecycle_seq == expected and self.progress is None)
            if not valid or self.success or self.lifecycle_outcome or self.rejection_reason:
                raise ValueError('Invalid lifecycle event')
        elif self.lifecycle_seq is not None or self.progress is not None:
            raise ValueError('Sequence requires lifecycle event')
        if self.lifecycle_outcome == 'unknown':
            if self.success or self.rejection_reason:
                raise ValueError('Unknown requires failure without rejection reason')
        elif self.lifecycle_outcome is not None:
            if self.success or self.rejection_reason is None:
                raise ValueError('Rejection requires failure and explicit reason')
        elif self.rejection_reason is not None:
            raise ValueError('Reason requires rejection outcome')
        return self
    base: Optional[str] = None
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
    capture_target: Optional[Any] = None
    target: Optional[Literal['toolkit', 'test_client']] = None
    session_id: Optional[str] = None
    image_anonymized: Optional[bool] = None
