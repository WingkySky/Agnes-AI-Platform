# =====================================================
# 菜单配置服务
#
# 设计理念：
#   - 菜单元数据（key、名称、图标、路径、权限）在前端内置
#   - 后端只存储用户配置：哪些显示、位置（顶部/侧边栏/隐藏）、分组、排序
#   - 存储格式：JSON 数组，存放在 system_configs 表中，key = "menu_configs"
# =====================================================

import json
import logging
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.system_config_service import get_config_value, set_config_value

logger = logging.getLogger("agnes_platform")

MENU_CONFIG_KEY = "menu_configs"


async def get_menu_configs(db: AsyncSession) -> List[Dict[str, Any]]:
    """
    获取菜单配置列表
    - 如果数据库中没有配置，返回空数组（前端会使用内置默认配置）
    """
    config_json = await get_config_value(db, MENU_CONFIG_KEY, "")
    if not config_json:
        return []
    try:
        return json.loads(config_json)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("[菜单配置] 解析菜单配置失败，返回默认配置: %s", e)
        return []


async def save_menu_configs(db: AsyncSession, configs: List[Dict[str, Any]]) -> None:
    """
    保存菜单配置（全量覆盖）
    """
    config_json = json.dumps(configs, ensure_ascii=False)
    await set_config_value(db, MENU_CONFIG_KEY, config_json)
    logger.info("[菜单配置] 菜单配置已保存，共 %d 项", len(configs))


async def reset_menu_configs(db: AsyncSession) -> None:
    """
    重置菜单配置为默认（删除数据库配置，前端会使用内置默认）
    """
    await set_config_value(db, MENU_CONFIG_KEY, "")
    logger.info("[菜单配置] 菜单配置已重置为默认")
