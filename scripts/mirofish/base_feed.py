#!/usr/bin/env python3
"""
DataFeed protocol — structural interface for all mirofish data feeds.
Feeds satisfy this protocol by providing source_name, fetch(), and get_cached()
at module level. No inheritance required.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class DataFeed(Protocol):
    source_name: str

    def fetch(self) -> list[dict]: ...
    def get_cached(self) -> list[dict]: ...
