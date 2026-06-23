#!/usr/bin/env python3
"""
Agnes Video V2.0 极限参数测试脚本

测试目标：
  1. 各 FPS（24/30/60）的最大秒数
  2. 各 FPS 的最高可用分辨率

测试策略：
  - 文生视频（无需图片），只测 API 能否接受请求
  - 通过 HTTP 状态码初步判断：202=接受，400/422=参数非法
  - 不等待任务完成（异步），只验证请求是否被服务端接受
"""

import httpx
import asyncio
import json
from itertools import product

# ── 配置 ──────────────────────────────────────────────
API_KEY = "sk-KNdtRXxslHMgqX3BEEyk6lYunvfvawvkyiehgT8gHS4JkWth"
BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = "agnes-video-v2.0"

# 官方 num_frames 有效值（8n+1）
VALID_NUM_FRAMES = [81, 121, 161, 241, 441]

# 要测试的 FPS
FPS_VALUES = [24, 30, 60]

# 要测试的分辨率组合 (width, height)
RESOLUTION_PAIRS = [
    (768, 512),    # 3:2 小
    (1152, 768),   # 3:2 默认
    (1280, 720),   # 16:9 720p
    (1920, 1080),  # 16:9 1080p
    (2048, 2048),  # 1:1
    (3840, 2160),  # 4K
    (4096, 4096),  # 4K 1:1
]

PROMPT = "A calm lake at sunrise, gentle ripples, soft golden light, cinematic wide shot, no people, peaceful nature"

# ── 辅助函数 ───────────────────────────────────────────
def calc_duration(num_frames: int, fps: int) -> float:
    return num_frames / fps

async def test_video_creation(
    client: httpx.AsyncClient,
    num_frames: int,
    fps: int,
    width: int,
    height: int,
) -> dict:
    """发送一个文生视频请求，返回 (num_frames, fps, width, height, http_status, response_body)"""
    url = f"{BASE_URL}/videos"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "num_frames": num_frames,
        "frame_rate": fps,
        "width": width,
        "height": height,
    }
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
        return {
            "num_frames": num_frames,
            "fps": fps,
            "width": width,
            "height": height,
            "duration_s": calc_duration(num_frames, fps),
            "status_code": resp.status_code,
            "response": resp.json() if resp.text else {},
        }
    except Exception as e:
        return {
            "num_frames": num_frames,
            "fps": fps,
            "width": width,
            "height": height,
            "duration_s": calc_duration(num_frames, fps),
            "status_code": None,
            "error": str(e),
        }

async def run_tests():
    """测试所有 FPS × num_frames × 分辨率 组合"""
    results = []

    async with httpx.AsyncClient() as client:
        # 先测试：各 FPS 的最大 num_frames × 默认分辨率（1152×768）
        print("=" * 60)
        print("阶段 1：测试各 FPS 最大 num_frames（默认分辨率 1152×768）")
        print("=" * 60)

        for fps in FPS_VALUES:
            for nf in VALID_NUM_FRAMES:
                dur = calc_duration(nf, fps)
                r = await test_video_creation(client, nf, fps, 1152, 768)
                status = r.get("status_code") or r.get("error", "???")
                ok = "✅" if r.get("status_code") == 202 else "❌"
                print(f"  FPS={fps:2d} | frames={nf:3d} | {dur:5.2f}s | {status} {ok}")
                results.append(r)

        # 再测试：最大 num_frames(441) × 各 FPS × 各分辨率
        print()
        print("=" * 60)
        print("阶段 2：测试最大 num_frames=441 × 各 FPS × 各分辨率")
        print("=" * 60)

        for fps in FPS_VALUES:
            for w, h in RESOLUTION_PAIRS:
                nf = 441
                dur = calc_duration(nf, fps)
                r = await test_video_creation(client, nf, fps, w, h)
                status = r.get("status_code") or r.get("error", "???")
                ok = "✅" if r.get("status_code") == 202 else "❌"
                print(f"  FPS={fps:2d} | frames={nf} | {dur:5.2f}s | {w}×{h} | {status} {ok}")
                results.append(r)

    # ── 分析结果 ──────────────────────────────────────
    print()
    print("=" * 60)
    print("结果汇总")
    print("=" * 60)

    for fps in FPS_VALUES:
        print(f"\n▶ FPS={fps}")
        fps_results = [r for r in results if r["fps"] == fps]

        # 找出该 FPS 接受的 num_frames 上限
        accepted_nf = sorted(set(
            r["num_frames"] for r in fps_results
            if r.get("status_code") == 202 and r["width"] == 1152
        ), reverse=True)
        if accepted_nf:
            max_nf = accepted_nf[0]
            print(f"  最大 num_frames: {max_nf} ({calc_duration(max_nf, fps):.2f}s)")

        # 找出该 FPS 在 num_frames=441 时接受的分辨率上限
        res_results = [r for r in fps_results if r["num_frames"] == 441 and r["width"] != 1152]
        accepted_res = [(r["width"], r["height"]) for r in res_results if r.get("status_code") == 202]
        if accepted_res:
            print(f"  441 frames 时接受的最大分辨率: {accepted_res}")

    # 保存原始结果
    output_file = "video_limits_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存到 {output_file}")

if __name__ == "__main__":
    asyncio.run(run_tests())
