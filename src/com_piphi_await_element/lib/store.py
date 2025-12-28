

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import  logger

devices: Dict[str, Dict] = {}
