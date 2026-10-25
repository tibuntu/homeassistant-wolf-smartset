"""Constants for the Wolf SmartSet integration."""

from datetime import timedelta
import logging

DOMAIN = "wolf_smartset"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "WOLF"

CONF_SYSTEMS = "systems"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 120  # seconds, ADR-Polling-003
MIN_SCAN_INTERVAL = 60  # MaxSystemBusSamplingRateSec of the portal
MAX_BACKOFF = timedelta(hours=1)
BACKOFF_ISSUE_STEPS = 3
DESCRIPTION_MAX_AGE = timedelta(days=1)
