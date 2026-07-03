import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2, os, json
from psycopg2.extras import RealDictCursor

host = os.environ.get("PGHOST", "acela.proxy.rlwy.net")
port = os.environ.get("PGPORT", "35577")
db = os.environ.get("PGDATABASE", "railway")
user = os.environ.get("PGUSER", "postgres")
pw = os.environ.get("PGPASSWORD", "")

if not pw:
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("PGPASSWORD="):
                    pw = line.strip().split("=", 1)[1].strip('"')
                if line.startswith("PGHOST="):
                    host = line.strip().split("=", 1)[1].strip('"')
                if line.startswith("PGPORT="):
                    port = line.strip().split("=", 1)[1].strip('"')

conn = psycopg2.connect(host=host, port=port, database=db, user=user, password=pw)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("COUNCIL AUDIT (CONTINUED)")
print("=" * 60)

# Check sp500_grades columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'sp500_grades' ORDER BY ordinal_position
""")
print("\n--- sp500_grades COLUMNS ---")
for row in cur.fetchall():
    print(f"  {row['column_name']}")

# Check vox_grades columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'vox_grades' ORDER BY ordinal_position
""")
print("\n--- vox_grades COLUMNS ---")
for row in cur.fetchall():
    print(f"  {row['column_name']}")

# Grade diversity in sp500_grades
print("\n--- GRADE DIVERSITY (sp500_grades) ---")
cur.execute("""
    SELECT COUNT(DISTINCT vox_grade) as grade_unique,
           COUNT(DISTINCT technical_score) as tech_unique,
           COUNT(DISTINCT fundamental_score) as fund_unique,
           COUNT(DISTINCT macro_score) as macro_unique,
           COUNT(DISTINCT sector_score) as sector_unique,
           COUNT(DISTINCT weather_score) as weather_unique,
           COUNT(DISTINCT sentiment_score) as sentiment_unique
    FROM sp500_grades
""")
row = cur.fetchone()
for k, v in row.items():
    status = "OK" if v > 5 else "WARNING"
    print(f"  [{status}] {k}: {v} unique values")

# Grade distribution
print("\n--- GRADE DISTRIBUTION (sp500_grades) ---")
cur.execute("""
    SELECT vox_grade, COUNT(*) as n
    FROM sp500_grades
    GROUP BY vox_grade
    ORDER BY vox_grade
""")
for row in cur.fetchall():
    print(f"  Grade {row['vox_grade']}: {row['n']} tickers")

# positions.grade vs sp500_grades.vox_grade for all S&P positions
print("\n--- POSITIONS.GRADE vs SP500_GRADES.VOX_GRADE (all S&P positions) ---")
cur.execute("""
    SELECT p.ticker, p.grade as pos_grade, s.vox_grade as sp_grade,
           p.council, p.live_value
    FROM positions p
    JOIN sp500_grades s ON p.ticker = s.ticker
    WHERE p.grade != s.vox_grade
    ORDER BY p.live_value DESC
""")
mismatches = cur.fetchall()
print(f"  Total mismatches: {len(mismatches)}")
for row in mismatches[:15]:
    print(f"    {row['ticker']}: pos={row['pos_grade']}, sp500={row['sp_grade']}, council={row['council']}, value=${row['live_value']:.0f}")

conn.close()
print("\n" + "=" * 60)
print("END COUNCIL AUDIT 2")
print("=" * 60)
