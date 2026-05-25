# X/Twitter Setup for Momentum Tracking

## One-Time Setup (Manual)

1. Create app at https://developer.x.com/en/portal/dashboard
2. Set redirect URI to `http://localhost:8080/callback`
3. Get Client ID and Client Secret
4. Register:
```bash
xurl auth apps add openclaw-app --client-id YOUR_ID --client-secret YOUR_SECRET
```
5. Authenticate:
```bash
xurl auth oauth2 --app openclaw-app YOUR_USERNAME
xurl auth default openclaw-app
```
6. Verify:
```bash
xurl auth status
xurl whoami
```

## After Setup, momentum tracker will auto-search X for:
- CEG, VST (AI Energy)
- NVDA, AVGO, VRT (AI Supply Chain)
- RKLB, ASTS (Space)
- SOL, BTC, ETH (Crypto)

## Cron Jobs Active:
- x-momentum-daily: Every day 4:00 PM
- volume-scan-daily: Weekdays 9:00 AM
- openclaw-pipeline: Fridays 9:00 AM
- weekly-portfolio: Fridays 9:00 AM
