import logging
import os

logger = logging.getLogger(__name__)

# Set level from environment variable, default to ERROR to reduce noise
log_level = os.environ.get("LEXIFLOW_LOG_LEVEL", "ERROR").upper()
level = getattr(logging, log_level, logging.ERROR)
logger.setLevel(level)

handler = logging.StreamHandler()

log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
formatter = logging.Formatter(log_format)

handler.setFormatter(formatter)
logger.addHandler(handler)
