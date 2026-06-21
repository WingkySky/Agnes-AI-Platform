import requests
import sys

BASE = "http://localhost:8000"

def test_user(username, password, label):
    print(f"\n{'='*60}")
    print(f"【{label}】 username={username}")
    print("="*60)

    # 1. 登录
    login_resp = requests.post(
        f"{BASE}/api/auth/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"}
    )
    print(f"登录状态码: {login_resp.status_code}")
    if login_resp.status_code != 200:
        print(f"登录失败: {login_resp.text}")
        return
    token_data = login_resp.json()
    token = token_data.get("access_token", "")
    print(f"Token: {token[:80]}...")

    # 2. 获取全部历史
    print("\n--- 全部历史 (type=all, page=1, page_size=10) ---")
    history_resp = requests.get(
        f"{BASE}/api/history",
        params={"type": "all", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"状态码: {history_resp.status_code}")
    data = history_resp.json()
    print(f"total: {data.get('total')}")
    print(f"total_image_count: {data.get('total_image_count')}")
    print(f"total_video_count: {data.get('total_video_count')}")
    print(f"items 数量: {len(data.get('items', []))}")
    for item in data.get("items", [])[:3]:
        t = item.get("type", "")
        url = (item.get("result_url") or "")[:60]
        print(f"  id={item.get('id')}, type={t}, url={url}...")

    # 3. 获取视频历史
    print("\n--- 视频历史 (type=video, page=1, page_size=10) ---")
    video_resp = requests.get(
        f"{BASE}/api/history",
        params={"type": "video", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"}
    )
    video_data = video_resp.json()
    print(f"total: {video_data.get('total')}")
    print(f"total_video_count: {video_data.get('total_video_count')}")
    print(f"items 数量: {len(video_data.get('items', []))}")
    for item in video_data.get("items", [])[:3]:
        url = (item.get("result_url") or "")[:60]
        print(f"  id={item.get('id')}, type={item.get('type')}, url={url}...")

    # 4. 获取图片历史
    print("\n--- 图片历史 (type=image, page=1, page_size=10) ---")
    image_resp = requests.get(
        f"{BASE}/api/history",
        params={"type": "image", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"}
    )
    image_data = image_resp.json()
    print(f"total: {image_data.get('total')}")
    print(f"total_image_count: {image_data.get('total_image_count')}")
    print(f"items 数量: {len(image_data.get('items', []))}")
    for item in image_data.get("items", [])[:3]:
        url = (item.get("result_url") or "")[:60]
        print(f"  id={item.get('id')}, type={item.get('type')}, url={url}...")

# 测试 admin
test_user("admin", "admin123", "超级管理员")

# 测试 test_user（新注册的用户，没有数据）
test_user("test_user", "test123456", "新用户 test_user (无数据)")

print("\n\n=== 测试完成 ===")
