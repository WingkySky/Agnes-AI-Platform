# =====================================================
# 项目制创作服务层
#
# 模块组成:
#   - sse_manager:       项目级 SSE 推送（向导进度/生成进度/实体变更等）
#   - project_service:   项目 CRUD + 状态机
#   - wizard:            创建向导（4 步 LLM 链：剧本 → 实体抽取 → 分镜拆分 → 帧提示词）
#   - script_service:    剧本增删改查 + 重新生成
#   - character_service: 角色增删改查 + 资产版本管理
#   - scene_service:     场景增删改查 + 资产版本管理
#   - prop_service:      道具增删改查 + 资产版本管理
#   - shot_service:      分镜增删改查 + 绑定实体 + 重排序
#   - frame_image_service: 帧图多版本管理 + 生成
#   - video_service:     视频多版本管理 + 生成
#   - asset_bridge:      公共资产库引用 / 转存（C2 模式）
#   - canvas_bridge:     画布数据同步（J4 双视图）
#   - merge_service:     最终成片合成
# =====================================================

from app.services.project.sse_manager import project_sse_manager, ProjectSSEManager

__all__ = ["project_sse_manager", "ProjectSSEManager"]
