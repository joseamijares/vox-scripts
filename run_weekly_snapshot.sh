#!/bin/bash
# Weekly Portfolio Snapshot Runner
# Extracts the Telegram summary from weekly_portfolio.py output

cd ~/.hermes/scripts
python3 weekly_portfolio.py | awk '/---TELEGRAM_SUMMARY_START---/{flag=1;next}/---TELEGRAM_SUMMARY_END---/{flag=0}flag'
