from typing import Any

from playwright.async_api import Page


class PageObserver:
    def __init__(self, page: Page):
        self.page = page

    async def get_interactive_elements(self) -> list[dict[str, Any]]:
        elements = []

        locator = self.page.locator(
            "button, input, textarea, select, a"
        )

        count = await locator.count()

        for i in range(count):
            element = locator.nth(i)

            try:
                if not await element.is_visible():
                    continue

                elements.append(
                    {
                        "tag": await element.evaluate(
                            "(el) => el.tagName.toLowerCase()"
                        ),
                        "text": (await element.inner_text()).strip(),
                        "type": await element.get_attribute("type"),
                        "id": await element.get_attribute("id"),
                        "name": await element.get_attribute("name"),
                        "placeholder": await element.get_attribute(
                            "placeholder"
                        ),
                        "href": await element.get_attribute("href"),
                    }
                )

            except Exception:
                continue

        return elements

    async def observe(self) -> dict[str, Any]:
        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "text": (
                await self.page.locator("body").inner_text()
            ).strip(),
            "interactive_elements": await self.get_interactive_elements(),
        }
