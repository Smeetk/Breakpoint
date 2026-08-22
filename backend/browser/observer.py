from typing import Any

from playwright.async_api import Page


class PageObserver:
    def __init__(self, page: Page):
        self.page = page

    async def observe(self) -> dict[str, Any]:
        title = await self.page.title()

        text = await self.page.locator(
            "body"
        ).inner_text()

        interactive_elements = await (
            self.page.locator(
                "a, button, input, textarea, select"
            ).evaluate_all(
                """
                elements => elements.map(element => ({
                    tag: element.tagName.toLowerCase(),
                    text: (
                        element.innerText ||
                        element.value ||
                        ""
                    ).trim(),
                    type: element.getAttribute("type"),
                    id: element.id || null,
                    name: element.getAttribute("name"),
                    placeholder: element.getAttribute(
                        "placeholder"
                    ),
                    href: element.getAttribute("href")
                }))
                """
            )
        )

        return {
            "url": self.page.url,
            "title": title,
            "text": text,
            "interactive_elements": (
                interactive_elements
            ),
        }
