import asyncio
from datetime import datetime
from app.core.database import async_session_local
from app.models.generation import Generation

async def main():
    user_id = 5
    test_urls = [
        'https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4',
        'https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4',
    ]
    async with async_session_local() as db:
        for i, url in enumerate(test_urls):
            record = Generation(
                user_id=user_id, type='video', model='agnes-video-v1',
                prompt='Test video ' + str(i+1) + ': Beautiful nature scene',
                task_id='test-task-' + str(i+1), backend_task_id='test-backend-' + str(i+1),
                result_url=url, status='success', created_at=datetime.utcnow(),
            )
            db.add(record)
        await db.commit()
        print('Done: created 2 test video records for user', user_id)

asyncio.run(main())
