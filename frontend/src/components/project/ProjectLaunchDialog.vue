<!-- =====================================================
     项目创建对话框 ProjectLaunchDialog
     - 步骤 1: 选择模板（drama/ad/education/anime）
     - 步骤 2: 填写模板参数
     - 步骤 3: 触发向导创建并跳转详情页
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    :title="'创建项目'"
    width="640px"
    :close-on-click-modal="false"
    destroy-on-close
    @closed="resetState"
  >
    <!-- 步骤1：选择模板 -->
    <template v-if="step === 1">
      <div class="launch-section">
        <p class="launch-desc">选择一个创作场景模板</p>
        <el-scrollbar max-height="380px">
          <div class="template-list">
            <div
              v-for="tpl in templates"
              :key="tpl.key"
              class="template-item"
              :class="{ selected: selectedCategory === tpl.key }"
              @click="selectTemplate(tpl)"
            >
              <div class="template-thumb">
                <el-icon :size="36"><Film /></el-icon>
              </div>
              <div class="template-info">
                <div class="template-name">{{ tpl.name }}</div>
                <div class="template-desc">{{ tpl.description }}</div>
              </div>
            </div>
          </div>
        </el-scrollbar>
      </div>
    </template>

    <!-- 步骤2：配置参数 -->
    <template v-if="step === 2">
      <div class="launch-section">
        <p class="launch-desc">填写项目参数</p>
        <el-form label-position="top" class="param-form">
          <el-form-item label="项目标题" required>
            <el-input v-model="projectTitle" placeholder="为你的项目起个名字" />
          </el-form-item>
          <el-form-item label="项目描述">
            <el-input
              v-model="projectDescription"
              type="textarea"
              :rows="2"
              placeholder="简短描述（可选）"
            />
          </el-form-item>
          <el-form-item
            v-for="input in selectedTemplate?.inputs_config"
            :key="input.key"
            :label="input.label || input.key"
          >
            <el-input
              v-if="input.type === 'text' || input.type === 'string'"
              v-model="formInputs[input.key]"
              :placeholder="input.placeholder || input.description"
              type="textarea"
              :rows="input.key === 'story' || input.key === 'topic' || input.key === 'prompt' ? 4 : 2"
            />
            <el-input-number
              v-else-if="input.type === 'number' || input.type === 'int'"
              v-model="formInputs[input.key]"
              :min="input.min ?? 1"
              :max="input.max ?? 100"
              style="width: 100%"
            />
            <el-switch
              v-else-if="input.type === 'boolean' || input.type === 'bool'"
              v-model="formInputs[input.key]"
            />
            <el-select
              v-else-if="input.type === 'select' || input.type === 'enum'"
              v-model="formInputs[input.key]"
              style="width: 100%"
              :placeholder="input.placeholder || input.description"
            >
              <el-option
                v-for="opt in (input.options || [])"
                :key="typeof opt === 'string' ? opt : opt.value"
                :label="typeof opt === 'string' ? opt : opt.label"
                :value="typeof opt === 'string' ? opt : opt.value"
              />
            </el-select>
            <el-input v-else v-model="formInputs[input.key]" :placeholder="input.placeholder" />
          </el-form-item>
          <el-form-item label="宽高比">
            <el-radio-group v-model="aspectRatio">
              <el-radio-button value="16:9">16:9 横屏</el-radio-button>
              <el-radio-button value="9:16">9:16 竖屏</el-radio-button>
              <el-radio-button value="1:1">1:1 方形</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </div>
    </template>

    <!-- 步骤3：创建中 -->
    <template v-if="step === 3">
      <div class="launch-section creating">
        <el-icon class="creating-icon" :size="48"><Loading /></el-icon>
        <p class="creating-text">正在启动向导，请稍候...</p>
      </div>
    </template>

    <template #footer>
      <el-button v-if="step === 1" @click="visible = false">取消</el-button>
      <el-button v-if="step === 2" @click="step = 1">上一步</el-button>
      <el-button
        v-if="step === 2"
        type="primary"
        :loading="creating"
        :disabled="!projectTitle.trim()"
        @click="launch"
      >
        启动向导
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Film, Loading } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'

const props = defineProps<{
  modelValue: boolean
  /** 初始预选模板类别（从 WorkshopView 跳转时传入） */
  initialCategory?: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean)
  (e: 'created', projectId: number)
}>()

const projectStore = useProjectStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const step = ref(1)
const creating = ref(false)
const selectedCategory = ref<string>('')
const selectedTemplate = ref<any>(null)
const projectTitle = ref('')
const projectDescription = ref('')
const aspectRatio = ref('16:9')
const formInputs = ref<Record<string, any>>({})

// =====================================================
// 模板场景列表 — 与后端 wizard_chains.WIZARD_CHAINS 保持一致
// 4 种场景：短剧 / 广告 / 教育 / 动漫
// =====================================================
const templates = [
  {
    key: 'drama',
    name: '短剧创作',
    description: '输入故事主题，自动生成剧本/分镜/角色/视频',
    inputs_config: [
      { key: 'topic', label: '故事主题', type: 'text', required: true, default: '', placeholder: '例如：都市爱情故事' },
      { key: 'style', label: '画风', type: 'select', default: 'realistic', options: [
        { label: '写实', value: 'realistic' },
        { label: '动漫', value: 'anime' },
        { label: '水墨', value: 'ink' },
        { label: '赛博朋克', value: 'cyberpunk' },
      ] },
      { key: 'episodes', label: '集数', type: 'number', default: 1, min: 1, max: 10 },
      { key: 'duration_per_episode', label: '单集时长（秒）', type: 'number', default: 30, min: 10, max: 300 },
    ],
  },
  {
    key: 'ad',
    name: '广告创作',
    description: '输入产品信息，生成广告文案/配图/视频',
    inputs_config: [
      { key: 'product', label: '产品名', type: 'text', required: true, default: '', placeholder: '例如：新机型手机' },
      { key: 'selling_points', label: '卖点', type: 'text', required: true, default: '', placeholder: '例如：长续航、高清摄像' },
      { key: 'style', label: '广告风格', type: 'select', default: 'modern', options: [
        { label: '现代', value: 'modern' },
        { label: '复古', value: 'vintage' },
        { label: '科技', value: 'tech' },
        { label: '温馨', value: 'warm' },
      ] },
      { key: 'duration', label: '视频时长（秒）', type: 'number', default: 30, min: 10, max: 120 },
    ],
  },
  {
    key: 'education',
    name: '教学课件',
    description: '输入教学主题，生成课件内容/配图/讲解视频',
    inputs_config: [
      { key: 'topic', label: '教学主题', type: 'text', required: true, default: '', placeholder: '例如：Python 编程基础' },
      { key: 'grade', label: '目标年级', type: 'select', default: 'high_school', options: [
        { label: '小学', value: 'elementary' },
        { label: '初中', value: 'middle' },
        { label: '高中', value: 'high_school' },
        { label: '大学', value: 'college' },
      ] },
      { key: 'style', label: '课件风格', type: 'select', default: 'clean', options: [
        { label: '简洁', value: 'clean' },
        { label: '活泼', value: 'lively' },
      ] },
      { key: 'duration', label: '视频时长（分钟）', type: 'number', default: 5, min: 1, max: 30 },
    ],
  },
  {
    key: 'anime',
    name: '动漫创作',
    description: '输入主角设定，生成动漫剧本/分镜/视频',
    inputs_config: [
      { key: 'character', label: '主角设定', type: 'text', required: true, default: '', placeholder: '例如：少年剑客' },
      { key: 'style', label: '画风', type: 'select', default: 'anime', options: [
        { label: '日漫', value: 'anime' },
        { label: '国漫', value: 'guoman' },
        { label: '美漫', value: 'us_comic' },
      ] },
      { key: 'story', label: '故事背景', type: 'text', default: '', placeholder: '简短描述故事发生的背景' },
      { key: 'num_images', label: '图片数量', type: 'number', default: 8, min: 4, max: 30 },
    ],
  },
]

watch(visible, (v) => {
  if (v) {
    resetState()
    // 如果有初始类别，自动选中对应模板
    if (props.initialCategory) {
      const tpl = templates.find(t => t.key === props.initialCategory)
      if (tpl) selectTemplate(tpl)
    }
  }
})

function resetState() {
  step.value = 1
  creating.value = false
  selectedCategory.value = ''
  selectedTemplate.value = null
  projectTitle.value = ''
  projectDescription.value = ''
  aspectRatio.value = '16:9'
  formInputs.value = {}
}

function selectTemplate(tpl: any) {
  selectedCategory.value = tpl.key
  selectedTemplate.value = tpl
  // 用默认值填充 formInputs
  const inputs: Record<string, any> = {}
  ;(tpl.inputs_config || []).forEach((cfg: any) => {
    inputs[cfg.key] = cfg.default ?? (cfg.type === 'number' ? 1 : '')
  })
  formInputs.value = inputs
  projectTitle.value = tpl.name ? `${tpl.name} - ${new Date().toLocaleDateString()}` : '新项目'
  step.value = 2
}

async function launch() {
  if (!selectedTemplate.value || !projectTitle.value.trim()) return
  creating.value = true
  step.value = 3
  try {
    // ProjectLaunchDialog 中的 4 种场景对应 wizard_chains.WIZARD_CHAINS 预设链路，
    // 不依赖数据库 PipelineTemplate，因此使用 category 模式创建项目。
    const project = await projectStore.createWizardProject({
      category: selectedCategory.value,
      title: projectTitle.value.trim(),
      description: projectDescription.value.trim() || undefined,
      inputs: { ...formInputs.value },
      aspect_ratio: aspectRatio.value,
    })
    ElMessage.success('项目已创建，向导正在运行')
    visible.value = false
    emit('created', project.id)
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
    step.value = 2
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.launch-section { padding: 0 4px; }
.launch-desc { margin: 0 0 12px; color: var(--el-text-color-secondary); font-size: 14px; }
.template-list { display: flex; flex-direction: column; gap: 8px; }
.template-item {
  display: flex; gap: 12px; padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px; cursor: pointer; transition: all 0.2s;
}
.template-item:hover { border-color: var(--el-color-primary); background: var(--el-fill-color-light); }
.template-item.selected { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.template-thumb {
  width: 56px; height: 56px; display: flex; align-items: center; justify-content: center;
  background: var(--el-fill-color); border-radius: 4px; color: var(--el-color-primary);
}
.template-info { flex: 1; min-width: 0; }
.template-name { font-weight: 500; margin-bottom: 4px; }
.template-desc { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.5; }
.param-form { margin-top: 8px; }
.launch-section.creating { text-align: center; padding: 40px 0; }
.creating-icon { color: var(--el-color-primary); animation: rotating 2s linear infinite; }
.creating-text { margin-top: 16px; color: var(--el-text-color-secondary); }
@keyframes rotating { from { transform: rotate(0); } to { transform: rotate(360deg); } }
</style>
