# Breaking Shock Monitor (2026-07-13)

## What
`vox_intel_suite.py` mode `breaking` + wrapper `vox_intel_breaking_run.py`

## Crons
- `vox-intel-breaking` — `0 6,9,12,15,18 * * 1-5` CT
- `vox-intel-breaking-weekend` — `0 9,17 * * 0,6` CT

## Also fixed same day
- `vox_data_health.py` — latest-per-ticker grade freshness (no more false 35 confidence)
- `vox_mandatory_checklist.py` — psycopg2, never blank PGPASSWORD, exit 1 on fail
- `vox_obsidian_compound.py` — open issues + Breaking-LATEST link

## Artifacts
- `~/.hermes/cron/output/intel/breaking_YYYY-MM-DD.{json,md}`
- Obsidian `vox/memory/decisions/Breaking-YYYY-MM-DD.md` + `Breaking-LATEST.md`
