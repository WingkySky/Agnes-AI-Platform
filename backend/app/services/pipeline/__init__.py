# =====================================================
# 流水线服务模块
# 项目制创作已迁移到 app.services.project，本模块仅保留模板管理服务
# =====================================================

from app.services.pipeline.template_service import (
    get_template_by_id,
    get_template_by_key,
    list_templates,
    create_template,
    update_template,
    delete_template,
    validate_steps_config,
)

__all__ = [
    "get_template_by_id",
    "get_template_by_key",
    "list_templates",
    "create_template",
    "update_template",
    "delete_template",
    "validate_steps_config",
]
