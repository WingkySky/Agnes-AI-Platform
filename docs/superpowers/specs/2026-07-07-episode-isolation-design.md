# 集数隔离（Episode Isolation）设计文档

## 一、背景与问题

### 1.1 问题描述

当前项目支持"大项目 → 多集剧本 → 分镜/人物/物品/场景"的创作链路，但集数之间**完全没有数据隔离**，导致：

1. **第二集分镜追加到第一集后面**：在第二集生成分镜时，新分镜的 `sequence_no` 按项目全局递增，直接挂在第一集分镜列表末尾，视觉上无法区分。
2. **人物/物品/场景默认只能拿第一集剧本**：三类资源的"从剧本提取"功能内部硬编码取 `scripts[0]`，无论用户在 UI 选中哪一集，提取的永远是第一集的剧本内容。
3. **列表混排**：分镜/角色/场景/道具的列表查询只按 `project_id` 过滤，所有集的数据混在一起，无法按集查看。

### 1.2 根因（三层协同缺失）

| 层 | 问题 |
|---|---|
| 数据模型 | 只有 `ProjectScript` 自己有 `episode_no`；`ProjectCharacter/Scene/Prop` 只有 `project_id` 无集归属；`ProjectShot.script_id` 是 nullable 软关联，列表查询忽略它；`sequence_no` 唯一约束是 `(project_id, sequence_no)` 项目全局 |
| Service | `split_shots_from_script` / `extract_xxx_from_script` 不接收 `script_id` 参数，内部 `.order_by(episode_no).first()` 永远取第一集；序号计算按 project 全局 max |
| 前端 | API 层 `extractFromScript(projectId, _scriptId)` / `splitShotsFromScript(projectId, _scriptId)` 参数名带下划线表示故意丢弃；三个 Tab 的"从剧本提取"硬编码 `projectStore.scripts[0]`；Store 是全局扁平数组无集概念 |

## 二、目标与非目标

### 2.1 目标

1. 角色/场景/道具/分镜四类资源**强属于某一集**（`script_id` NOT NULL + 级联删除）
2. 分镜序号按集重置（每集从 1 开始），不再追加到上一集末尾
3. "从剧本提取"/"分镜拆分"真正使用当前选中集的剧本内容
4. 顶部统一集数切换器，切换后自动重新拉取对应集的四类资源
5. 提供"全部集"全局视图，按集分组展示
6. 提供跨集复制功能（角色/场景/道具），缓解强隔离下的复用痛点

### 2.2 非目标

- 不做"项目级全局资源 + 出现集关联表"的多对多方案（已选定强隔离）
- 不做现有数据迁移（按 AGENTS.md 默认规则直接重建表）
- 不做分镜的跨集复制（分镜强属于某集，跨集复制语义不明）
- 不改 ScriptTab 自身的选中状态（剧本 Tab 独立管理剧本，不与全局集数联动）

## 三、核心决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 隔离粒度 | 强隔离：每集独立 | 模型简单、查询直接、UI 清晰；跨集复用通过"复制到其他集"功能弥补 |
| 现有数据 | 不迁移，直接重建表 | 符合 AGENTS.md "项目未上线不写迁移"默认规则 |
| 本期范围 | 隔离 + 跨集复制 + 全局视图 | 完整解决隔离与复用痛点 |
| 实现方案 | 方案 A：全局顶部切换器 + 后端按 script_id 过滤 + 跨集复制深拷贝 | 符合项目现有 FastAPI 薄路由 + Service 重逻辑架构；切换器统一符合用户"统一入口"偏好；后端按 script_id 过滤是标准 REST 查询参数模式 |

## 四、数据模型层设计

文件：`backend/app/models/project.py`

### 4.1 四张资源表新增 `script_id` 外键

`ProjectCharacter`、`ProjectScene`、`ProjectProp`、`ProjectShot` 统一新增：

```python
script_id = Column(
    Integer,
    ForeignKey("project_scripts.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
    comment="所属集剧本ID"
)
```

- **NOT NULL**：强制每个资源必须属于某一集，把"强隔离"业务规则下沉到数据库层
- **ondelete=CASCADE**：删除某集剧本时，该集下所有资源自动级联删除
- **index=True**：按集查询是高频路径
- 保留 `project_id` 外键不动（项目级查询仍需要，且便于直查避免 join）

### 4.2 分镜序号改为按集重置

`ProjectShot` 现有唯一约束 `uq_project_shots_seq` on `(project_id, sequence_no)` 改为：

```python
UniqueConstraint("project_id", "script_id", "sequence_no", name="uq_project_shots_seq")
```

`sort_order` 的 max 计算在 Service 层改为按 `script_id` 范围取，使每集分镜序号从 1 开始。

### 4.3 ProjectScript 增加反向关系

```python
characters = relationship("ProjectCharacter", back_populates="script", cascade="all, delete-orphan")
scenes = relationship("ProjectScene", back_populates="script", cascade="all, delete-orphan")
props = relationship("ProjectProp", back_populates="script", cascade="all, delete-orphan")
shots = relationship("ProjectShot", back_populates="script", cascade="all, delete-orphan")
```

四张资源表对应增加 `script = relationship("ProjectScript", back_populates="...")`。

### 4.4 NOT NULL 的设计依据

原 `ProjectShot.script_id` 是 nullable 软关联，失败原因有三：

1. **历史演进遗留**：分镜表最初设计时无集概念，后加 `script_id` 字段为兼容存量数据设为 nullable
2. **向导流程绕过**：`wizard.py` 创建 ProjectShot 时不传 script_id，nullable 让该流程能跑通
3. **应用层不使用**：`list_shots` 查询忽略 script_id，`create_shot` 不写 script_id，软关联实际等于没关联

改 NOT NULL 的理由：

1. **语义必须强制**：可选字段不会被遵守，NOT NULL 把业务规则下沉到数据库层
2. **强隔离的物理基础**：强隔离要求每个资源有且只有一个集归属
3. **列表查询确定性**：NULL 行归属无法判定，过滤时要么丢失要么污染
4. **级联删除确定性**：NULL 行永远不会被级联删除，会变孤儿数据
5. **让错误提前发生**：把"忘记写 script_id"从"运行时静默产生脏数据"变成"创建时报错立即暴露"

### 4.5 建表/重建策略

按 AGENTS.md "不写迁移"，直接 drop 相关表重建。由于 `ProjectShot` 被 `ProjectShotCharacter`/`ProjectShotProp`/`ProjectShotFrameImage`/`ProjectShotVideo` 外键引用，这些子表一并重建。开发期可用 `drop_all` + `create_all` 或单个 alembic revision 完成。

## 五、Schema / Service / 路由层设计

### 5.1 Schema 层（`backend/app/schemas/project.py`）

四类资源的 Create/Response 模型统一新增字段：

```python
# CharacterCreate / SceneCreate / PropCreate / ShotCreate
script_id: int = Field(..., description="所属集剧本ID")

# CharacterResponse / SceneResponse / PropResponse / ShotResponse
script_id: int
episode_no: int | None = None  # 仅 Response 带，前端直接展示"第N集"无需再查 script
```

- Create 用 `int`（必填，无默认值）与数据库 NOT NULL 对齐，Pydantic 层拦住缺失 script_id 的请求
- Response 带 `episode_no` 避免前端二次查询
- `ScriptResponse` 增加 `shot_count` / `character_count` / `scene_count` / `prop_count` 可选计数字段，供集数切换器显示"第2集（12 个分镜）"

### 5.2 Service 层改造

#### 5.2.1 extract/split 函数接收 script_id（核心修复）

四个函数签名统一改为接收 `script_id`，不再内部 `.first()` 取第一集：

| 函数 | 文件 | 新签名 |
|---|---|---|
| `split_shots_from_script` | `backend/app/services/project/shot_service.py` | `(db, project_id, script_id)` |
| `extract_characters_from_script` | `backend/app/services/project/character_service.py` | `(db, project_id, script_id)` |
| `extract_scenes_from_script` | `backend/app/services/project/scene_service.py` | `(db, project_id, script_id)` |
| `extract_props_from_script` | `backend/app/services/project/prop_service.py` | `(db, project_id, script_id)` |

内部取剧本改为按 script_id 精确查询，并加归属校验防越权：

```python
script = (await db.execute(
    select(ProjectScript).where(
        ProjectScript.id == script_id,
        ProjectScript.project_id == project_id,
    )
)).scalars().first()
if not script:
    raise HTTPException(404, "剧本不存在或不属于该项目")
```

#### 5.2.2 split 的序号计算改为按集

```python
max_seq = (await db.execute(
    select(func.coalesce(func.max(ProjectShot.sequence_no), 0))
    .where(ProjectShot.script_id == script_id)
)).scalar() or 0
# sort_order 同理
```

第二集分镜从 1 开始，不再追加到第一集末尾。

#### 5.2.3 list 函数增加 script_id 可选过滤

四个 list 函数统一改为：

```python
async def list_shots(db: AsyncSession, project_id: int, script_id: int | None = None):
    stmt = select(ProjectShot).where(ProjectShot.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectShot.script_id == script_id)
    stmt = stmt.order_by(ProjectShot.sort_order)
    return (await db.execute(stmt)).scalars().all()
```

- `script_id=None`（不传）= 全部集（全局视图）
- `script_id=N` = 仅某集

为支持 Response 带 `episode_no`，list 查询需要 join `ProjectScript` 取 `episode_no` 填充返回。或在 Service 层批量查一次 `scripts` 字典后映射，避免 N+1。

#### 5.2.4 create 路径强制写 script_id

- `create_shot` 接收 `script_id` 入参并写入
- `create_character/scene/prop` 同理
- `wizard.py` 的 `_step_storyboard_split` 创建分镜时传入 `script_id=script.id`（script 对象在向导步骤 1 已创建）

#### 5.2.5 跨集复制函数（三类资源）

```python
async def copy_character_to_script(
    db: AsyncSession, project_id: int, character_id: int, target_script_id: int
) -> ProjectCharacter:
    # 校验源资源属于 project
    src = await db.get(ProjectCharacter, character_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源资源不存在")
    # 校验目标 script 属于 project
    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")
    # 名称冲突处理
    existing = (await db.execute(
        select(ProjectCharacter).where(
            ProjectCharacter.script_id == target_script_id,
            ProjectCharacter.name == src.name,
        )
    )).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name
    # 深拷贝：复制所有业务字段（除 id/created_at/updated_at/script_id 外），
    # 不复制关联分镜（ProjectShotCharacter 等）——分镜强属于原集
    new_entity = ProjectCharacter(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        # 角色其他业务字段（如 appearance/personality/role 等）逐一从 src 复制
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    return new_entity
```

`copy_scene_to_script` / `copy_prop_to_script` 同构。三类函数可通过工厂或各自实现（视现有 Service 组织方式而定）。

**不复制的内容**：
- 关联分镜（`ProjectShotCharacter` 等）——分镜强属于原集，跨集复制分镜不在本期范围
- `id` / `created_at` / `updated_at` ——由数据库生成

### 5.3 路由层改造（`backend/app/routes/projects.py`）

#### 5.3.1 list 接口支持 `?script_id=N` 查询参数

```python
@router.get("/{project_id}/shots")
async def list_shots_api(project_id: int, script_id: int | None = None, db = Depends(...)):
    return await shot_service.list_shots(db, project_id, script_id)
```

涉及四个 list 接口（shots + 工厂模式的 characters/scenes/props）。

#### 5.3.2 extract/split 接口接收 script_id 请求体

```python
class ExtractRequest(BaseModel):
    script_id: int

@router.post("/{project_id}/characters/extract-from-script")
async def extract_characters_api(project_id: int, req: ExtractRequest, db = Depends(...)):
    return await character_service.extract_characters_from_script(db, project_id, req.script_id)
```

涉及四个 extract/split 接口。工厂模式 `_build_entity_routes` 的 extract handler 当前调用 `extract_fn(db, project_id)`，需改为 `extract_fn(db, project_id, req.script_id)`，工厂入参签名相应调整。

#### 5.3.3 跨集复制接口

```python
class CopyToRequest(BaseModel):
    target_script_id: int

@router.post("/{project_id}/characters/{entity_id}/copy-to")
async def copy_character_to_api(
    project_id: int, entity_id: int, req: CopyToRequest, db = Depends(...)
):
    new_entity = await character_service.copy_character_to_script(
        db, project_id, entity_id, req.target_script_id
    )
    return new_entity
```

scenes/props 同构，通过工厂模式统一注册。shots 不提供此接口。

#### 5.3.4 create 接口

由于 Create Schema 已把 `script_id` 设为必填，路由层 `POST /{project_id}/shots` 等接口会自动要求请求体带 script_id，无需额外改动。

## 六、前端 API / Store 层设计

### 6.1 API 层（`frontend/src/api/projects.ts`）

#### 6.1.1 list 接口支持 script_id 可选参数

```typescript
// buildEntityApi 内部
list: (projectId: number, scriptId?: number) =>
  client.get(`/api/projects/${projectId}/${prefix}`, {
    params: scriptId !== undefined ? { script_id: scriptId } : undefined,
  }),

export function listShots(projectId: number, scriptId?: number): Promise<ShotResponse[]> {
  return client.get(`/api/projects/${projectId}/shots`, {
    params: scriptId !== undefined ? { script_id: scriptId } : undefined,
  })
}
```

#### 6.1.2 extract / split 接口真正发送 scriptId（修复"下划线丢弃"）

```typescript
extractFromScript: (projectId: number, scriptId: number) =>
  client.post(`/api/projects/${projectId}/${prefix}/extract-from-script`, { script_id: scriptId }),

export function splitShotsFromScript(projectId: number, scriptId: number): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/split`, { script_id: scriptId })
}
```

去掉参数名前缀下划线，TypeScript 类型签名直接体现必填语义。

#### 6.1.3 新增跨集复制接口

```typescript
copyTo: (projectId: number, entityId: number, targetScriptId: number) =>
  client.post(`/api/projects/${projectId}/${prefix}/${entityId}/copy-to`, {
    target_script_id: targetScriptId,
  }),
```

characters/scenes/props 共用工厂模式，一处加即可。

### 6.2 Store 层（`frontend/src/stores/project.ts`）

#### 6.2.1 state 增加 currentScriptId

```typescript
state: () => ({
  // ...现有字段
  currentScriptId: null as number | null,  // null=全部集视图，number=某集
})
```

语义约定：
- `currentScriptId === null` → 全部集视图，list 接口不传 script_id，前端按 `episode_no` 分组展示
- `currentScriptId === N` → 仅第 N 集，list 接口传 script_id=N

#### 6.2.2 setCurrentScript action

```typescript
async setCurrentScript(scriptId: number | null) {
  this.currentScriptId = scriptId
  await Promise.all([
    this.fetchShots(),
    this.fetchEntities('characters'),
    this.fetchEntities('scenes'),
    this.fetchEntities('props'),
  ])
}
```

切换集时自动重新拉取四类资源，保证 UI 与 currentScriptId 同步。

#### 6.2.3 fetchShots / fetchEntities 使用 currentScriptId

```typescript
async fetchShots() {
  if (!this.currentProjectId) return
  this.shots = await apiListShots(this.currentProjectId, this.currentScriptId ?? undefined)
}

async fetchEntities(type: 'characters' | 'scenes' | 'props') {
  if (!this.currentProjectId) return
  const api = this._entityApiMap[type]
  this[type] = await api.list(this.currentProjectId, this.currentScriptId ?? undefined)
}
```

`currentScriptId ?? undefined` 把 null 转成 undefined，让 API 层不传 query 参数（拉全部）。

#### 6.2.4 splitShotsFromScript / extractEntitiesFromScript 透传 scriptId

```typescript
async splitShotsFromScript(scriptId: number) {
  await apiSplitShotsFromScript(this.currentProjectId!, scriptId)
  await this.fetchShots()
}

async extractEntitiesFromScript(type, scriptId: number) {
  const api = this._entityApiMap[type]
  await api.extractFromScript(this.currentProjectId!, scriptId)
  await this.fetchEntities(type)
}
```

#### 6.2.5 按集分组的 getter（全局视图用）

```typescript
getters: {
  shotsByEpisode(state): Record<number, ProjectShot[]> {
    const grouped: Record<number, ProjectShot[]> = {}
    for (const shot of state.shots) {
      const ep = shot.episode_no ?? 0
      ;(grouped[ep] ??= []).push(shot)
    }
    return grouped
  },
  // charactersByEpisode / scenesByEpisode / propsByEpisode 同理
}
```

前提：后端 Response 已带 `episode_no` 字段。

#### 6.2.6 createXxx 透传 script_id

手动新建资源时默认使用 `currentScriptId`：

```typescript
async createShot(payload: ShotCreate) {
  if (!this.currentScriptId) throw new Error('请先选择集数')
  const shot = await apiCreateShot(this.currentProjectId!, {
    ...payload,
    script_id: this.currentScriptId,
  })
  this.shots.push(shot)
}
```

`currentScriptId === null`（全部集视图）时禁止手动新建，UI 层禁用"新建"按钮并提示。

#### 6.2.7 copyEntityTo action

```typescript
async copyEntityTo(
  type: 'characters' | 'scenes' | 'props',
  entityId: number,
  targetScriptId: number
) {
  const api = this._entityApiMap[type]
  await api.copyTo(this.currentProjectId!, entityId, targetScriptId)
  // 不自动切换到目标集，留在当前集
}
```

## 七、前端 UI 层设计

### 7.1 顶部集数切换器（`frontend/src/components/project/ProjectManagerView.vue`）

#### 7.1.1 位置与形态

在 Tab 栏之上或右侧，新增"当前集"选择器，采用 Element Plus `el-select`：

```
[ 第1集 ▼ ]  [剧本] [角色] [场景] [道具] [分镜] [时间线]
```

选项：
- 全部集（`currentScriptId = null`）
- 第N集：标题（X 个分镜 / Y 个角色）

#### 7.1.2 关键实现

```vue
<template>
  <div class="episode-switcher">
    <span class="label">{{ t('project.currentEpisode') }}</span>
    <el-select
      v-model="currentScriptId"
      placeholder="请选择集"
      @change="onScriptChange"
      style="width: 240px"
    >
      <el-option :label="t('project.allEpisodes')" :value="null" />
      <el-option
        v-for="script in projectStore.scripts"
        :key="script.id"
        :label="`第${script.episode_no}集：${script.title}`"
        :value="script.id"
      />
    </el-select>
  </div>
</template>

<script setup lang="ts">
const projectStore = useProjectStore()
const currentScriptId = ref<number | null>(projectStore.currentScriptId)

async function onScriptChange(val: number | null) {
  await projectStore.setCurrentScript(val)
}

onMounted(async () => {
  // 首次进入默认选中第一集，避免一进来就拉全量
  if (projectStore.currentScriptId === null && projectStore.scripts.length > 0) {
    await projectStore.setCurrentScript(projectStore.scripts[0].id)
  }
})
</script>
```

#### 7.1.3 ScriptTab 不受影响

`ScriptTab.vue` 维护自己的 `selectedScriptId` 用于剧本编辑/重生成，不与全局 `currentScriptId` 联动——剧本 Tab 的操作是"管理剧本本身"，不是"切换当前查看的集"。

### 7.2 ShotsTab 改造（`frontend/src/components/project/ShotsTab.vue`）

#### 7.2.1 列表数据来源

```typescript
const shots = computed(() => {
  if (projectStore.currentScriptId === null) {
    return projectStore.shotsByEpisode  // 全部集视图：按集分组
  }
  return projectStore.shots  // 单集视图：直接展示
})
```

#### 7.2.2 全部集视图渲染

按 `episode_no` 分区展示，每集一个折叠面板：

```vue
<template v-if="projectStore.currentScriptId === null">
  <el-collapse v-for="(shots, ep) in projectStore.shotsByEpisode" :key="ep">
    <el-collapse-item :title="`第${ep}集（${shots.length} 个分镜）`">
      <ShotCard v-for="shot in shots" :key="shot.id" :shot="shot" />
    </el-collapse-item>
  </el-collapse>
</template>

<template v-else>
  <ShotCard v-for="shot in shots" :key="shot.id" :shot="shot" />
</template>
```

#### 7.2.3 "新建分镜"按钮禁用逻辑

```typescript
const canCreate = computed(() => projectStore.currentScriptId !== null)
```

```vue
<el-button :disabled="!canCreate" @click="onCreateShot">
  {{ t('project.createShot') }}
</el-button>
<el-tooltip v-if="!canCreate" :content="t('project.selectEpisodeFirst')" placement="top">
  <el-icon><InfoFilled /></el-icon>
</el-tooltip>
```

#### 7.2.4 "从剧本拆分"快捷入口

ShotsTab 也提供"从剧本拆分"入口，用 `currentScriptId` 调用：

```typescript
async function onSplitFromScript() {
  if (!projectStore.currentScriptId) return
  await projectStore.splitShotsFromScript(projectStore.currentScriptId)
}
```

### 7.3 CharactersTab / ScenesTab / PropsTab 改造

三个 Tab 结构同构，统一改造模式。

#### 7.3.1 列表数据来源

```typescript
const characters = computed(() => {
  if (projectStore.currentScriptId === null) {
    return projectStore.charactersByEpisode
  }
  return projectStore.characters
})
```

全部集视图按集分区展示（同 7.2.2）。

#### 7.3.2 "从剧本提取"按钮修复（核心）

移除硬编码 `projectStore.scripts[0]`，改用 `currentScriptId`：

```typescript
async function onExtractFromScript() {
  if (!projectStore.currentScriptId) {
    ElMessage.warning(t('project.selectEpisodeFirst'))
    return
  }
  await projectStore.extractEntitiesFromScript('characters', projectStore.currentScriptId)
}
```

第二集的"从剧本提取"会真正用第二集的剧本内容。

#### 7.3.3 "新建"按钮禁用逻辑

与 ShotsTab 一致，全部集视图下禁用并提示。

#### 7.3.4 跨集复制按钮

每个角色/场景/道具卡片上增加"复制到其他集"按钮（el-dropdown）：

```vue
<el-dropdown @command="onCopyTo">
  <el-button size="small" text>
    <el-icon><CopyDocument /></el-icon>
    {{ t('project.copyToEpisode') }}
  </el-button>
  <template #dropdown>
    <el-dropdown-menu>
      <el-dropdown-item
        v-for="script in otherScripts"
        :key="script.id"
        :command="script.id"
      >
        第{{ script.episode_no }}集：{{ script.title }}
      </el-dropdown-item>
    </el-dropdown-menu>
  </template>
</el-dropdown>
```

```typescript
const otherScripts = computed(() =>
  projectStore.scripts.filter(s => s.id !== projectStore.currentScriptId)
)

async function onCopyTo(targetScriptId: number) {
  if (!projectStore.currentScriptId) return
  await projectStore.copyEntityTo('characters', currentEntity.id, targetScriptId)
  ElMessage.success(t('project.copiedToEpisode'))
}
```

复制后不自动切换到目标集，留在当前集。

### 7.4 ProjectDetailView 无需改动

`ProjectDetailView.vue` 只负责加载项目、订阅 SSE、切换 manager/canvas 视图，不涉及集数切换。

### 7.5 国际化与样式约定

- **i18n**：所有新增文案走 `t('project.xxx')`，不硬编中文。涉及 key：`project.currentEpisode`（当前集）、`project.allEpisodes`（全部集）、`project.selectEpisodeFirst`（请先选择集数）、`project.copyToEpisode`（复制到其他集）、`project.copiedToEpisode`（已复制到目标集）等
- **样式**：集数切换器样式放在 `ProjectManagerView.vue` 的 scoped CSS，不污染全局。全部集视图的折叠面板复用 Element Plus `el-collapse` 默认样式，仅做少量间距覆盖
- **图标**：复制按钮用 `@element-plus/icons-vue` 的 `CopyDocument`，提示用 `InfoFilled`

## 八、错误处理

### 8.1 后端错误返回

| 场景 | HTTP 状态 | 错误信息 |
|---|---|---|
| script_id 不存在或不属于该项目 | 404 | "剧本不存在或不属于该项目" |
| 调用 create 时未传 script_id | 422 | Pydantic 自动校验失败（字段必填） |
| 调用 copy-to 时目标集不存在 | 404 | "目标集剧本不存在" |
| 调用 copy-to 时源资源不存在 | 404 | "源资源不存在" |
| extract/split 时剧本内容为空 | 400 | "剧本内容为空，无法提取" |
| 剧本内容过长导致 LLM 提取失败 | 500 | 走现有 LLM 调用错误处理 |

所有错误走现有 HTTPException 统一响应结构（status/message/data）。

### 8.2 前端错误反馈

- API 调用失败时 `ElMessage.error` 显示后端返回的 message
- `currentScriptId === null` 时调用 create/extract/split，前端先拦截并 `ElMessage.warning('请先选择集数')`，不发请求
- 跨集复制成功后 `ElMessage.success('已复制到目标集')`

### 8.3 边界情况

1. **项目只有一集剧本**：集数切换器仍显示，但"全部集"和"第1集"结果相同。不特殊处理，保持一致性。
2. **项目无剧本**：集数切换器显示"请先创建剧本"，所有资源 Tab 显示空状态并提示"请先在剧本 Tab 创建一集剧本"。
3. **删除某集剧本**：级联删除该集下所有资源。前端在删除成功后刷新 `scripts` 列表，如果 `currentScriptId` 指向被删除的集，自动切到第一集或"全部集"。
4. **全部集视图下的分镜排序**：按 `episode_no` 升序，集内按 `sort_order` 升序。
5. **跨集复制名称冲突**：自动加"（副本）"后缀，不阻断操作。

## 九、测试策略

按 AGENTS.md "代码测试从开始就要求覆盖率"。

### 9.1 后端测试（pytest + pytest-asyncio）

新增 `backend/tests/test_episode_isolation.py`：

| 测试用例 | 验证点 |
|---|---|
| `test_create_shot_requires_script_id` | 不传 script_id 创建分镜返回 422 |
| `test_create_character_requires_script_id` | 不传 script_id 创建角色返回 422 |
| `test_split_shots_uses_correct_script` | 第二集分镜拆分后序号从 1 开始，不追加到第一集末尾 |
| `test_split_shots_writes_script_id` | 拆分生成的分镜 script_id 等于传入的 script_id |
| `test_extract_characters_uses_correct_script` | 第二集提取角色用第二集剧本内容（mock LLM 验证入参） |
| `test_extract_scenes_uses_correct_script` | 同上 |
| `test_extract_props_uses_correct_script` | 同上 |
| `test_list_shots_filter_by_script_id` | `?script_id=1` 只返回第一集分镜 |
| `test_list_shots_without_script_id_returns_all` | 不传 script_id 返回全部集分镜 |
| `test_list_characters_filter_by_script_id` | 角色列表按集过滤 |
| `test_copy_character_to_other_episode` | 复制后目标集出现新记录，名称/形象图一致 |
| `test_copy_character_name_conflict_adds_suffix` | 目标集已有同名时加"（副本）"后缀 |
| `test_copy_character_does_not_copy_shot_association` | 复制不复制分镜关联 |
| `test_delete_script_cascades_resources` | 删除某集剧本后该集角色/场景/道具/分镜全部删除 |
| `test_split_shots_invalid_script_id_returns_404` | 不存在的 script_id 返回 404 |
| `test_split_shots_cross_project_returns_404` | script_id 属于其他项目返回 404 |
| `test_shot_sequence_no_unique_per_script` | 同集内 sequence_no 唯一，跨集可重复 |
| `test_response_includes_episode_no` | Response 带 episode_no 字段 |

### 9.2 前端测试

项目现有前端测试框架按现有约定补充。重点测试 Store 层：

| 测试用例 | 验证点 |
|---|---|
| `setCurrentScript` 切换集后重新拉取四类资源 | mock api.list，验证调用参数带 script_id |
| `setCurrentScript(null)` 切换到全部集时不传 script_id | 验证 api 调用 params 为 undefined |
| `extractEntitiesFromScript` 真正发送 script_id | 验证 POST body 包含 script_id |
| `splitShotsFromScript` 真正发送 script_id | 同上 |
| `createShot` 在 currentScriptId=null 时抛错 | 验证抛出"请先选择集数" |
| `copyEntityTo` 调用正确接口 | 验证 POST URL 和 body |

### 9.3 手动验证清单

实现完成后需手动验证：

1. 创建项目，向导生成第一集剧本和分镜
2. 在剧本 Tab 新增第二集剧本
3. 顶部切换器选"第2集"，进入分镜 Tab，点击"从剧本拆分"
4. 验证第二集分镜序号从 1 开始，不混入第一集
5. 切换到"全部集"视图，验证按集分组展示
6. 在第二集 Tab 点击"从剧本提取角色"，验证用第二集剧本内容
7. 在第一集角色卡片点击"复制到其他集"选第二集，切换到第二集验证角色出现
8. 删除第二集剧本，验证第二集的分镜/角色/场景/道具全部消失，第一集不受影响
9. 全部集视图下"新建"按钮禁用并显示提示

## 十、改动文件清单

### 10.1 后端

| 文件 | 改动内容 |
|---|---|
| `backend/app/models/project.py` | 四张资源表加 `script_id` 外键（NOT NULL + CASCADE + index）；分镜唯一约束改为 `(project_id, script_id, sequence_no)`；ProjectScript 增加反向 relationship |
| `backend/app/schemas/project.py` | 四类 Create/Response 加 `script_id`；Response 加 `episode_no`；ScriptResponse 加计数字段；新增 `ExtractRequest` / `CopyToRequest` |
| `backend/app/routes/projects.py` | 四个 list 接口加 `script_id` query 参数；四个 extract/split 接口改请求体；新增三个 copy-to 接口；工厂模式签名调整 |
| `backend/app/services/project/shot_service.py` | `split_shots_from_script` / `list_shots` / `create_shot` 接收 script_id；序号计算按集（分镜不提供跨集复制，见 2.2 非目标） |
| `backend/app/services/project/character_service.py` | `extract_characters_from_script` / `list_characters` / `create_character` 接收 script_id；新增 `copy_character_to_script` |
| `backend/app/services/project/scene_service.py` | 同 character_service |
| `backend/app/services/project/prop_service.py` | 同 character_service |
| `backend/app/services/project/wizard.py` | `_step_storyboard_split` 创建分镜时传 `script_id=script.id` |
| `backend/tests/test_episode_isolation.py` | 新增，覆盖 9.1 节所有用例 |

### 10.2 前端

| 文件 | 改动内容 |
|---|---|
| `frontend/src/api/projects.ts` | list 接口加 scriptId 可选参数；extract/split 真正发送 script_id（去掉下划线）；新增 copyTo 接口 |
| `frontend/src/stores/project.ts` | state 加 `currentScriptId`；`setCurrentScript` action；fetchXxx 使用 currentScriptId；新增 `copyEntityTo`；新增按集分组 getter |
| `frontend/src/components/project/ProjectManagerView.vue` | 顶部新增集数切换器；onMounted 默认选第一集 |
| `frontend/src/components/project/ShotsTab.vue` | 列表按集分组渲染；新建/拆分按钮逻辑；全部集视图禁用新建 |
| `frontend/src/components/project/CharactersTab.vue` | 列表按集分组；修复 onExtractFromScript 用 currentScriptId；跨集复制按钮 |
| `frontend/src/components/project/ScenesTab.vue` | 同 CharactersTab |
| `frontend/src/components/project/PropsTab.vue` | 同 CharactersTab |
| `frontend/src/i18n/` | 新增集数切换相关 key |

### 10.3 不改动的文件

- `frontend/src/views/projects/ProjectDetailView.vue` — 不涉及集数切换
- `frontend/src/components/project/ScriptTab.vue` — 保持独立选中状态
- `backend/app/services/project/wizard_chains.py` — 向导链路本身不变，只是 `_step_storyboard_split` 内部传 script_id

## 十一、风险与权衡

### 11.1 NOT NULL 导致向导流程必须改对

风险：`wizard.py` 的 `_step_storyboard_split` 当前不传 script_id，改 NOT NULL 后会直接报错。

缓解：向导步骤 1 已创建 script 对象（`_step_script_generation`），只需把 `script.id` 透传到步骤 2 的 ProjectShot 创建即可，改动小且有测试覆盖。

### 11.2 强隔离下跨集复用成本

风险：同一角色在多集出现需在每集分别创建/提取，用户操作成本高。

缓解：本期提供"复制到其他集"功能（深拷贝名称/描述/形象图），用户可在第一集建好后一键复制到其他集。后续如发现复用需求强烈，可考虑加"全局角色库"方案（非本期范围）。

### 11.3 全部集视图性能

风险：项目集数多时，全部集视图一次拉取所有资源，可能数据量大。

缓解：
- 列表接口默认按 `sort_order` 排序，前端按集分组展示，单集内数据量可控
- 如未来出现性能问题，可加分页（非本期范围）
- 首次进入默认选第一集而非全部集，避免一进来就拉全量

### 11.4 级联删除的破坏性

风险：删除某集剧本会自动删除该集下所有资源，用户可能误删。

缓解：
- 前端删除剧本时弹确认框，明确提示"将删除该集下所有分镜/角色/场景/道具"
- 后端 ondelete=CASCADE 是数据库层保障，即使前端漏确认也无法绕过
- 项目未上线，无存量数据保护需求

### 11.5 Response 带 episode_no 的实现方式

风险：list 查询要带 `episode_no`，可能引入 N+1 或 join 复杂度。

缓解：Service 层批量查一次 `scripts` 字典（key=script_id, value=episode_no），在内存映射填充 Response，避免 N+1。单项目集数通常 < 50，字典查询 O(1)。

## 十二、数据流总览

```
用户切换集数（顶部切换器）
  └─ store.setCurrentScript(scriptId)
       ├─ 更新 currentScriptId
       └─ Promise.all([fetchShots, fetchCharacters, fetchScenes, fetchProps])
            └─ 每个 fetch 带 currentScriptId 调 list 接口
                 └─ 后端按 script_id 过滤返回（带 episode_no）
                      └─ Store 更新扁平数组
                           └─ 各 Tab 响应式渲染

全部集视图（currentScriptId=null）
  └─ list 接口不传 script_id → 后端返回全部
       └─ getter shotsByEpisode 按 episode_no 分组
            └─ UI 按集分区折叠展示

从剧本提取/拆分（单集视图）
  └─ Tab 调 store.extractEntitiesFromScript(type, currentScriptId)
       └─ API POST body 带 script_id
            └─ 后端用 script_id 精确查剧本，不再 .first() 取第一集
                 └─ 提取结果写入对应 script_id 下
                      └─ 重新 fetchEntities 刷新当前集列表

跨集复制
  └─ 卡片"复制到其他集"下拉选目标集
       └─ store.copyEntityTo(type, entityId, targetScriptId)
            └─ API POST /copy-to {target_script_id}
                 └─ 后端深拷贝生成新记录（script_id=target）
                      └─ 留在当前集，用户切换到目标集时可见
```
