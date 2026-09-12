import sqlite3

conn = sqlite3.connect('agnes_platform.db')
cursor = conn.cursor()

print('=== generations 表结构 ===')
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='generations'")
for row in cursor.fetchall():
    print(row[0])

print()
print('=== 前 10 条生成记录 ===')
try:
    cursor.execute('SELECT id, user_id, type, status, substr(prompt,1,50), substr(result_url,1,60), created_at FROM generations ORDER BY id DESC LIMIT 10')
    for row in cursor.fetchall():
        print(f'id={row[0]}, user_id={row[1]}, type={row[2]}, status={row[3]}, prompt={row[4]}, url={row[5]}, created={row[6]}')
except Exception as e:
    print(f'Error: {e}')

print()
print('=== 按 user_id 分组统计 ===')
try:
    cursor.execute('SELECT user_id, type, COUNT(*) as cnt FROM generations GROUP BY user_id, type ORDER BY user_id, type')
    for row in cursor.fetchall():
        print(f'user_id={row[0]}, type={row[1]}, count={row[2]}')
except Exception as e:
    print(f'Error: {e}')

print()
print('=== users 表 ===')
try:
    cursor.execute('SELECT id, username, role, is_admin, credits FROM users')
    for row in cursor.fetchall():
        print(f'id={row[0]}, username={row[1]}, role={row[2]}, is_admin={row[3]}, credits={row[4]}')
except Exception as e:
    print(f'Error: {e}')

conn.close()
