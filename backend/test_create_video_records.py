#!/usr/bin/env python3
"""
创建测试视频记录脚本
直接在数据库中为用户创建测试视频记录
"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '.')

from app.core.database import async_session_local
from app.models.generation import Generation


async def create_test_records(user_id: int = 1):
    """
    为指定用户创建测试视频记录
    """
    # 使用一个公开的视频 URL 用于测试（small sample mp4）
    test_video_urls = [
        "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
        "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    ]

    async with async_session_local() as db:
        # 清理之前的测试数据
        for i, video_url in enumerate(test_video_urls):
            record = Generation(
                user_id=user_id,
                type="#!/usr/bin/env python3
"""
创建测试视频记录脚本
直接在数据库中为用户创建测试视频记??"""
创建测试视?t?_直接在数据库中为用? """
import asyncio
import sys
from datetime import da      import sys
frl=from date,

sys.path.insert(0, '.ess
from app.core.database importdatfrom app.models.generation import Generation


a(r

async def create_test_records(user_id: in 查    