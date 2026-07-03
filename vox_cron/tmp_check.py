import os, psycopg2

with open('/Users/jos/.hermes/.env', 'r') as f:
    env_content = f.read()

for line in env_content.split('\n'):
    if line.startswith('DB_PASSWORD'):
        DB_PASSWORD=*** 1)[1].strip()
        break

conn = psycopg2.connect(
    host='acela.proxy.rlwy.net', port=35577, database='railway',
    user='postgres', password=DB_PASSWORD
)
cur = conn.cursor()

cur.execute('SELECT COUNT(*) FROM vox_grades')
print('vox_grades:', cur.fetchone()[0], 'rows')

cur.execute('SELECT COUNT(*) FROM grade_alerts')
print('grade_alerts:', cur.fetchone()[0], 'rows')

conn.close()
