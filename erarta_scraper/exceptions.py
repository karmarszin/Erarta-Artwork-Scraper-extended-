class ScraperError(Exception):
    """Base error for the ETL pipeline."""


class ParseError(ScraperError):
    """Page loaded but required fields could not be extracted."""


class BrowserError(ScraperError):
    """WebDriver failed to load or locate page content."""


class QueueError(ScraperError):
    """Task-queue / persistence failure."""
