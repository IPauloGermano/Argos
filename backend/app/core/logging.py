"""Structured logs with required event names. Never log secrets."""
import json
import logging
import sys

_events = {
    "SEARCH_STARTED", "JOBS_FOUND", "JOBS_DEDUPLICATED", "JOBS_FILTERED",
    "MATCH_STARTED", "MATCH_COMPLETED", "NOTIFICATION_SENT",
    "NOTIFICATION_FAILED", "SEARCH_COMPLETED",
}

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
logger = logging.getLogger("hermes")


def log_event(event: str, **fields):
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, default=str))
