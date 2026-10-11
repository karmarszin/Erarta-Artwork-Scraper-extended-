from __future__ import annotations

from types import TracebackType

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from erarta_scraper.config import Settings
from erarta_scraper.exceptions import BrowserError
from erarta_scraper.scraping.pace import Pace


def build_chrome(settings: Settings) -> WebDriver:
    options = Options()
    if settings.headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,720")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise BrowserError("failed to start Chrome WebDriver") from exc


class BrowserSession:
    def __init__(self, settings: Settings, driver: WebDriver | None = None) -> None:
        self.settings = settings
        self._owned = driver is None
        self.driver = driver or build_chrome(settings)
        self.pace = Pace(settings.request_delay_seconds)

    def __enter__(self) -> BrowserSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owned:
            self.driver.quit()

    def get(self, url: str) -> None:
        self.pace.wait()
        try:
            self.driver.get(url)
        except WebDriverException as exc:
            raise BrowserError(f"failed to open {url}") from exc

    def wait_css(self, selector: str, timeout: float | None = None) -> list:
        wait = WebDriverWait(self.driver, timeout or self.settings.page_wait_seconds)
        try:
            return wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
        except TimeoutException as exc:
            raise BrowserError(f"timeout waiting for {selector}") from exc

    def text_or_empty(self, xpath: str) -> str:
        try:
            return self.driver.find_element(By.XPATH, xpath).text.strip()
        except NoSuchElementException:
            return ""
