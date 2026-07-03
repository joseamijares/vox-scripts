#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_discovery_pipeline

vox_discovery_pipeline.main()
