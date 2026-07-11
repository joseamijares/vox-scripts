#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_filing_summarizer import main

if __name__ == '__main__':
    main(limit=10, store_db=True)
