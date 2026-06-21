"""用 FastAPI TestClient 测试用户隔离"""
import sys
sys.path.insert(0, '/Users/skywing/agnes-platform/backend')

from app.core.security import create_access_token

# 创建两个用户的 token
token_user_1 = create_access_token(user_id=1)
token_user_3 = create_access_token(user_id=3)

print(f'用户 1 token: {token_user_1[:50]}...')
print(f'用户 3 token: {token_user_3[:50]}...')
print()

# 直接用 httpx 调用测试（确保用正确的异步客户端）
import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8003', timeout=30) as client:
        # 1. 未登录
        print('=== 1. 未登录请求 ===')
        r = await client.get('/api/history')
        print(f'Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            print(f'Total: {data.get("total")}, items: {len(data.get("items", []))}')
            for item in data.get("items", [])[:3]:
                print(f'  id={item.get("id")}, user_id={item.get("user_id")}, prompt={str(item.get("prompt", ""))[:30]}')
        else:
            print(f'Body: {r.text[:300]}')
        print()

        # 2. 用户 1
        print('=== 2. 用户 1 (id=1) ===')
        headers = {'Authorization': f'Bearer {token_user_1}'}
        r = await client.get('/api/history', headers=headers)
        print(f'Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            print(f'Total: {data.get("total")}, items: {len(data.get("items", []))}')
            for item in data.get("items", [])[:3]:
                print(f'  id={item.get("id")}, user_id={item.get("user_id")}, prompt={str(item.get("prompt", ""))[:30]}')
        else:
            print(f'Body: {r.text[:300]}')
        print()

        # 3. 用户 3
        print('=== 3. 用户 3 (id=3, admin) ===')
        headers = {'Authorization': f'Bearer {token_user_3}'}
        r = await client.get('/api/history', headers=headers)
        print(f'Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            print(f'Total: {data.get("total")}, items: {len(data.get("items", []))}')
            for item in data.get("items", [])[:3]:
                print(f'  id={item.get("id")}, user_id={item.get("user_id")}, prompt={str(item.get("prompt", ""))[:30]}')
        else:
            print(f'Body: {r.text[:300]}')

asyncio.run(test())
