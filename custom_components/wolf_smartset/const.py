"""Constants for the Wolf SmartSet integration."""

from datetime import timedelta
import logging

DOMAIN = "wolf_smartset"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "WOLF"

CONF_SYSTEMS = "systems"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DRY_RUN = "dry_run"
CONF_MAX_WRITES_PER_HOUR = "max_writes_per_hour"

DEFAULT_SCAN_INTERVAL = 120  # seconds, ADR-Polling-003
MIN_SCAN_INTERVAL = 60  # MaxSystemBusSamplingRateSec of the portal
DEFAULT_DRY_RUN = True  # nothing is written until the user switches this off
DEFAULT_MAX_WRITES_PER_HOUR = 20  # ADR-Writes-012
MAX_BACKOFF = timedelta(hours=1)
BACKOFF_ISSUE_STEPS = 3
DESCRIPTION_MAX_AGE = timedelta(days=1)
