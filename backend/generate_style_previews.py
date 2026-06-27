# =====================================================
# 风格元素缩略图生成脚本
# 功能：用 Agnes Image API 为每个内置风格元素生成代表性缩略图
# 使用方式（在 backend 目录下）：
#   python3 generate_style_previews.py
#
# 注意：
# - 会消耗 Agnes Image API 额度（每个元素 1 张 512x512）
# - 已存在缩略图的元素会跳过（幂等）
# - 生成的图片保存到 data/style_previews/{key}.png
# =====================================================

import asyncio
import logging
import os
import sys

# 允许直接以脚本形式运行
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.style_element import StyleElement
from app.services.agnes_client import agnes_client

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_style_previews")

# 缩略图存放目录
PREVIEW_DIR = os.path.join(script_dir, "data", "style_previews")


# =====================================================
# 从 Agnes Image API 响应中提取图片 URL
# Agnes Image API 标准返回结构：
#   { "data": [ { "url": "https://..." }, ... ] }
# 同时兼容顶层 url / image_url 的兜底返回格式
# =====================================================
def _extract_image_url(result: dict) -> str:
    if not isinstance(result, dict):
        return ""
    data_field = result.get("data")
    # 标准结构：data 是数组，取第一个元素的 url
    if isinstance(data_field, list) and data_field:
        first = data_field[0]
        if isinstance(first, dict):
            url = first.get("url") or first.get("image_url")
            if url:
                return url
    # 兜底1：data 是 dict
    if isinstance(data_field, dict):
        url = data_field.get("url") or data_field.get("image_url")
        if url:
            return url
    # 兜底2：顶层直接返回
    return result.get("url") or result.get("image_url") or ""


# =====================================================
# 为单个风格元素生成缩略图
# 已存在缩略图则跳过（幂等），否则调用 Agnes Image API 生成并下载保存
# 返回 True 表示新生成，False 表示跳过或失败
# =====================================================
async def generate_preview_for_element(element: StyleElement, db: AsyncSession) -> bool:
    """为单个风格元素生成缩略图，返回是否新生成"""
    # 检查是否已有缩略图（幂等）
    for ext in (".png", ".jpg", ".webp"):
        if os.path.exists(os.path.join(PREVIEW_DIR, f"{element.key}{ext}")):
            logger.info("跳过（已存在）: %s", element.key)
            return False

    # 构造生成 prompt：用元素 content + 示意图说明
    prompt = (
        f"{element.content}, a beautiful sample illustration showcasing this {element.layer} style, "
        f"high quality, representative artwork"
    )

    try:
        result = await agnes_client.create_image(
            prompt=prompt,
            model="agnes-image-2.1-flash",
            size="512x512",
            response_format="url",
        )
        image_url = _extract_image_url(result if isinstance(result, dict) else {})

        if not image_url:
            logger.warning("生成失败（无 URL）: %s resp=%s", element.key, str(result)[:200])
            return False

        # 下载图片
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(image_url)
            if resp.status_code != 200:
                logger.warning("下载失败: %s status=%d", element.key, resp.status_code)
                return False

            # 保存
            os.makedirs(PREVIEW_DIR, exist_ok=True)
            out_path = os.path.join(PREVIEW_DIR, f"{element.key}.png")
            with open(out_path, "wb") as f:
                f.write(resp.content)

        # 更新 DB 中的 preview_image 字段
        element.preview_image = f"/api/style-elements/preview/{element.key}"
        await db.commit()

        logger.info("生成成功: %s -> %s", element.key, out_path)
        return True

    except Exception as e:
        logger.error("生成异常: %s - %s", element.key, e)
        return False


# =====================================================
# 主流程：
#   1. 初始化 agnes_client 连接池
#   2. 查询所有内置风格元素
#   3. 串行生成缩略图（避免并发消耗过多 API 额度）
#   4. 释放连接池
# =====================================================
async def main():
    print("==== 开始生成风格元素缩略图 ====")
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    # 初始化 Agnes 客户端连接池
    await agnes_client.start()

    try:
        async with async_session() as session:
            # 查询所有内置元素
            result = await session.execute(
                select(StyleElement)
                .filter(StyleElement.is_builtin == True)
                .order_by(StyleElement.layer, StyleElement.sort_order)
            )
            elements = list(result.scalars().all())

            if not elements:
                print("未找到内置风格元素，请先执行 seed_style_elements.py")
                return

            print(f"共 {len(elements)} 个内置元素待处理")

            # 串行生成（避免并发消耗过多 API 额度）
            success = 0
            skipped = 0
            failed = 0
            for i, element in enumerate(elements, 1):
                print(f"[{i}/{len(elements)}] 处理: {element.key} ({element.name})")
                try:
                    generated = await generate_preview_for_element(element, session)
                    if generated:
                        success += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error("处理失败: %s - %s", element.key, e)
                    failed += 1
                    continue
                # 间隔避免 API 限流
                await asyncio.sleep(1)

            print(f"\n==== 完成 ====")
            print(f"成功生成: {success}")
            print(f"已跳过: {skipped}")
            print(f"失败: {failed}")
            print(f"缩略图目录: {PREVIEW_DIR}")
    finally:
        # 释放连接池
        await agnes_client.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已取消")
