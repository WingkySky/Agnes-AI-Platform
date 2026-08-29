# =====================================================
# 分镜脚本生成 Schema（无限画布 script 节点）
# - 无状态：不建表、不存储，结果由前端写回画布节点
# =====================================================

from typing import List, Optional

from pydantic import BaseModel, Field


class StoryboardCharacter(BaseModel):
    """角色设定（来自画布上游文本/图片节点）"""
    name: str = Field(default="", description="角色名")
    description: str = Field(default="", description="角色外貌/服饰/性格描述")
    ref_image_url: Optional[str] = Field(None, description="角色参考图 URL")


class StoryboardRequest(BaseModel):
    """分镜脚本生成请求"""
    story: str = Field(..., min_length=1, description="剧情概述")
    characters: List[StoryboardCharacter] = Field(default_factory=list, description="已有角色设定列表（画布上游节点 + 资产卡回传）")
    scenes: List[StoryboardCharacter] = Field(default_factory=list, description="已有场景设定列表（反向通道，分镜沿用已有设定）")
    shot_count_min: int = Field(6, ge=1, le=30, description="期望镜头数下限")
    shot_count_max: int = Field(12, ge=1, le=30, description="期望镜头数上限（≤30）")
    style: Optional[str] = Field(None, description="画面风格（可空）")
    model: Optional[str] = Field(None, description="分镜聊天模型（chat 类型，可空；未传或不在聊天模型注册表中时回退第一个聊天模型）")


class StoryboardShot(BaseModel):
    """单个分镜"""
    no: int = Field(default=0, description="镜头序号（从 1 开始，缺失时后端按顺序补齐）")
    shot_size: str = Field(default="", description="景别（远景/全景/中景/近景/特写）")
    camera: str = Field(default="", description="机位/运镜")
    characters: List[str] = Field(default_factory=list, description="出场角色名（与角色清单按名关联）")
    location: str = Field(default="", description="场景名（与场景清单按名关联）")
    description: str = Field(default="", description="画面描述（生图提示词主体）")
    dialogue: str = Field(default="", description="台词（可空）")


class StoryboardAsset(BaseModel):
    """从剧情提取的资产卡（角色/场景）"""
    name: str = Field(default="", description="名称")
    description: str = Field(default="", description="描述（角色写外貌/服饰/气质，场景写环境/时间/氛围）")


class StoryboardAssetGroup(BaseModel):
    """全剧资产清单"""
    characters: List[StoryboardAsset] = Field(default_factory=list, description="角色清单")
    scenes: List[StoryboardAsset] = Field(default_factory=list, description="场景清单")


class StoryboardResult(BaseModel):
    """分镜 + 资产一体化结果"""
    shots: List[StoryboardShot] = Field(default_factory=list, description="分镜列表")
    assets: StoryboardAssetGroup = Field(default_factory=StoryboardAssetGroup, description="全剧资产清单")
