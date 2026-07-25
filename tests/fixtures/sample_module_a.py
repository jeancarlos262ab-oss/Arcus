"""Sample module A for graph builder testing."""
import os
from pathlib import Path


def process_data(data: dict) -> dict:
    """Process input data and return result."""
    return {k: v.upper() if isinstance(v, str) else v for k, v in data.items()}


def validate_config(config: dict) -> bool:
    """Validate configuration dictionary."""
    required_keys = {"host", "port"}
    return all(key in config for key in required_keys)


class DataProcessor:
    """Main data processing class."""

    def __init__(self, name: str) -> None:
        """Initialize processor with a name."""
        self.name = name
        self.processed_count = 0

    def process(self, data: dict) -> dict:
        """Process data and track count."""
        result = process_data(data)
        self.processed_count += 1
        return result

    def validate(self) -> bool:
        """Validate internal state."""
        return self.name is not None and self.processed_count >= 0

    def _internal_helper(self) -> str:
        """Internal helper method (private)."""
        return f"Helper for {self.name}"


class AdvancedProcessor(DataProcessor):
    """Extended data processor with additional features."""

    def __init__(self, name: str, debug: bool = False) -> None:
        """Initialize with debug flag."""
        super().__init__(name)
        self.debug = debug

    def process(self, data: dict) -> dict:
        """Override process with debug support."""
        if self.debug:
            print(f"Processing: {data}")
        return super().process(data)
