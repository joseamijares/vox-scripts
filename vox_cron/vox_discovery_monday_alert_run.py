#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_discovery_pipeline

# Monday alert only wrapper
class FakeArgs:
    def __init__(self):
        self.monday_alert = True

vox_discovery_pipeline.run_monday_alert_only()
