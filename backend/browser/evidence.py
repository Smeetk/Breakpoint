from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Evidence:
    action: str
    url: str

    timestamp: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )

    screenshot: str | None = None

    console_errors: list[str] = field(
        default_factory=list
    )

    failed_requests: list[dict[str, Any]] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "url": self.url,
            "timestamp": self.timestamp,
            "screenshot": self.screenshot,
            "console_errors": self.console_errors,
            "failed_requests": self.failed_requests,
        }
