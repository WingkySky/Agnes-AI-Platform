<!-- =====================================================
     字幕样式对话框 SubtitleStyleDialog
     - 编辑字幕字体/字号/颜色/描边/位置/边距
     - 实时预览字幕效果
     - 保存到 projects.timeline_data.subtitle_style
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    title="字幕样式"
    width="560px"
    :close-on-click-modal="false"
    append-to-body
  >
    <div class="style-editor">
      <!-- 表单区 -->
      <el-form :model="formData" label-width="100px" size="default">
        <el-form-item label="字体">
          <el-select v-model="formData.font_family" placeholder="选择字体" filterable>
            <el-option
              v-for="font in fontOptions"
              :key="font"
              :label="font"
              :value="font"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="字号">
          <el-slider
            v-model="formData.font_size"
            :min="12"
            :max="120"
            :step="1"
            show-input
            :show-input-controls="false"
          />
        </el-form-item>

        <el-form-item label="字体颜色">
          <el-color-picker v-model="formData.font_color" />
          <span class="color-hex">{{ formData.font_color }}</span>
        </el-form-item>

        <el-form-item label="描边颜色">
          <el-color-picker v-model="formData.outline_color" />
          <span class="color-hex">{{ formData.outline_color }}</span>
        </el-form-item>

        <el-form-item label="描边宽度">
          <el-slider
            v-model="formData.outline_width"
            :min="0"
            :max="10"
            :step="1"
            show-input
            :show-input-controls="false"
          />
        </el-form-item>

        <el-form-item label="位置">
          <el-radio-group v-model="formData.position">
            <el-radio-button value="top">顶部</el-radio-button>
            <el-radio-button value="center">居中</el-radio-button>
            <el-radio-button value="bottom">底部</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="垂直边距">
          <el-slider
            v-model="formData.margin_vertical"
            :min="0"
            :max="300"
            :step="5"
            show-input
            :show-input-controls="false"
          />
        </el-form-item>
      </el-form>

      <!-- 预览区 -->
      <div class="preview-area">
        <div class="preview-label">预览</div>
        <div
          class="preview-frame"
          :class="formData.position"
          :style="{ padding: formData.margin_vertical + 'px 20px' }"
        >
          <span
            class="preview-text"
            :style="{
              fontFamily: formData.font_family,
              fontSize: formData.font_size + 'px',
              color: formData.font_color,
              textShadow: formData.outline_width > 0
                ? `${formData.outline_width}px ${formData.outline_width}px ${formData.outline_color}`
                : 'none',
            }"
          >这是字幕预览效果</span>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import type { SubtitleStyle } from '@/types/project'

const projectStore = useProjectStore()

const visible = defineModel<boolean>('visible', { default: false })

const props = defineProps<{
  /** 初始样式（传入时用于回填） */
  style?: SubtitleStyle | null
}>()

const emit = defineEmits<{
  (e: 'save', style: SubtitleStyle): void
}>()

// 默认字幕样式（与后端 DEFAULT_SUBTITLE_STYLE 对齐）
const DEFAULT_STYLE: SubtitleStyle = {
  font_family: 'Microsoft YaHei',
  font_size: 48,
  font_color: '#FFFFFF',
  outline_color: '#000000',
  outline_width: 2,
  position: 'bottom',
  margin_vertical: 60,
}

// 可选字体清单
const fontOptions = [
  'Microsoft YaHei',
  'SimHei',
  'SimSun',
  'KaiTi',
  'FangSong',
  'Arial',
  'Helvetica',
  'Times New Roman',
]

const formData = ref<SubtitleStyle>({ ...DEFAULT_STYLE })

// 对话框打开时回填样式
watch(visible, (open) => {
  if (open) {
    formData.value = { ...DEFAULT_STYLE, ...(props.style || projectStore.subtitleStyle || {}) }
  }
})

async function handleSave() {
  try {
    await projectStore.updateSubtitleStyle(formData.value)
    emit('save', { ...formData.value })
    ElMessage.success('字幕样式已保存')
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}
</script>

<style scoped>
.style-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.color-hex {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'Menlo', 'Monaco', monospace;
}

.preview-area {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  overflow: hidden;
}

.preview-label {
  padding: 6px 12px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.preview-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: linear-gradient(135deg, #2c3e50 0%, #4a6079 100%);
  display: flex;
  align-items: flex-start;
  justify-content: center;
}

.preview-frame.center {
  align-items: center;
}

.preview-frame.bottom {
  align-items: flex-end;
}

.preview-text {
  display: inline-block;
  max-width: 90%;
  text-align: center;
  line-height: 1.4;
  word-break: break-word;
}
</style>
