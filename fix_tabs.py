#!/usr/bin/env python3
import subprocess, json

COMPOSIO = "/Users/jos/.composio/composio"
P_ID = "1VpCMR9NAK0TfW43XMQn0jDvI114c2E6Hc4rpu7VguNo"
T_ID = "1O66XpOhacNCJhia8QpHu0RAIFvYozAD8a1tslY808iA"

def run(cmd, data):
    args = json.dumps(data)
    c = [COMPOSIO, "execute", cmd, "-d", args]
    r = subprocess.run(c, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except:
        return {"err": r.stdout[:200]}

# Check current tabs
r = run("GOOGLESHEETS_GET_SPREADSHEET_INFO", {"spreadsheetId": P_ID})
print("Portfolio current sheets:", [s['properties']['title'] for s in r.get('data',{}).get('sheets',[])])

r2 = run("GOOGLESHEETS_GET_SPREADSHEET_INFO", {"spreadsheetId": T_ID})
print("Trade Ideas current sheets:", [s['properties']['title'] for s in r2.get('data',{}).get('sheets',[])])
