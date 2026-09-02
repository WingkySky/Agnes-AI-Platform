# =====================================================
# 积分规则管理路由（仅管理员）
#
# GET    /api/admin/credit-rules           列出所有积分规则
# PUT    /api/admin/credit-rules/{key}     修改某条积分规则的 value / description
# POST   /api/admin/credit-rules/reset     恢复默认积分规则
# =====================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update as sa_update

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_admin_user
from app.models.credit_rule import CreditRule, DEFAULT_CREDIT_RULES
from app.models.user import User
from app.schemas.user import CreditRuleResponse, CreditRuleUpdateRequest
from app.services.credits_service import invalidate_credit_rules_cache
from app.services.project.project_service import rebuild_all_project_covers

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin", tags=["管理员-积分规则"])


# ---------- 辅助：从数据库读取所有规则为 dict ----------
async def load_credit_rules(db: AsyncSession) -> dict:
    """读取所有积分规则，返回 {rule_key: int_value} 字典（缺失的键用 DEFAULT_CREDIT_RULES 中的默认值补上）"""
    result = await db.execute(select(CreditRule))
    rows = result.scalars().all()
    from_db = {r.rule_key: r.value for r in rows}

    merged = {}
    for default in DEFAULT_CREDIT_RULES:
        key = default["rule_key"]
        merged[key] = from_db.get(key, default["value"])
    # 把数据库里超出默认范围的也一起返回（扩展规则）
    for r in rows:
        merged.setdefault(r.rule_key, r.value)
    return merged


# ---------- 列出所有积分规则 ----------
async def _build_credit_rule_items(db: AsyncSession) -> list[CreditRuleResponse]:
    """合并默认值构建完整规则列表（GET 与 reset 共用）"""
    # 1. 读取数据库中的规则
    result = await db.execute(select(CreditRule).order_by(CreditRule.id.asc()))
    rows = result.scalars().all()
    by_key = {r.rule_key: r for r in rows}

    # 2. 合并默认值 —— 保证前端能看到完整的一组规则
    items: list[CreditRuleResponse] = []
    now = datetime.utcnow()
    for default in DEFAULT_CREDIT_RULES:
        key = default["rule_key"]
        if key in by_key:
            r = by_key[key]
            items.append(CreditRuleResponse(
                id=r.id, rule_key=r.rule_key, name=r.name or default["name"],
                value=r.value, description=r.description or default["description"] or "",
                updated_at=r.updated_at,
            ))
        else:
            # 还没在数据库中，临时以默认值返回（下次 PUT 时会真正落库）
            items.append(CreditRuleResponse(
                id=0, rule_key=key, name=default["name"], value=default["value"],
                description=default["description"] or "", updated_at=now,
            ))

    # 追加数据库中额外存在的规则（超出默认范围）
    for r in rows:
        if r.rule_key not in [d["rule_key"] for d in DEFAULT_CREDIT_RULES]:
            items.append(CreditRuleResponse(
                id=r.id, rule_key=r.rule_key, name=r.name or r.rule_key,
                value=r.value, description=r.description or "", updated_at=r.updated_at,
            ))
    return items


@router.get("/credit-rules", summary="[管理员] 列出所有积分规则")
async def list_credit_rules(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    return ok(data=await _build_credit_rule_items(db))


# ---------- 修改某条积分规则 ----------
@router.put("/credit-rules/{rule_key:path}", summary="[管理员] 修改积分规则")
async def update_credit_rule(
    rule_key: str,
    req: CreditRuleUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    rule_key = (rule_key or "").strip()
    if not rule_key:
        raise HTTPException(status_code=400, detail="rule_key 不能为空")

    # 查找现有记录
    result = await db.execute(select(CreditRule).filter(CreditRule.rule_key == rule_key))
    row = result.scalar_one_or_none()

    now = datetime.utcnow()
    if row is None:
        # 从默认值中查找 name/description，作为初始内容
        default = next((d for d in DEFAULT_CREDIT_RULES if d["rule_key"] == rule_key), None)
        name = req.name or (default["name"] if default else rule_key)
        description = req.description if req.description is not None else (
            default["description"] if default else ""
        )
        row = CreditRule(
            rule_key=rule_key,
            name=name,
            value=req.value,
            description=description,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        if req.name is not None:
            row.name = req.name
        row.value = req.value
        if req.description is not None:
            row.description = req.description
        row.updated_at = now

    await db.commit()
    await db.refresh(row)

    # 清除积分规则缓存
    invalidate_credit_rules_cache()

    logger.info("[管理员操作] %s 修改积分规则 %s = %d", admin.username, rule_key, row.value)
    return ok(data=CreditRuleResponse(
        id=row.id, rule_key=row.rule_key, name=row.name,
        value=row.value, description=row.description or "", updated_at=row.updated_at,
    ))


# ---------- 恢复默认积分规则 ----------
@router.post("/credit-rules/reset", summary="[管理员] 恢复默认积分规则")
async def reset_credit_rules(
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    now = datetime.utcnow()
    for default in DEFAULT_CREDIT_RULES:
        key = default["rule_key"]
        result = await db.execute(select(CreditRule).filter(CreditRule.rule_key == key))
        row = result.scalar_one_or_none()
        if row is None:
            db.add(CreditRule(
                rule_key=key, name=default["name"], value=default["value"],
                description=default["description"] or "",
                created_at=now, updated_at=now,
            ))
        else:
            row.name = default["name"]
            row.value = default["value"]
            row.description = default["description"] or ""
            row.updated_at = now
    await db.commit()
    # 清除积分规则缓存
    invalidate_credit_rules_cache()

    logger.info("[管理员操作] %s 恢复默认积分规则", admin.username)
    return ok(data=await _build_credit_rule_items(db))


# =====================================================
# 项目封面批量回填（管理员专用）
# =====================================================

@router.post("/projects/rebuild-all-covers", summary="[管理员] 批量回填项目封面")
async def rebuild_all_covers_api(
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    """为所有缺少封面的项目自动回填封面（扫描所有帧图）"""
    result = await rebuild_all_project_covers(db)
    logger.info("[管理员操作] %s 执行批量封面回填: %s", admin.username, result)
    return ok(data=result)
