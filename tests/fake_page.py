"""A minimal stand-in for Playwright's Page/Locator API.

`linkedin_page.py` is the layer that actually talks to LinkedIn, and it was at
0% coverage because importing it required Playwright. It is import-safe now, so
this double lets the selector logic be exercised in CI without a browser.

Locators are registered by a canonical key so a test says what the page
contains, and anything unregistered resolves to an empty locator — which is
exactly what a LinkedIn markup change looks like.

Keys:
    "css:<selector>"            page.locator(sel) / card.locator(sel)
    "role:<role>:<name>"        page.get_by_role(role, name=...)
    "label:<name>"              page.get_by_label(name)
"""

from __future__ import annotations

import re


def canonical(kind: str, *parts) -> str:
    out = [kind]
    for part in parts:
        if isinstance(part, re.Pattern):
            out.append(part.pattern)
        else:
            out.append(str(part))
    return ":".join(out)


class FakeElement:
    """One matched element."""

    def __init__(self, text="", attributes=None, href=None):
        self.text = text
        self.attributes = dict(attributes or {})
        if href is not None:
            self.attributes["href"] = href
        self.clicked = 0
        self.filled: list[str] = []
        self.uploaded: list[str] = []
        self.scrolled = 0

    # -- Playwright Locator surface used by LinkedInPage ---------------------
    def click(self):
        self.clicked += 1

    def fill(self, value):
        self.filled.append(value)

    def text_content(self):
        return self.text

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.attributes.get(name)

    def scroll_into_view_if_needed(self):
        self.scrolled += 1

    def set_input_files(self, path):
        self.uploaded.append(path)

    def wait_for(self, timeout=None):
        return None


class FakeLocator:
    """A match set. `.first`/`.nth()` narrow it, like Playwright's."""

    def __init__(self, page, elements):
        self._page = page
        self._elements = list(elements)

    def count(self):
        return len(self._elements)

    @property
    def first(self):
        if self._elements and isinstance(self._elements[0], FakeCard):
            return self._elements[0]
        return FakeLocator(self._page, self._elements[:1])

    def nth(self, index):
        if index >= len(self._elements):
            return FakeLocator(self._page, [])
        item = self._elements[index]
        # A card keeps its own child registry; narrowing must not flatten it.
        if isinstance(item, FakeCard):
            return item
        return FakeLocator(self._page, [item])

    def _one(self):
        if not self._elements:
            raise AssertionError("operated on an empty locator")
        return self._elements[0]

    def click(self):
        self._one().click()

    def fill(self, value):
        self._one().fill(value)

    def text_content(self):
        return self._one().text_content()

    def inner_text(self):
        return self._one().inner_text()

    def get_attribute(self, name):
        return self._one().get_attribute(name)

    def scroll_into_view_if_needed(self):
        self._one().scroll_into_view_if_needed()

    def set_input_files(self, path):
        self._one().set_input_files(path)

    def wait_for(self, timeout=None):
        if not self._elements:
            raise TimeoutError("locator never appeared")

    # nested lookups scoped to this element (cards)
    def locator(self, selector):
        return self._page._resolve(canonical("css", selector), scope=self)

    def get_by_role(self, role, name=None):
        return self._page._resolve(canonical("role", role, name), scope=self)


class FakeCard(FakeLocator):
    """A feed/search card whose children are registered per-card."""

    def __init__(self, page, children=None):
        super().__init__(page, [FakeElement()])
        self.children = dict(children or {})

    def locator(self, selector):
        return FakeLocator(self._page, self.children.get(canonical("css", selector), []))

    def get_by_role(self, role, name=None):
        return FakeLocator(self._page, self.children.get(canonical("role", role, name), []))


class FakePage:
    """Registry-backed Page double.

    `register(key, elements)` declares what the page contains. Anything not
    registered comes back empty.
    """

    def __init__(self, url="https://www.linkedin.com/feed/", registry=None):
        self.url = url
        self.registry: dict[str, list] = dict(registry or {})
        self.visited: list[str] = []
        self.evaluated: list[str] = []
        self.waits = 0
        self.wait_for_url_fails = False

    # -- test-facing helpers -------------------------------------------------
    def register(self, key, elements):
        self.registry[key] = elements if isinstance(elements, list) else [elements]
        return self

    def register_css(self, selector, elements):
        return self.register(canonical("css", selector), elements)

    def register_role(self, role, name, elements):
        return self.register(canonical("role", role, name), elements)

    def register_label(self, name, elements):
        return self.register(canonical("label", name), elements)

    # -- Playwright Page surface --------------------------------------------
    def _resolve(self, key, scope=None):
        return FakeLocator(self, self.registry.get(key, []))

    def goto(self, url):
        self.visited.append(url)
        self.url = url

    def locator(self, selector):
        return self._resolve(canonical("css", selector))

    def get_by_role(self, role, name=None):
        return self._resolve(canonical("role", role, name))

    def get_by_label(self, name):
        return self._resolve(canonical("label", name))

    def wait_for_url(self, pattern, timeout=None):
        if self.wait_for_url_fails:
            raise TimeoutError("navigation never completed")

    def wait_for_load_state(self, state, timeout=None):
        return None

    def wait_for_timeout(self, ms):
        self.waits += 1

    def evaluate(self, script):
        self.evaluated.append(script)
