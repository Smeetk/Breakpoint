from typing import Literal

from pydantic import BaseModel


class BrowserAction(BaseModel):
    action: Literal[
        "navigate",
        "click",
        "type",
        "back",
        "forward",
        "refresh",
        "screenshot",
        "observe",
    ]

    url: str | None = None
    selector: str | None = None
    text: str | None = None
    path: str | None = None
