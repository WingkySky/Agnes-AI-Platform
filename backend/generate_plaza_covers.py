# =====================================================
# 官方预设封面批量生成脚本
# 用 Agnes Image API 为缺封面的官方预设串行生成封面
# 使用方式（在 backend 目录下）：
#   python3 generate_plaza_covers.py
#
# 注意：
# - 会消耗 Agnes Image API 额度（每个预设 1 张 512x512）
# - 默认只为 cover_image 为空的官方卡生成（幂等）
# - 单张生成也可在管理端预设详情弹层点「生成封面」
# =====================================================

import asyncio
import logging
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from app.core.database import async_session
from app.services.preset_cover_service import generate_missing_official_covers

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_plaza_covers")


async def main():
    print("==== 开始生成官方预设封面（仅缺封面的） ====")
    async with async_session() as session:
        ok = await generate_missing_official_covers(session)
    print(f"==== 完成：成功 {ok} 张 ====")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已取消")
