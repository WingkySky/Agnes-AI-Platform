# 时间线预览完整版 + 字幕 drawtext 兜底 实施计划

> 创建日期：2026-07-05
> 目标：实现时间线编辑器的完整版预览（多片段+音频+字幕实时联动），并修复字幕烧录（drawtext 兜底）

## 背景与目标

### 当前问题
1. **预览缺失**：TimelineEditor 内的"播放"按钮是占位 stub，点击只弹提示框，无法真正预览时间线
2. **字幕烧录失败**：当前 ffmpeg 未编译 libass，`subtitles` 滤镜不可用，回退到 `mov_text` 软字幕（浏览器默认不显示）

### 目标
1. **完整版预览**：在时间线编辑器内实现视频片段+音频+字幕的实时联动预览，未合成的项目也能预览
2. **字幕修复**：补回 drawtext 兜底路径，libass 不可用时自动走 drawtext 直烧，立即可用

## 技术方案

### 预览核心策略
- **多 `<video>` / `<audio>` 元素 + requestAnimationFrame 主时钟调度 + HTML 字幕 overlay**
- 主时钟用 `performance.now()` 累积，避免依赖单个 `video.currentTime`
- 视频元素全部 `muted`，音频走独立 `<audio>` 元素
- 字幕用 HTML overlay div，CSS 映射 SubtitleStyle

### 字幕策略
- 优先级：libass 可用 → ASS 硬烧；不可用 → drawtext 直烧（新补回）
- drawtext 是 ffmpeg 内置滤镜，无 libass 依赖，立即可用
- 复用旧 pipeline 时期的字体查找/转义逻辑（`watermark_service.py` 已保留）

## 任务拆解

### 阶段 1：字幕 drawtext 兜底（后端，独立可上线）

#### Task 1.1：补回 drawtext 字幕烧录路径
**文件**：`backend/app/services/project/merge_service.py`

**修改点**：
1. 新增 `_check_drawtext_available()` 函数（检测 ffmpeg 是否支持 drawtext 滤镜，结果缓存）
2. 新增 `_build_drawtext_filter(clips, style, video_width, video_height)` 函数
   - 输入：字幕片段列表 + SubtitleStyle + 视频分辨率
   - 输出：drawtext 滤镜字符串列表（每条字幕一个 drawtext）
   - 复用 `watermark_service.py` 的字体查找和文本转义逻辑
3. 修改 `execute_merge_advanced` 的字幕生成逻辑：
   - libass 可用 → ASS 硬烧（保持现状）
   - libass 不可用 + drawtext 可用 → drawtext 直烧（新增）
   - 两者都不可用 → SRT 软字幕（保持现状）
4. 修改 `_ffmpeg_final_composite` 支持 `subtitle_mode="drawtext"` 模式
   - drawtext 模式：构造 `-vf drawtext=...` 滤镜链烧录到画面

**验证**：
- 当前 ffmpeg 无 libass 但有 drawtext，应自动走 drawtext 直烧
- 生成的 final.mp4 在浏览器播放能看到字幕

#### Task 1.2：drawtext 字幕样式映射
**文件**：`backend/app/services/project/merge_service.py`

**修改点**：
- `_build_drawtext_filter` 中映射 SubtitleStyle 到 drawtext 参数：
  - `font_family` → `fontfile=`（通过 `_find_font` 查找系统字体）
  - `font_size` → `fontsize=`
  - `font_color` → `fontcolor=`（hex 转 0xRRGGBB）
  - `outline_color` + `outline_width` → `borderw=` + `bordercolor=`
  - `position=bottom` → `y=h-text_h-margin_v`
  - `margin_vertical` → `margin_v`（垂直边距）
  - `start_time` + `duration` → `enable='between(t,start,end)'`

**验证**：
- 字幕位置、字体、颜色、描边符合 SubtitleStyle 配置

### 阶段 2：后端 timeline_data 扩展（预览前置）

#### Task 2.1：扩展 timeline_data 返回 source_file_url
**文件**：`backend/app/services/project/timeline_service.py`

**修改点**：
- `get_timeline_data` 在序列化每个 clip 时，根据 `source_type` + `source_id` 关联查询：
  - `source_type='shot_video'` → 查 `ProjectShotVideo`，注入 `source_file_url`、`source_duration_ms`、`source_width`、`source_height`、`source_thumbnail_url`
  - `source_type='shot_audio'` → 查 `ProjectShotAudio`，注入 `source_file_url`、`source_duration_ms`
  - `source_type='subtitle'` → 不注入（用 `subtitle_text`）
- 批量查询优化：先收集所有 source_id，按类型分组 IN 查询，避免 N+1

**验证**：
- `/api/projects/{id}/timeline/data` 返回的 clips 中包含 source_file_url 等字段

#### Task 2.2：更新 TimelineClipResponse schema
**文件**：`backend/app/schemas/project.py`

**修改点**：
- `TimelineClipResponse` 新增可选字段：
  - `source_file_url: Optional[str]`
  - `source_duration_ms: Optional[int]`
  - `source_width: Optional[int]`
  - `source_height: Optional[int]`
  - `source_thumbnail_url: Optional[str]`

**验证**：
- schema 校验通过，OpenAPI 文档更新

#### Task 2.3：更新前端 TimelineClip 类型
**文件**：`frontend/src/types/project.ts`

**修改点**：
- `TimelineClip` 接口新增对应可选字段

**验证**：
- TypeScript 编译通过

### 阶段 3：预览调度核心（composable）

#### Task 3.1：创建 useTimelinePreview composable
**文件**：`frontend/src/composables/useTimelinePreview.ts`（新建）

**核心 API**：
```typescript
export function useTimelinePreview(options: {
  clips: Ref<TimelineClip[]>
  subtitleStyle: Ref<SubtitleStyle | null>
  totalDuration: Ref<number>
}) {
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const activeVideoClipId = ref<number | null>(null)
  const activeAudioClipId = ref<number | null>(null)
  const activeSubtitleText = ref('')

  const videoEls = new Map<number, HTMLVideoElement>()
  const audioEls = new Map<number, HTMLAudioElement>()

  function registerVideoEl(clipId: number, el: HTMLVideoElement | null)
  function registerAudioEl(clipId: number, el: HTMLAudioElement | null)
  async function play(): Promise<void>
  function pause(): void
  function seek(t: number): void
  function stop(): void

  return {
    isPlaying, currentTime,
    activeVideoClipId, activeAudioClipId, activeSubtitleText,
    registerVideoEl, registerAudioEl,
    play, pause, seek, stop,
  }
}
```

**调度算法**：
- `play()`：记录 `startTimeRef = performance.now() - currentTime.value * 1000`，启动 `requestAnimationFrame(tick)`
- `tick()`：
  1. 计算 `currentTime = (performance.now() - startTimeRef) / 1000`
  2. 找当前时间对应的 video clip，激活其 `<video>`，其它暂停隐藏
  3. 同样调度 audio clip
  4. 找当前时间对应的 subtitle clip，更新 `activeSubtitleText`
  5. 若 `currentTime >= totalDuration`，停止
- `seek(t)`：更新 `currentTime`，重置 `startTimeRef`，立即调度一次
- `pause()`：取消 RAF，暂停所有 video/audio

**关键细节**：
- 视频 seek 容差：`Math.abs(el.currentTime - target) > 0.1` 才 seek，避免频繁 seek 卡顿
- 视频元素 `muted` 必须设为 true（避免与 audio 叠加）
- 未加载片段的容错：`source_file_url` 为空时显示占位

**验证**：
- 单元测试或手动测试：3 个视频片段连续播放，播放头跟随，字幕同步切换

### 阶段 4：预览容器组件

#### Task 4.1：创建 TimelinePreview 组件
**文件**：`frontend/src/components/project/timeline/TimelinePreview.vue`（新建）

**模板结构**：
```vue
<template>
  <div class="timeline-preview" :class="{ playing: isPlaying }">
    <!-- 视频元素池（隐藏，只渲染不显示） -->
    <div class="media-pool" aria-hidden="true">
      <video
        v-for="clip in videoClips"
        :key="clip.id"
        :ref="el => registerVideoEl(clip.id, el as HTMLVideoElement | null)"
        :src="clip.source_file_url || undefined"
        :poster="clip.source_thumbnail_url || undefined"
        muted
        playsinline
        preload="auto"
        @error="onMediaError(clip.id, $event)"
      />
      <audio
        v-for="clip in audioClips"
        :key="clip.id"
        :ref="el => registerAudioEl(clip.id, el as HTMLAudioElement | null)"
        :src="clip.source_file_url || undefined"
        preload="auto"
      />
    </div>

    <!-- 预览画面区：显示当前激活的视频 -->
    <div class="preview-stage">
      <video
        v-for="clip in videoClips"
        :key="'display-' + clip.id"
        v-show="activeVideoClipId === clip.id"
        :ref="el => registerVideoDisplayEl(clip.id, el as HTMLVideoElement | null)"
        :src="clip.source_file_url || undefined"
        :poster="clip.source_thumbnail_url || undefined"
        muted
        playsinline
        preload="auto"
        class="preview-video"
      />
      <div v-if="!activeVideoClipId" class="preview-empty">
        <el-icon :size="48"><VideoPlay /></el-icon>
        <span>点击播放按钮开始预览</span>
      </div>
    </div>

    <!-- 字幕 overlay -->
    <div class="subtitle-overlay" v-if="activeSubtitleText">
      <span class="subtitle-text" :style="subtitleStyleCss">{{ activeSubtitleText }}</span>
    </div>
  </div>
</template>
```

**关键设计**：
- **双 video 元素**：每个视频片段有 2 个 `<video>` 元素
  - 1 个隐藏在 media-pool 用于预加载和 seek
  - 1 个在 preview-stage 用于实际显示（v-show 控制）
  - 原因：避免 display:none 影响 video 加载，同时分离显示和预加载职责
- **字幕 overlay**：CSS 映射 SubtitleStyle，绝对定位在底部
- **空状态**：无激活视频时显示提示

**字幕样式 CSS 映射**：
```typescript
const subtitleStyleCss = computed(() => {
  const s = subtitleStyle.value
  if (!s) return {}
  return {
    fontFamily: s.font_family || 'Microsoft YaHei',
    fontSize: `${s.font_size || 24}px`,
    color: s.font_color || '#FFFFFF',
    textShadow: `0 0 ${s.outline_width || 2}px ${s.outline_color || '#000000'}, 0 0 ${s.outline_width || 2}px ${s.outline_color || '#000000'}`,
    marginBottom: `${s.margin_vertical || 40}px`,
  }
})
```

**验证**：
- 预览画面正确显示当前视频片段
- 字幕按时间同步切换
- 无激活视频时显示空状态提示

### 阶段 5：集成到 TimelineTab

#### Task 5.1：TimelineTab 集成预览
**文件**：`frontend/src/components/project/timeline/TimelineTab.vue`

**修改点**：
1. 引入 `TimelinePreview` 组件和 `useTimelinePreview` composable
2. 初始化 composable：
   ```typescript
   const preview = useTimelinePreview({
     clips: computed(() => draftClips.value),
     subtitleStyle: computed(() => projectStore.subtitleStyle),
     totalDuration,
   })
   ```
3. 替换 stub 实现：
   - `onPlay` → `preview.isPlaying.value ? preview.pause() : preview.play()`
   - `onSeek` → `preview.seek(t)`
4. 模板新增 `<TimelinePreview>` 组件（放在工具栏下方、编辑器上方）
5. `preview.currentTime` watch → 同步到 TimelineEditor 的 `playheadTime`

**验证**：
- 点击播放按钮，预览启动，播放头跟随
- 点击标尺，预览跳转到对应位置
- 拖拽播放头，预览跟随

#### Task 5.2：TimelineEditor 受控播放头
**文件**：`frontend/src/components/project/timeline/TimelineEditor.vue`

**修改点**：
- `playheadTime` 支持受控模式：新增 `playheadTime` prop（受控）+ 内部 `internalPlayheadTime`（非受控）
- 优先使用 prop，无 prop 时回退到内部状态
- 播放按钮 emit `play` 事件（保持现状，由父组件处理）
- `onRulerClick` / `onPlayheadDrag` emit `seek` 事件（保持现状）

**验证**：
- 受控模式下播放头跟随预览 currentTime
- 非受控模式下点击标尺/拖拽播放头正常工作

#### Task 5.3：当前播放片段高亮
**文件**：`frontend/src/components/project/timeline/TimelineClip.vue`

**修改点**：
- 新增 `isPlayingClip` prop（boolean）
- 播放中的片段添加高亮样式（边框+阴影）

**验证**：
- 播放时当前片段高亮，停止时取消高亮

### 阶段 6：清理与优化

#### Task 6.1：移除编辑器内冗余播放按钮（可选）
**文件**：`frontend/src/components/project/timeline/TimelineEditor.vue`

**决策**：保留编辑器内的播放按钮（用于触发预览），但在预览容器也有播放控件，形成"预览区+编辑器"双控件联动

**不修改**，保持现状。

#### Task 6.2：预览性能优化
**文件**：`frontend/src/composables/useTimelinePreview.ts`

**优化点**：
- 只预加载当前播放位置 ±2 个 clip 的视频元素，其它 `preload="none"`
- 调度时动态切换 `preload` 属性
- 大量片段（>20）时显示警告

**验证**：
- 20+ 片段时内存占用合理，无明显卡顿

## 文件清单

### 新建（2 个）
| 文件 | 作用 |
|---|---|
| `frontend/src/components/project/timeline/TimelinePreview.vue` | 预览容器组件 |
| `frontend/src/composables/useTimelinePreview.ts` | 调度 composable |

### 修改 - 后端（4 个）
| 文件 | 修改点 |
|---|---|
| `backend/app/services/project/merge_service.py` | 补回 drawtext 字幕烧录路径 |
| `backend/app/services/project/timeline_service.py` | `get_timeline_data` 关联查询注入 source_file_url |
| `backend/app/schemas/project.py` | `TimelineClipResponse` 新增 source_* 字段 |
| `backend/app/services/watermark_service.py` | 抽取 `_find_font` / `_escape_drawtext_text` 为可复用函数（可选，或直接在 merge_service 中复用） |

### 修改 - 前端（5 个）
| 文件 | 修改点 |
|---|---|
| `frontend/src/types/project.ts` | `TimelineClip` 新增 source_* 字段 |
| `frontend/src/components/project/timeline/TimelineTab.vue` | 集成预览组件和 composable |
| `frontend/src/components/project/timeline/TimelineEditor.vue` | 播放头支持受控模式 |
| `frontend/src/components/project/timeline/TimelineClip.vue` | 新增 isPlayingClip 高亮 |
| `frontend/src/api/projects.ts` | 无需修改（复用 getTimelineData） |

## 验收标准

### 字幕修复
- [ ] 当前 ffmpeg（无 libass）能成功烧录字幕到画面
- [ ] final.mp4 在浏览器播放能看到中文字幕
- [ ] 字幕样式（字体/颜色/描边/位置）符合 SubtitleStyle 配置

### 预览功能
- [ ] 点击播放按钮，预览启动，视频+音频+字幕同步播放
- [ ] 播放头跟随预览 currentTime 实时移动
- [ ] 点击时间标尺，预览跳转到对应位置
- [ ] 拖拽播放头，预览跟随
- [ ] 当前播放片段在时间线上高亮
- [ ] 字幕按时间同步切换显示
- [ ] 未合成项目（无 final.mp4）也能预览
- [ ] 暂停/继续/停止功能正常
- [ ] 预览结束自动停止并重置到起点

## 实施顺序

1. **阶段 1**（字幕修复，独立可上线）：Task 1.1 → 1.2
2. **阶段 2**（后端数据扩展）：Task 2.1 → 2.2 → 2.3
3. **阶段 3**（调度核心）：Task 3.1
4. **阶段 4**（预览容器）：Task 4.1
5. **阶段 5**（集成）：Task 5.1 → 5.2 → 5.3
6. **阶段 6**（优化）：Task 6.2

字幕修复（阶段 1）与预览功能（阶段 2-6）相互独立，可分别上线。
