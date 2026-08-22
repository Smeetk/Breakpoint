from typing import Literal

from pydantic import BaseModel, Field


class BrowserAction(BaseModel):
    action: Literal[
        "navigate",
        "click",
        "type",
        "back",
        "forward",
        "refresh",
        "screenshot",
    ]

    url: str | None = None

    selector: str | None = None

    text: str | None = None

    path: str | None = Field(
        default=None,
        description="Path for saving a screenshot.",
    )
