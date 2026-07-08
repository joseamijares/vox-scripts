import subprocess, os

with open('/Users/jos/.hermes/.env', 'r') as f:
    env_content = f.read()

for line in env_content.split('\n'):
    if line.startswith('DB_PASSWORD'):
        DB_PASSWORD=*** 1)[1].strip()
        break

env = {'PGPASSWORD': DB_PASSWORD}
result = subprocess.run(['psql', '-h', 'acela.proxy.rlwy.net', '-p', '35577', '-U', 'postgres', '-d', 'railway', '-t', '-c', 'ALTER TABLE earnings_calendar ADD COLUMN IF NOT EXISTS report_time VARCHAR(20)'], capture_output=True, text=True, env=env)
print(result.stdout)
print(result.stderr)
