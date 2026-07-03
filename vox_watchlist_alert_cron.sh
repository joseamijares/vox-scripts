#!/bin/bash
# VOX Daily Alert Cron - Runs at 9:00 AM, 12:00 PM, 3:00 PM CT
# Checks for grade threshold crossings and sends Telegram alerts

cd /Users/jos/.hermes/scripts
python3 vox_alert_system_v2.py --watchlist --telegram
