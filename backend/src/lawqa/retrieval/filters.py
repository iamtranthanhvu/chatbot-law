from datetime import UTC, date, datetime

from qdrant_client import models


def valid_at(reference_date: date) -> models.Filter:
    """Chunks in force on `reference_date`: valid_from <= d < valid_to (missing bounds = open)."""
    moment = datetime(reference_date.year, reference_date.month, reference_date.day, tzinfo=UTC)
    return models.Filter(
        must=[
            models.Filter(
                should=[
                    models.IsEmptyCondition(is_empty=models.PayloadField(key="valid_from")),
                    models.FieldCondition(key="valid_from", range=models.DatetimeRange(lte=moment)),
                ]
            ),
            models.Filter(
                should=[
                    models.IsEmptyCondition(is_empty=models.PayloadField(key="valid_to")),
                    models.FieldCondition(key="valid_to", range=models.DatetimeRange(gt=moment)),
                ]
            ),
        ]
    )
