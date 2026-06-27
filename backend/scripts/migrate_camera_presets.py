# =====================================================
# CameraPreset → PresetIndex 迁移脚本
# 扫描现有 camera_presets 表，补齐 preset_index 条目。
# 幂等：已存在 preset_index 记录的不重复插入。
# =====================================================

import os
import sys

# 确保 backend 目录在 sys.path 中，以便导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.camera_preset import CameraPreset
from app.models.prompt_preset import PresetIndex
from sqlalchemy import and_


def migrate():
    db = SessionLocal()
    try:
        presets = db.query(CameraPreset).all()
        total = len(presets)
        created = 0
        skipped = 0

        print(f"找到 {total} 条 CameraPreset 记录")

        for cp in presets:
            # 检查是否已存在 preset_index 记录
            existing = (
                db.query(PresetIndex)
                .filter(
                    and_(
                        PresetIndex.preset_type == "camera",
                        PresetIndex.preset_id == cp.id,
                    )
                )
                .first()
            )

            if existing:
                skipped += 1
                continue

            # 创建 preset_index 条目
            entry = PresetIndex(
                preset_type="camera",
                preset_id=cp.id,
                category=cp.category or "通用",
                tags=cp.tags or [],
                user_id=cp.user_id,
                is_public=cp.is_public,
                is_approved=cp.is_approved,
                usage_count=cp.usage_count,
                name=cp.name,
                description=cp.description,
                created_at=cp.created_at,
            )
            db.add(entry)
            created += 1

        db.commit()
        print(f"迁移完成：新建 {created} 条，跳过 {skipped} 条（已存在），共 {total} 条")
    except Exception as e:
        db.rollback()
        print(f"迁移失败：{e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
