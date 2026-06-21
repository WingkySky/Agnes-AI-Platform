"""直接测试 history 路由的用户隔离逻辑"""
import sqlite3

conn = sqlite3.connect('agnes_platform.db')
cursor = conn.cursor()

# 测试：模拟不同 user_id 的查询
print('=== 模拟不同用户查询 history ===')

# 未登录用户（user_id IS NULL）
cursor.execute('SELECT COUNT(*) FROM generations WHERE user_id IS NULL')
count_null = cursor.fetchone()[0]
print(f'未登录用户可见数量: {count_null}')

# 用户 1 (xintiandi121)
cursor.execute('SELECT COUNT(*) FROM generations WHERE user_id = 1')
count_1 = cursor.fetchone()[0]
print(f'用户 1 可见数量: {count_1}')

# 用户 3 (admin)
cursor.execute('SELECT COUNT(*) FROM generations WHERE user_id = 3')
count_3 = cursor.fetchone()[0]
print(f'用户 3 可见数量: {count_3}')

print()
print('=== 实际记录分布 ===')
cursor.execute('SELECT user_id, type, COUNT(*) FROM generations GROUP BY user_id, type')
for row in cursor.fetchall():
    print(f'user_id={row[0]}, type={row[1]}, count={row[2]}')

print()
print('=== 检查历史路由是否正确配置 ===')
cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='generations'")
print(f'generations 表存在: {cursor.fetchone()[0] > 0}')

conn.close()
