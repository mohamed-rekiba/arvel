# Browser Tests

Arvel doesn't ship a browser-test driver, but **Playwright for Python** integrates with pytest out of the box and is the recommended choice.

```bash
uv add --dev playwright pytest-playwright
uv run playwright install
```

```python
import pytest
from playwright.async_api import Page


@pytest.mark.asyncio
async def test_user_can_log_in(page: Page) -> None:
    await page.goto("http://localhost:8000/login")
    await page.fill('input[name="email"]', "alice@example.com")
    await page.fill('input[name="password"]', "secret")
    await page.click('button[type="submit"]')

    await page.wait_for_url("**/dashboard")
    assert await page.locator("h1").text_content() == "Welcome, Alice"
```

## Running against the dev environment

Start the app (via `arvel serve` or Docker Compose) before running browser tests:

```bash
arvel serve &
uv run pytest tests/browser/
```

Use `pytest-playwright`'s `--browser chromium|firefox|webkit` flag to target a specific engine. Chromium is the default.

## See also

- [Testing — Getting Started](testing.md) — pytest setup and test layout.
- [Testing — HTTP Tests](http-tests.md) — lighter-weight option when you don't need a real browser.
