from __future__ import annotations

from selenium.webdriver.common.by import By

from erarta_scraper.config import Settings
from erarta_scraper.exceptions import BrowserError
from erarta_scraper.scraping.browser import BrowserSession
from erarta_scraper.scraping.selectors import CatalogLocators


def catalog_page_url(settings: Settings, page_index: int) -> str:
    base = settings.catalog_base_url.rstrip("/")
    return f"{base}/?pageIndex={page_index}"


def extract_links_from_page(browser: BrowserSession, page_index: int) -> list[str]:
    selector = CatalogLocators.product_cards(page_index)
    try:
        cards = browser.wait_css(selector)
    except BrowserError:
        return []
    links: list[str] = []
    for card in cards:
        href = card.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
        if href:
            links.append(href)
    return links


def collect_catalog_links(
    browser: BrowserSession,
    settings: Settings,
    pages_count: int,
) -> list[str]:
    collected: list[str] = []
    for page_index in range(1, pages_count + 1):
        browser.get(catalog_page_url(settings, page_index))
        collected.extend(extract_links_from_page(browser, page_index))
    return collected
