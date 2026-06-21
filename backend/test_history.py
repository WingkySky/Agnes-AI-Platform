import httpx
import json

BASE = 'http://localhost:8002'
client = httpx.Client(timeout=30)

# 1. 测试未登录（匿名）
print('=== 1. 未登录请求 /api/history ===')
r = client.get(f'{BASE}/api/history')
print(f'Status: {r.status_code}')
data = r.json()
print(f'Total: {data.get("total", 0)}, Items: {len(data.get("items", []))}')
print(f'Items (first 3 user_ids): {[item.get("user_id") for item in data.get("items", [])[:3]]}')
print()

# 2. 登录用户 1
print('=== 2. 登录用户 xintiandi121 (密码 test123456) ===')
login = client.post(f'{BASE}/api/auth/login', json={'username': 'xintiandi121', 'password': 'test123456'})
print(f'登录状态: {login.status_code}')
if login.status_code == 200:
    token_data = login.json()
    token = token_data.get('access_token') or token_data.get('data', {}).get('access_token')
    print(f'Token: {str(token)[:50]}...')
    headers = {'Authorization': f'Bearer {token}'}
    r = client.get(f'{BASE}/api/history', headers=headers)
    print(f'历史状态: {r.status_code}')
    data = r.json()
    print(f'Total: {data.get("total", 0)}, Items: {len(data.get("items", []))}')
    user_ids = [item.get("user_id") for item in data.get("items", [])[:5]]
    print(f'Items user_ids: {user_ids}')
else:
    print(f'登录失败: {login.text[:200]}')
print()

# 3. 登录用户 admin
print('=== 3. 登录用户 admin (尝试不同密码) ===')
for pwd in ['admin123', 'test123456', 'admin', 'password', '123456']:
    login2 = client.post(f'{BASE}/api/auth/login', json={'username': 'admin', 'password': pwd})
    if login2.status_code == 200:
        print(f'密码 {pwd} 成功！')
        token_data = login2.json()
        token = token_data.get('access_token') or token_data.get('data', {}).get('access_token')
        print(f'Token: {str(token)[:50]}...')
        headers = {'Authorization': f'Bearer {token}'}
        r = client.get(f'{BASE}/api/history', headers=headers)
        print(f'历史状态: {r.status_code}')
        data = r.json()
        print(f'Total: {data.get("total", 0)}, Items: {len(data.get("items", []))}')
        user_ids = [item.get("user_id") for item in data.get("items", [])[:5]]
        print(f'Items user_ids: {user_ids}')
        break
    else:
        print(f'密码 {pwd} 失败: {login2.status_code}')

client.close()
