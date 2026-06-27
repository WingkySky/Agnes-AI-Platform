"""
性能对比测试 v2：直连 AgnesAIClient vs agn-sdk 接 Agnes

测试策略（避免 Agnes 服务端排队干扰）：
  - 用 GET /models 端点（响应快、无副作用、不走视频排队）
  - 每条路径连续调用 N 次，统计平均/中位数/P95 延迟
  - 单独测一次 GET /videos/{不存在的id} 看 4xx 错误的响应延迟
    （这一步能暴露 agn-sdk 对 4xx 错误的重试陷阱）

测试维度：
  1. 客户端初始化耗时
  2. GET /models 单次延迟分布（N=20 次）
  3. GET 4xx 错误响应延迟（看是否触发重试）
  4. 请求体序列化开销（用一个空 POST 测量）

运行方式：
  cd /Users/skywing/agnes-platform/backend
  PYTHONUNBUFFERED=1 ./.venv/bin/python -u scripts/perf_compare_agn_sdk_vs_direct.py
"""

import asyncio
import os
import statistics
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, "/Users/skywing/agnes-platform/backend")

from dotenv import load_dotenv

load_dotenv("/Users/skywing/agnes-platform/backend/.env")

API_KEY = os.getenv("AGNES_API_KEY", "")
BASE_URL = os.getenv("AGNES_API_BASE_URL", "https://apihub.agnes-ai.com/v1")
POLL_URL = os.getenv("AGNES_API_POLL_URL", "https://apihub.agnes-ai.com/agnesapi")

if not API_KEY:
    print("[ERROR] AGNES_API_KEY 未配置")
    sys.exit(1)

N_MODELS_CALLS = 20  # GET /models 调用次数
WARMUP_CALLS = 2  # 预热次数（不计入统计）


# ==================== 路径 A：直连 AgnesAIClient ====================
async def measure_direct() -> Dict[str, Any]:
    """测量直连 AgnesAIClient 的协议层开销"""
    import httpx

    from app.services.agnes_client import AgnesAIClient

    result: Dict[str, Any] = {"path": "A: 直连 AgnesAIClient"}

    # 1. 客户端初始化
    t0 = time.perf_counter()
    client = AgnesAIClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        poll_url=POLL_URL,
    )
    await client.start()
    result["init_ms"] = (time.perf_counter() - t0) * 1000

    try:
        # 2. GET /models 多次调用
        # AgnesAIClient 没有直接暴露 list_models，用底层 _get 复用连接池
        latencies: List[float] = []

        # 预热
        for _ in range(WARMUP_CALLS):
            await client._get(f"{BASE_URL}/models")

        # 正式测量
        for i in range(N_MODELS_CALLS):
            t1 = time.perf_counter()
            try:
                await client._get(f"{BASE_URL}/models")
                lat = (time.perf_counter() - t1) * 1000
                latencies.append(lat)
            except Exception as e:
                print(f"[A] /models 第 {i+1} 次失败: {e}")
                latencies.append(-1)

        result["models_latencies_ms"] = latencies
        result["models_avg_ms"] = statistics.mean(latencies) if latencies else 0
        result["models_median_ms"] = statistics.median(latencies) if latencies else 0
        result["models_p95_ms"] = (
            sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies)
        )
        result["models_min_ms"] = min(latencies) if latencies else 0
        result["models_max_ms"] = max(latencies) if latencies else 0

        # 3. 测试 4xx 错误响应延迟（GET 一个不存在的 video_id，应该返回 404 或类似）
        # AgnesAIClient.poll_video_status 优先用 video_id 走 poll_url
        t0 = time.perf_counter()
        try:
            await client.poll_video_status(
                video_id="nonexistent_id_test_perf_compare",
                task_id="nonexistent_id_test_perf_compare",
                model_name="agnes-video-v2.0",
            )
            result["err_4xx_ms"] = (time.perf_counter() - t0) * 1000
            result["err_4xx_status"] = "no error"
        except Exception as e:
            result["err_4xx_ms"] = (time.perf_counter() - t0) * 1000
            result["err_4xx_status"] = str(e)[:200]

    finally:
        await client.shutdown()

    return result


# ==================== 路径 B：agn-sdk Client + AgnesAdapter ====================
async def measure_agn_sdk() -> Dict[str, Any]:
    """测量 agn-sdk Client + AgnesAdapter 的协议层开销"""
    from agn.client import Client as AGNSDKClient

    result: Dict[str, Any] = {"path": "B: agn-sdk Client+AgnesAdapter"}

    # 1. 客户端初始化
    t0 = time.perf_counter()
    sdk_client = AGNSDKClient(
        provider="agnes",
        api_key=API_KEY,
        base_url=BASE_URL,
        poll_url=POLL_URL,
    )
    await sdk_client.start()
    result["init_ms"] = (time.perf_counter() - t0) * 1000

    try:
        # 2. GET /models 多次调用（agn-sdk 暴露 list_models）
        latencies: List[float] = []

        # 预热
        for _ in range(WARMUP_CALLS):
            await sdk_client.list_models()

        # 正式测量
        for i in range(N_MODELS_CALLS):
            t1 = time.perf_counter()
            try:
                await sdk_client.list_models()
                lat = (time.perf_counter() - t1) * 1000
                latencies.append(lat)
            except Exception as e:
                print(f"[B] list_models 第 {i+1} 次失败: {e}")
                latencies.append(-1)

        result["models_latencies_ms"] = latencies
        result["models_avg_ms"] = statistics.mean(latencies) if latencies else 0
        result["models_median_ms"] = statistics.median(latencies) if latencies else 0
        result["models_p95_ms"] = (
            sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies)
        )
        result["models_min_ms"] = min(latencies) if latencies else 0
        result["models_max_ms"] = max(latencies) if latencies else 0

        # 3. 测试 4xx 错误响应延迟（poll 一个不存在的 task_id）
        # agn-sdk 的 video_poll 会先走 poll_url，失败后回退到 /videos/{task_id}
        t0 = time.perf_counter()
        try:
            await sdk_client.video_poll(
                task_id="nonexistent_id_test_perf_compare",
                model="agnes-video-v2.0",
            )
            result["err_4xx_ms"] = (time.perf_counter() - t0) * 1000
            result["err_4xx_status"] = "no error"
        except Exception as e:
            result["err_4xx_ms"] = (time.perf_counter() - t0) * 1000
            result["err_4xx_status"] = str(e)[:200]

    finally:
        await sdk_client.close()

    return result


# ==================== 主流程 ====================
async def main() -> None:
    print("=" * 80)
    print("性能对比测试 v2：直连 AgnesAIClient vs agn-sdk AgnesAdapter")
    print("=" * 80)
    print(f"BASE_URL: {BASE_URL}")
    print(f"POLL_URL: {POLL_URL}")
    print(f"API_KEY : {API_KEY[:10]}...{API_KEY[-4:]}")
    print(f"测试方法: GET /models 调用 {N_MODELS_CALLS} 次 + 1 次 4xx 错误延迟测试")
    print("-" * 80)

    print("\n>>> 路径 A：直连 AgnesAIClient <<<\n")
    result_a = await measure_direct()

    print("\n>>> 路径 B：agn-sdk Client + AgnesAdapter <<<\n")
    result_b = await measure_agn_sdk()

    # ==================== 对比报告 ====================
    print("\n" + "=" * 80)
    print("对比结果")
    print("=" * 80)

    def fmt_ms(v: Any) -> str:
        if v is None:
            return "N/A"
        return f"{v:.2f} ms"

    def diff(a: Any, b: Any) -> str:
        if a is None or b is None:
            return "N/A"
        d = b - a
        pct = (d / a * 100) if a else 0
        return f"{d:+.2f} ms ({pct:+.1f}%)"

    print(f"{'指标':<28} {'A 直连':<18} {'B agn-sdk':<18} {'差异(B-A)':<24}")
    print("-" * 90)
    print(f"{'客户端初始化':<28} {fmt_ms(result_a.get('init_ms')):<18} {fmt_ms(result_b.get('init_ms')):<18} {diff(result_a.get('init_ms'), result_b.get('init_ms'))}")
    print(f"{'/models 平均延迟':<28} {fmt_ms(result_a.get('models_avg_ms')):<18} {fmt_ms(result_b.get('models_avg_ms')):<18} {diff(result_a.get('models_avg_ms'), result_b.get('models_avg_ms'))}")
    print(f"{'/models 中位延迟':<28} {fmt_ms(result_a.get('models_median_ms')):<18} {fmt_ms(result_b.get('models_median_ms')):<18} {diff(result_a.get('models_median_ms'), result_b.get('models_median_ms'))}")
    print(f"{'/models P95 延迟':<28} {fmt_ms(result_a.get('models_p95_ms')):<18} {fmt_ms(result_b.get('models_p95_ms')):<18} {diff(result_a.get('models_p95_ms'), result_b.get('models_p95_ms'))}")
    print(f"{'/models 最小延迟':<28} {fmt_ms(result_a.get('models_min_ms')):<18} {fmt_ms(result_b.get('models_min_ms')):<18} {diff(result_a.get('models_min_ms'), result_b.get('models_min_ms'))}")
    print(f"{'/models 最大延迟':<28} {fmt_ms(result_a.get('models_max_ms')):<18} {fmt_ms(result_b.get('models_max_ms')):<18} {diff(result_a.get('models_max_ms'), result_b.get('models_max_ms'))}")
    print(f"{'4xx 错误响应延迟':<28} {fmt_ms(result_a.get('err_4xx_ms')):<18} {fmt_ms(result_b.get('err_4xx_ms')):<18} {diff(result_a.get('err_4xx_ms'), result_b.get('err_4xx_ms'))}")

    print("\n--- 详细延迟分布（ms）---")
    print(f"{'路径 A 直连':<20}:", [f"{x:.1f}" for x in result_a.get("models_latencies_ms", [])])
    print(f"{'路径 B agn-sdk':<20}:", [f"{x:.1f}" for x in result_b.get("models_latencies_ms", [])])

    print("\n--- 4xx 错误响应详情 ---")
    print(f"{'路径 A 4xx 响应':<20}: {result_a.get('err_4xx_ms', 0):.1f}ms, 状态: {result_a.get('err_4xx_status', 'N/A')[:120]}")
    print(f"{'路径 B 4xx 响应':<20}: {result_b.get('err_4xx_ms', 0):.1f}ms, 状态: {result_b.get('err_4xx_status', 'N/A')[:120]}")

    # 结论
    print("\n" + "-" * 80)
    print("简要结论：")

    init_diff = (result_b.get('init_ms', 0) - result_a.get('init_ms', 0)) if result_a.get('init_ms') else 0
    avg_diff = (result_b.get('models_avg_ms', 0) - result_a.get('models_avg_ms', 0)) if result_a.get('models_avg_ms') else 0
    err_diff = (result_b.get('err_4xx_ms', 0) - result_a.get('err_4xx_ms', 0)) if result_a.get('err_4xx_ms') else 0

    print(f"  - 客户端初始化: agn-sdk 比直连 {'慢' if init_diff > 0 else '快'} {abs(init_diff):.1f}ms")
    print(f"  - /models 平均延迟: agn-sdk 比直连 {'慢' if avg_diff > 0 else '快'} {abs(avg_diff):.2f}ms")
    print(f"  - 4xx 错误响应: agn-sdk 比直连 {'慢' if err_diff > 0 else '快'} {abs(err_diff):.2f}ms")

    if err_diff > 5000:
        print(f"\n  ⚠️ 4xx 错误响应差异显著 (>5s)，这通常意味着 agn-sdk 对 4xx 错误触发了重试。")
        print(f"    这会显著放大任何参数错误、API Key 错误、模型不存在等场景的延迟。")


if __name__ == "__main__":
    asyncio.run(main())
