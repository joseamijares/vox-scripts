#!/usr/bin/env python3
"""VOX Hybrid Price Feed — Fast hourly wrapper.
Updates positions and broker_positions (no vox_grades) to fit in 120s cron window.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vox_hybrid_price_feed as pf

conn = pf.connect()
cur = conn.cursor()
pos_tickers, broker_tickers, _ = pf.get_tickers_with_old_prices(cur)
cur.close()
conn.close()

pf.update_prices(pos_tickers, table='positions')
pf.update_prices(broker_tickers, table='broker_positions')
pf.show_price_summary()
