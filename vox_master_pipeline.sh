#!/bin/bash
# VOX Master Pipeline — Autonomous Daily Run
# Runs: data refresh → grading → briefing → deploy

set -e

echo "=========================================="
echo "VOX MASTER PIPELINE — $(date)"
echo "=========================================="

# 1. Validate data (reads real broker files)
echo ""
echo "📊 Step 1: Data Validation"
cd /Users/jos/.hermes/scripts
python3 vox_data_validator.py

# 2. Grade all positions
echo ""
echo "📈 Step 2: Grading"
python3 vox_batch_grade.py

# 3. Generate daily briefing
echo ""
echo "🧠 Step 3: Daily Briefing"
python3 vox_daily_briefing.py

# 4. Build and deploy dashboard
echo ""
echo "🚀 Step 4: Deploy Dashboard"
cd /Users/jos/dev/vox-dashboard
npm run build
vercel deploy --prod --yes

echo ""
echo "=========================================="
echo "✅ PIPELINE COMPLETE — $(date)"
echo "=========================================="
