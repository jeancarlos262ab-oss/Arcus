"""Sample module B for graph builder testing."""
from typing import Optional

from sample_module_a import process_data, DataProcessor


def transform_record(record: dict) -> dict:
    """Transform a single record using the processor."""
    return process_data(record)


class RecordManager:
    """Manages records using DataProcessor."""

    def __init__(self) -> None:
        """Initialize the manager."""
        self.processor = DataProcessor("manager")
        self.records: list[dict] = []

    def add_record(self, record: dict) -> None:
        """Add a record to the manager."""
        processed = self.processor.process(record)
        self.records.append(processed)

    def get_record(self, index: int) -> Optional[dict]:
        """Retrieve a record by index."""
        if 0 <= index < len(self.records):
            return self.records[index]
        return None

    def transform_all(self) -> list[dict]:
        """Transform all records."""
        return [transform_record(r) for r in self.records]
