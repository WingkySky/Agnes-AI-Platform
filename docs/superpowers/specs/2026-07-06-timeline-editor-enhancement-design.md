# 时间线编辑器增强设计

**日期**：2026-07-06
**作者**：brainstorming 协作产出
**状态**：待审阅

## 背景与目标

当前时间线编辑器已实现基础剪辑能力（分割、波纹删除、拖拽吸附、撤销/重做、键盘快捷键），但存在两大缺口：

1. **添加片段缺乏实质**：`AddClipDialog` 只是空表单，不关联项目实体，添加出来的片段无源文件、预览无法显示内容
2. **布局固化**：预览区固定较大高度，素材库、预览、时间线三区无法弹性调整，用户无法根据场景优化可视面积

本次设计目标：
- **建立项目素材库**：把项目下生成的视频/音频/帧图/BGM 聚合成可拖拽的素材库，用户可拖到时间线任意位置
- **弹性三区布局**：素材库（左）+ 预览区（右）+ 时间线（底部全宽），分隔条可拖拽，面板可隐藏
- **补充剪辑功能**：复制/剪切/粘贴、标记 Markers、轨道 Mute/Lock

参考来源：[walterlow/freecut](https://github.com/walterlow/freecut) 的剪辑器核心交互模式（媒体库面板 + 拖拽到时间线 + 多种编辑模式）。

## 范围

### 本次实现（P0+P1）

- 弹性布局（垂直/水平分隔条、素材库可隐藏、状态持久化）
- 项目素材库（4 类素材聚合 API + 前端面板）
- 拖拽到时间线（含落点高亮、吸附、防重叠）
- 复制/剪切/粘贴
- 轨道 Mute / Lock（M+L 两按钮）
- 标记 Markers（持久化到数据库）

### 暂不实现（P2，后续阶段）

- 插入编辑（Insert Edit）
- Solo 独听、Hide 单独隐藏按钮（与 Lock 合并）
- 滚动/滑动/滑移编辑（Rolling/Slip/Slide）
- 速率拉伸、冻结帧

## 设计

### 1. 弹性三区布局

#### 1.1 布局结构

```
┌─────────────────────────────────────────────┐
│ 顶部工具栏（撤销/重做/播放/分割/合成）          │
├──────────┬──┬──────────────────────────────┤
│  素材库   │垂│      预览区                  │
│ 240px    │直│      flex:1                  │
│可隐藏    │分│      最小 320px              │
│可调整    │隔│                              │
│180-400px │条│                              │
├──────────┴──┴──────────────────────────────┤
│         水平分隔条（可拖拽）                  │
├─────────────────────────────────────────────┤
│  时间线编辑器（底部全宽，默认 240px 高）       │
│  最小 120px，最大 60% 视口                    │
└─────────────────────────────────────────────┘
```

#### 1.2 面板尺寸约束

| 面板 | 默认 | 最小 | 最大 | 可隐藏 |
|---|---|---|---|---|
| 素材库 | 240px 宽 | 180px | 400px | 是 |
| 预览区 | flex:1 | 320px 宽 | 100%（素材库隐藏时） | 否 |
| 时间线 | 240px 高 | 120px | 60% 视口高度 | 否 |

#### 1.3 交互特性

- **垂直分隔条**：素材库与预览区之间，鼠标拖拽调整两侧宽度，hover 时变蓝
- **水平分隔条**：预览区行与时间线之间，拖拽调整时间线高度
- **素材库隐藏**：点素材库右上角 ◀ 收起，预览区获得全宽；左侧边缘保留竖条按钮可重新展开
- **状态持久化**：宽度/高度/隐藏状态通过 localforage 保存到 `timeline_layout` key，按 `project_id` 分键，下次进入恢复
- **拖拽落点高亮**：从素材库拖到时间线时，目标轨道高亮显示落点位置，吸附到相邻片段边界与播放头

#### 1.4 实现要点

新增组件 `TimelineSplitter.vue`（可复用的拖拽分隔条组件），支持方向（horizontal/vertical）、min/max、v-model 绑定值。

新增 composable `useTimelineLayout.ts`：
```typescript
interface TimelineLayoutState {
  libraryWidth: number       // 180-400
  libraryHidden: boolean
  timelineHeight: number    // 120-60%vh
}

async function loadLayout(projectId: number): Promise<TimelineLayoutState>
async function saveLayout(projectId: number, state: TimelineLayoutState): Promise<void>
```

`TimelineTab.vue` 改造：将现有的 `TimelinePreview` 与 `TimelineEditor` 包装为弹性容器，注入 `useTimelineLayout` 提供的尺寸状态。

### 2. 项目素材库

#### 2.1 数据结构

前端统一项结构 `MediaLibraryItem`：

```typescript
// frontend/src/types/project.ts 新增

/** 素材库项类型 */
type MediaItemType = 'shot_video' | 'shot_audio' | 'shot_frame_image' | 'bgm'

/** 素材库统一项结构（用于拖拽到时间线） */
interface MediaLibraryItem {
  id: number                      // 源实体 ID
  type: MediaItemType
  name: string                    // 显示名（如 "分镜1视频" 或 "BGM-舒缓钢琴"）
  file_url: string                // 可播放的 HTTP URL
  thumbnail_url?: string | null
  duration_ms: number             // 毫秒，用于创建片段的 duration
  width?: number | null
  height?: number | null
  shot_id?: number | null         // 关联分镜（便于溯源）
  meta?: {
    voice_name?: string           // shot_audio: 音色名
    mood?: string                 // bgm: 情绪
    is_static_image?: boolean     // shot_frame_image: true
  }
}

/** 素材库按类型分组的响应 */
interface MediaLibraryResponse {
  videos: MediaLibraryItem[]        // ProjectShotVideo
  audios: MediaLibraryItem[]        // ProjectShotAudio
  frame_images: MediaLibraryItem[] // ProjectShotFrameImage（静态图，duration_ms 默认 3000）
  bgms: MediaLibraryItem[]          // BGMItem（新增 URL 字段）
}
```

#### 2.2 后端改动

| 改动 | 文件 | 说明 |
|---|---|---|
| **新增 API**: `GET /api/projects/{pid}/media-library` | `routes/projects.py` | 一次性返回四类素材聚合数据 |
| **新增 API**: `GET /api/projects/{pid}/bgms/{bgm_id}/file` | `routes/projects.py` | 暴露 BGM 文件 HTTP URL（FileResponse） |
| **新增 source_type**: `shot_frame_image` / `bgm` | `models/project.py` 注释 + `timeline_service.py:get_timeline_data` 扩展预取 | 让 `get_timeline_data` 能注入这两类的 `source_file_url` 等字段 |
| **新增字段**: `ProjectTimelineClip.source_ref` | `models/project.py` | String(100) nullable，BGM 用此字段存 bgm_id 字符串（BGM id 是 string，无法存入 Integer 的 source_id） |
| **init_timeline 不动** | — | 仍只生成视频/音频，BGM/帧图靠用户从素材库拖拽添加 |

**BGM 文件端点实现**：
```python
@router.get("/{project_id}/bgms/{bgm_id}/file")
async def get_bgm_file(project_id: int, bgm_id: str):
    path = get_bgm_path(bgm_id)  # 复用 bgm_library
    if not path or not path.exists():
        raise HTTPException(404, "BGM 文件不存在")
    return FileResponse(path, media_type="audio/mpeg")
```

**media-library 端点实现**：在 `timeline_service.py` 新增 `get_media_library(db, project_id)` 函数，预取四类实体并组装为 `MediaLibraryResponse`。

#### 2.3 拖拽交互流程

```
[素材库]
  MediaLibraryItem 卡片 (draggable=true)
       │
       │ mousedown 开始拖拽，dataTransfer 携带 MediaLibraryItem JSON
       ▼
[拖拽中]
       │
       │ dragover 时间线轨道
       ▼
[时间线轨道高亮]
  显示落点指示线 + 时间读数 tooltip
       │
       │ drop 释放
       ▼
[onDrop 处理]
  1. 解析 MediaLibraryItem
  2. 根据 type 决定 track_type:
     - shot_video / shot_frame_image → video 轨
     - shot_audio / bgm → audio 轨
  3. 根据 drop 位置计算 start_time
  4. 应用 snap 吸附（复用已有 snap 逻辑）
  5. 防重叠 clamp（复用已有逻辑）
  6. 构造 TimelineClipCreateRequest:
     - source_type = item.type
     - source_id = item.id（BGM 用 source_ref 存字符串）
     - shot_id = item.shot_id
     - start_time, duration = item.duration_ms / 1000
     - trim_start = 0, trim_end = null
     - 帧图类型 duration 默认 3s
  7. pushHistory() + projectStore.createTimelineClip(payload)
  8. drop 后选中新建的片段
```

#### 2.4 静态帧图处理

`ProjectShotFrameImage` 无 `duration_ms` 字段。素材库组装时给 frame_images 类统一填 `duration_ms: 3000`（3 秒）。拖到时间线后用户可裁剪调整。

#### 2.5 source_type 扩展总览

| source_type | source_id 关联 | track_type | 备注 |
|---|---|---|---|
| `shot_video`（已有） | `project_shot_videos.id` | video | 复用现有逻辑 |
| `shot_audio`（已有） | `project_shot_audios.id` | audio | 复用现有逻辑 |
| `subtitle`（已有） | — | subtitle | 复用现有逻辑 |
| `shot_frame_image`（**新增**） | `project_shot_frame_images.id` | video | 静态图作视频片段 |
| `bgm`（**新增**） | `source_ref` 字段存 bgm_id 字符串 | audio | source_id 留空 |

### 3. 补充剪辑功能

#### 3.1 复制/剪切/粘贴

**剪贴板**：前端内存，不跨页面，不持久化。

```typescript
// frontend/src/composables/useClipClipboard.ts
interface ClipClipboardEntry {
  clip: TimelineClip            // 深拷贝的源片段
  operation: 'copy' | 'cut'    // cut = 复制后删除原片段
}

const useClipClipboard = () => {
  const clipboard = ref<ClipClipboardEntry | null>(null)
  function copy(clip: TimelineClip) {
    clipboard.value = { clip: deepClone(clip), operation: 'copy' }
  }
  // cut：立即删除原片段（pushHistory 由调用方在 cut 之前调用）
  async function cut(clip: TimelineClip) {
    clipboard.value = { clip: deepClone(clip), operation: 'cut' }
    await projectStore.deleteTimelineClip(clip.id)
    // cut 后剪贴板保持 'cut' 状态，首次 paste 时不会再次删除（因为原片段已删）
    // 在 paste 成功后将 operation 改为 'copy' 允许重复粘贴
  }
  async function paste(targetStartTime: number): Promise<void> {
    if (!clipboard.value) return
    const { clip, operation } = clipboard.value
    // 注意：cut 已在 cut() 调用时删除原片段，paste 不再重复删除
    await projectStore.createTimelineClip({
      track_type: clip.track_type,
      track_index: clip.track_index,
      source_type: clip.source_type,
      source_id: clip.source_id,
      shot_id: clip.shot_id,
      start_time: targetStartTime,
      duration: clip.duration,
      trim_start: clip.trim_start,
      trim_end: clip.trim_end ?? undefined,
      transition_type: clip.transition_type,
      transition_duration: clip.transition_duration,
      subtitle_text: clip.subtitle_text ?? undefined,
      sort_order: clip.sort_order,
    })
    // paste 成功后，cut 模式转为 copy 模式，允许重复粘贴
    if (operation === 'cut') {
      clipboard.value.operation = 'copy'
    }
  }
  return { copy, cut, paste, hasContent: computed(() => !!clipboard.value) }
}
```

**快捷键**：
- `Ctrl+C` / `Cmd+C`：复制选中片段（仅存入剪贴板，不删除原片段）
- `Ctrl+X` / `Cmd+X`：剪切选中片段（复制到剪贴板，**立即删除原片段**，操作入栈 pushHistory）
- `Ctrl+V` / `Cmd+V`：在播放头位置粘贴（若剪贴板是 cut 来源，粘贴后剪贴板转为 copy 模式可重复粘贴；若是 copy 来源，原片段不受影响）

**入栈**：粘贴操作 `pushHistory()`（创建新片段算结构性变更）。

#### 3.2 标记 Markers

**后端**：新增 `project_markers` 表。

```python
# backend/app/models/project.py 新增
class ProjectMarker(Base):
    __tablename__ = "project_markers"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    time = Column(Float, nullable=False)         # 秒
    name = Column(String(100), nullable=True)    # 可选命名
    color = Column(String(20), default="#4a9eff")  # 颜色（默认蓝）
    created_at = Column(DateTime, default=datetime.utcnow)
```

**API**：
- `POST /api/projects/{pid}/markers` — 创建（body: `{ time, name?, color? }`）
- `GET /api/projects/{pid}/markers` — 列表
- `DELETE /api/projects/{pid}/markers/{mid}` — 删除

**前端**：
- 时间线标尺上方渲染标记旗帜图标（点击跳转）
- 标记可右键删除、命名
- 快捷键：
  - `Ctrl+M`：在播放头位置添加标记（弹出小输入框命名，可跳过）
  - `Shift+M`：删除离播放头最近的标记
  - `[`：跳到上一标记
  - `]`：跳到下一标记

**store 增加 `markers` state + `fetchMarkers / addMarker / deleteMarker` actions**。

#### 3.3 轨道 Mute / Lock

**状态管理**：会话级 UI 状态，不持久化到后端，但用 localforage 保存到 `timeline_track_states` key 按 `project_id` 分键。

```typescript
// frontend/src/stores/project.ts 新增
interface TrackState {
  muted: boolean    // 静音（预览时该轨不播放音频）
  locked: boolean   // 锁定（该轨片段不可拖拽/裁剪/删除）
}

// state 增加
trackStates: Record<string, TrackState>  // key = `${track_type}:${track_index}`

// actions
function setTrackMuted(trackType: string, trackIndex: number, muted: boolean)
function setTrackLocked(trackType: string, trackIndex: number, locked: boolean)
function isTrackMuted(trackType: string, trackIndex: number): boolean
function isTrackLocked(trackType: string, trackIndex: number): boolean
```

**轨道头部 UI**（在 `TimelineTrack.vue` 顶部加 M + L 两按钮）：
- **M**（Mute）：激活时蓝色，预览时跳过该轨音频
- **L**（Lock）：激活时橙色，该轨片段不可拖拽/裁剪/删除（onDragStart / onTrimStart 检查锁定状态直接 return）

**预览集成**：`useTimelinePreview.ts` 播放时检查 `trackStates.muted`，跳过该轨音频元素的 `play()` 调用。

**合成集成**：`merge_service.py` 通过 query 参数 `?include_muted_tracks=false` 控制是否包含静音轨（默认不包含）。

### 4. 快捷键总览

| 快捷键 | 功能 | 状态 |
|---|---|---|
| Space | 播放/暂停 | ✅ 已有 |
| Ctrl+K | 分割 | ✅ 已有 |
| Delete | 波纹删除 | ✅ 已有 |
| ←/→ | 帧步进 ±1（Shift = ±10） | ✅ 已有 |
| Ctrl+Z / Ctrl+Shift+Z | 撤销/重做 | ✅ 已有 |
| **Ctrl+C** | 复制选中片段 | 🆕 新增 |
| **Ctrl+X** | 剪切选中片段 | 🆕 新增 |
| **Ctrl+V** | 在播放头位置粘贴 | 🆕 新增 |
| **Ctrl+M** | 在播放头添加标记 | 🆕 新增 |
| **Shift+M** | 删除最近标记 | 🆕 新增 |
| **[ / ]** | 跳到上一/下一标记 | 🆕 新增 |

### 5. 合成服务适配

`merge_service.py` 需扩展两类新 source_type：

#### 5.1 shot_frame_image（静态图作视频）

```python
# 静态图转视频流：-loop 1 -i image.png -t duration -r 30
# 归一化后参与 concat
```

#### 5.2 bgm（背景音乐）

```python
# 通过 source_ref 取 BGM 本地路径
# amix 时与 shot_audio 一起混音
# BGM 通常贯穿整个视频，作为单独音轨处理
```

### 6. 实施优先级

| 优先级 | 功能 | 实施复杂度 | 价值 |
|---|---|---|---|
| P0 | 弹性布局 + 素材库 + 拖拽到时间线 | 高 | 核心价值 |
| P0 | 复制/剪切/粘贴 | 低 | 高频使用 |
| P1 | 轨道 Mute/Lock | 中 | 多轨场景必备 |
| P1 | 标记 Markers | 中 | 长视频导航 |
| P2（后续） | 插入编辑 | 中 | 进阶功能 |

## 数据模型变更

### 新增表

**project_markers**：
| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 主键 |
| project_id | Integer FK | 关联项目 |
| time | Float | 标记时间（秒） |
| name | String(100) nullable | 标记名 |
| color | String(20) | 颜色（默认 #4a9eff） |
| created_at | DateTime | 创建时间 |

### 修改表

**project_timeline_clips**：
| 新增字段 | 类型 | 说明 |
|---|---|---|
| source_ref | String(100) nullable | BGM 类型的字符串 id 引用（source_id 是 Integer 不够用） |

## API 变更

### 新增端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{pid}/media-library` | 获取四类素材聚合数据 |
| GET | `/api/projects/{pid}/bgms/{bgm_id}/file` | BGM 文件 HTTP URL |
| POST | `/api/projects/{pid}/markers` | 创建标记 |
| GET | `/api/projects/{pid}/markers` | 列出标记 |
| DELETE | `/api/projects/{pid}/markers/{mid}` | 删除标记 |

### 修改端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{pid}/timeline` | `get_timeline_data` 扩展预取 `shot_frame_image` 和 `bgm` 类型的源信息 |

## 前端组件变更

### 新增组件

| 组件 | 路径 | 说明 |
|---|---|---|
| `MediaLibraryPanel.vue` | `frontend/src/components/project/timeline/MediaLibraryPanel.vue` | 素材库面板（左侧抽屉，4 类 Tab） |
| `TimelineSplitter.vue` | `frontend/src/components/project/timeline/TimelineSplitter.vue` | 可拖拽分隔条组件（复用） |
| `MarkersRuler.vue` | `frontend/src/components/project/timeline/MarkersRuler.vue` | 标记旗帜渲染（嵌入 TimelineEditor 标尺上方） |
| `TrackHeaderControls.vue` | `frontend/src/components/project/timeline/TrackHeaderControls.vue` | 轨道头部 M/L 按钮 |

### 新增 composable

| Composable | 路径 | 说明 |
|---|---|---|
| `useTimelineLayout.ts` | `frontend/src/composables/useTimelineLayout.ts` | 弹性布局状态管理 + localforage 持久化 |
| `useClipClipboard.ts` | `frontend/src/composables/useClipClipboard.ts` | 复制/剪切/粘贴剪贴板 |
| `useMarkers.ts` | `frontend/src/composables/useMarkers.ts` | 标记 CRUD + 快捷键 |
| `useTrackStates.ts` | `frontend/src/composables/useTrackStates.ts` | 轨道 Mute/Lock 状态管理 |

### 修改组件

| 组件 | 改动 |
|---|---|
| `TimelineTab.vue` | 重构布局为弹性三区；接入素材库、剪贴板、标记、轨道状态 |
| `TimelineEditor.vue` | 标尺上方加 MarkersRuler；轨道头部加 TrackHeaderControls；轨道支持 drop 事件 |
| `TimelineTrack.vue` | 检查 trackStates.locked 拦截拖拽/裁剪；轨道头部加 M/L 按钮 |
| `useTimelinePreview.ts` | 播放时检查 trackStates.muted 跳过该轨音频 |
| `types/project.ts` | 新增 `MediaLibraryItem` / `MediaLibraryResponse` / `ProjectMarker` / `TrackState` 类型 |
| `stores/project.ts` | 新增 `markers` / `trackStates` state 和对应 actions；新增 `fetchMediaLibrary` action |
| `api/projects.ts` | 新增 `getMediaLibrary` / `getBgmFileUrl` / `listMarkers` / `createMarker` / `deleteMarker` 函数 |
| `AddClipDialog.vue` | 保留作为「手动添加空白片段」入口（少用，但不删除） |

## 错误处理

- **拖拽创建失败**：`projectStore.createTimelineClip` 失败时回滚 `pushHistory()`，ElMessage 提示错误
- **BGM 文件 404**：`GET /bgms/{bgm_id}/file` 返回 404 时，前端素材库该 BGM 项 disabled 并显示「文件缺失」标签
- **标记创建失败**：ElMessage 提示，不影响时间线
- **轨道状态持久化失败**：localforage 写入失败时静默降级（仅会话内有效）

## 测试策略

- **后端**：新增 `test_media_library.py` 测试聚合 API、BGM 文件端点；`test_markers.py` 测试 CRUD
- **前端**：
  - 素材库拖拽到时间线的端到端流程（dragstart → drop → 创建片段 → 选中）
  - 复制/剪切/粘贴的撤销/重做一致性
  - 轨道锁定状态下拖拽被拦截
  - 标记快捷键（Ctrl+M / Shift+M / [ / ]）
- **回归**：现有 split/ripple/undo-redo 不被破坏

## 兼容性

- **数据库**：新增 `project_markers` 表 + `project_timeline_clips.source_ref` 字段，向后兼容（旧片段 source_ref 为 null）
- **API**：新增端点不破坏旧端点
- **前端**：`AddClipDialog` 保留作为少用的手动入口，不强制迁移

## 未覆盖范围（后续阶段）

- 插入编辑（Insert Edit）
- Solo 独听、Hide 单独隐藏按钮
- 滚动/滑动/滑移编辑（Rolling/Slip/Slide）
- 速率拉伸、冻结帧
- 多机位编辑
- AI 智能剪辑建议

## 参考资料

- [walterlow/freecut](https://github.com/walterlow/freecut) 剪辑器交互参考
- 项目现有时间线实现：`frontend/src/components/project/timeline/`
- 后端时间线服务：`backend/app/services/project/timeline_service.py`
