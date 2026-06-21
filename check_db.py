import sqlite3
import os

# 查找数据库文件
db_path = None
for f in ['agnes_platform.db', 'app.db', 'database.db', 'backend/agnes_platform.db', 'backend/app.db']:
    if os.path.exists(f):
        db_path = f
        break
if not db_path:
    for root, dirs, files in os.walk('.'):
        for f in files:
            if f.endswith('.db') and 'node_modules' not in root:
                db_path = os.path.join(root, f)
                break
        if db_path:
            break

print(f'DB 路径: {db_path}')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. generations 表字段
cursor.execute("PRAGMA table_info(generations)")
print("\n=== generations 表字段 ===")
for c in cursor.fetchall():
    print(f"  {c}")

# 2. 按 type+user_id 分组统计
cursor.execute("SELECT type, user_id, COUNT(*) FROM generations GROUP BY type, user_id")
print("\n=== 按 type+user_id 分组统计 ===")
for row in cursor.fetchall():
    print(f"  type={row[0]}, user_id={row[1]}, count={row[2]}")

# 3. 用户表
cursor.execute("SELECT id, username, role FROM users")
print("\n=== 用户表 ===")
for u in cursor.fetchall():
    print(f"  id={u[0]}, username={u[1]}, role={u[2]}")

# 4. user_id IS NULL 的记录
cursor.execute("SELECT type, COUNT(*) FROM generations WHERE user_id IS NULL GROUP BY type")
print("\n=== user_id 为 NULL 的记录 ===")
for row in cursor.fetchall():
    print(f"  type={row[0]}, count={row[1]}")

# 5. 查看最新视频记录
cursor.execute("SELECT id, user_id, status, result_url FROM generations WHERE type='video' ORDER BY id DESC LIMIT 10")
print("\n=== 最新 10 条视频记录 ===")
for v in cursor.fetchall():
    url = v[3][:60] + '...' if v[3] else '(空)'
    print(f"  id={v[0]}, user_id={v[1]}, status={v[2]}, url={url}")

conn.close()
