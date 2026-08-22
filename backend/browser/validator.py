from urllib.parse import urlparse

from backend.browser.schemas import BrowserAction


class ActionValidator:
    """
    Deterministic safety and validity checks for browser actions.

    The agent never directly controls the browser.
    Every action passes through this validator first.
    """

    BLOCKED_SCHEMES = {
        "javascript",
        "file",
        "data",
        "vbscript",
    }

    def validate(
        self,
        action: BrowserAction,
    ) -> None:
        if action.action == "navigate":
            self._validate_navigate(action)

        elif action.action == "click":
            self._require_selector(action)

        elif action.action == "type":
            self._require_selector(action)

            if action.text is None:
                raise ValueError(
                    "Type action requires 'text'"
                )

        elif action.action == "screenshot":
            if not action.path:
                raise ValueError(
                    "Screenshot action requires 'path'"
                )

        elif action.action in {
            "back",
            "forward",
            "refresh",
        }:
            return

        else:
            raise ValueError(
                f"Unsupported browser action: "
                f"{action.action}"
            )

    def _validate_navigate(
        self,
        action: BrowserAction,
    ) -> None:
        if not action.url:
            raise ValueError(
                "Navigate action requires 'url'"
            )

        parsed = urlparse(action.url)

        if parsed.scheme.lower() in (
            self.BLOCKED_SCHEMES
        ):
            raise ValueError(
                f"Blocked navigation scheme: "
                f"{parsed.scheme}"
            )

        if parsed.scheme.lower() not in {
            "http",
            "https",
        }:
            raise ValueError(
                "Navigation URL must use "
                "http or https"
            )

        if not parsed.netloc:
            raise ValueError(
                "Navigation URL must contain "
                "a valid host"
            )

    def _require_selector(
        self,
        action: BrowserAction,
    ) -> None:
        if not action.selector:
            raise ValueError(
                f"{action.action} action "
                "requires 'selector'"
            )

        if not action.selector.strip():
            raise ValueError(
                f"{action.action} action "
                "requires a non-empty selector"
            )
