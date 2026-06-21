"""直接测试 history 路由的用户隔离逻辑（不通过 HTTP）"""
import sys
sys.path.insert(0, '/Users/skywing/agnes-platform/backend')

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.generation import Generation  # 假设这是你的模型
from sqlalchemy import select, func

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///agnes_platform.db')
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        print('=== 测试不同用户查询 ===')

        # 未登录: user_id IS NULL
        stmt = select(Generation)
        stmt = stmt.filter(Generation.user_id.is_(None))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await db.execute(count_stmt)
        print(f'未登录用户 (user_id IS NULL): {result.scalar_one()} 条记录')

        # 用户 1
        stmt = select(Generation).filter(Generation.user_id == 1)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await db.execute(count_stmt)
        print(f'用户 1 (xintiandi121): {result.scalar_one()} 条记录')

        # 用户 3
        stmt = select(Generation).filter(Generation.user_id == 3)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await db.execute(count_stmt)
        print(f'用户 3 (admin): {result.scalar_one()} 条记录')

        print()
        print('=== 实际查询前 5 条（按用户3）===')
        stmt = select(Generation).filter(Generation.user_id == 3).order_by(Generation.created_at.desc()).limit(5)
        result = await db.execute(stmt)
        items = result.scalars().all()
        for item in items:
            print(f'  id={item.id}, user_id={item.user_id}, type={item.type}, prompt={item.prompt[:40] if item.prompt else ""}')

asyncio.run(test())
