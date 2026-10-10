"""Errors shared by the agent loop and the browser, importable without browser_harness."""


class StalePage(ValueError):
    """A decision no longer refers to the observed page."""
