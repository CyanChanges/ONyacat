#  Copyright (c) Cyan Changes 2024. All rights reserved.

import sys
import os

from loguru import logger

logger.remove()
logger.add(sys.stderr, level=os.environ.get("LOG_LEVEL", "DEBUG"))
logger.add("connection.log")
