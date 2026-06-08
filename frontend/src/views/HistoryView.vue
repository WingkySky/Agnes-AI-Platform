<!-- =====================================================
     历史记录视图 HistoryView
     - 筛选：全部 / 图片 / 视频
     - 分页加载
     - 点击卡片弹出详情（可预览、下载、删除）
     ===================================================== -->

<template>
  <div class="history-view">
    <h2 class="page-title">📜 生成历史</h2>
    <p class="page-desc">查看你在本平台生成过的所有图片与视频。可按类型筛选。</p>

    <!-- 筛选 Tab -->
    <div class="filter-wrap">
      <el-radio-group v-model="filterType" @change="loadList(true)">
        <el-radio-button value="all">全部 ({{ totalCount }})</el-radio-button>
        <el-radio-button value="image">图片 ({{ imageCount }})</el-radio-button>
        <el-radio-button value="video">视频 ({{ videoCount }})</el-radio-button>
      </el-radio-group>
      <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadList(true)">
        刷新
      </el-button>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && list.length === 0" class="loading-state">
      <el-icon :size="32" class="spinner"><Loading /></el-icon>
      <div>加载中...</div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="list.length === 0" class="empty-state">
      <el-icon :size="48"><Document /></el-icon>
      <p class="empty-text">暂无历史记录，去「图片生成」或「视频生成」页面试试吧～</p>
    </div>

    <!-- 卡片网格 -->
    <div v-else class="history-grid">
      <div
        v-for="item in list"
        :key="item.id"
        class="history-card"
        @click="showDetail(item)">
        <div class="card-preview">
          <img
            v-if="item.type === 'image'"
            :src="item.result_url"
            alt="history thumbnail"
            loading="lazy"
          />
          <video
            v-else-if="item.type === 'video'"
            :src="item.result_url"
            :poster="item.result_url"
            muted
            playsinline
            preload="metadata"
          />
          <div class="type-badge" :class="item.type">
            {{ item.type === 'image' ? '图片' : '视频' }}
          </div>
        </div>
        <div class="card-meta">
          <div class="card-prompt">{{ truncate(item.prompt, 80) }}</div>
          <div class="card-time">{{ formatTime(item.created_at) }}</div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="list.length > 0" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48, 100]"
        :total="totalCount"
        layout="total, sizes, prev, pager, next"
        background
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailItem ? (detailItem.type === 'image' ? '图片详情' : '视频详情') : '详情'"
      width="70%"
      top="5vh"
      destroy-on-close>
      <div v-if="detailItem" class="detail-content">
        <div class="detail-media">
          <img v-if="detailItem.type === 'image'" :src="detailItem.result_url" />
          <video v-else :src="detailItem.result_url" controls />
        </div>
        <div class="detail-info">
          <div class="info-row"><span class="label">提示词：</span><span>{{ detailItem.prompt }}</span></div>
          <div class="info-row"><span class="label">类型：</span><span>{{ detailItem.type === 'image' ? '图片' : '视频' }}</span></div>
          <div class="info-row" v-if="detailItem.model"><span class="label">模型：</span><span>{{ detailItem.model }}</span></div>
          <div class="info-row"><span class="label">状态：</span><span>{{ detailItem.status || 'success' }}</span></div>
          <div class="info-row"><span class="label">创建时间：</span><span>{{ detailItem.created_at }}</span></div>
          <div class="info-row"><span class="label">链接：</span><el-button link type="primary" @click="copyLink(detailItem.result_url)">复制链接</el-button></div>
          <div class="info-row"><span class="label"></span><el-button link type="primary" @click="downloadDetail">下载</el-button></div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="danger" :icon="Delete" @click="confirmDelete">删除此记录</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteVisible"
      title="确认删除"
      width="400px">
      <div>确定要删除这条记录吗？此操作不可撤销。</div>
      <template #footer>
        <el-button @click="deleteVisible = false">取消</el-button>
        <el-button type="danger" @click="doDelete">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Loading, Document, Delete } from '@element-plus/icons-vue'
import { getHistoryList, deleteHistoryRecord } from '@/api/history'

const list = ref([])
const loading = ref(false)
const totalCount = ref(0)
const imageCount = ref(0)
const videoCount = ref(0)
const page = ref(1)
const pageSize = ref(12)
const filterType = ref('all')

const detailVisible = ref(false)
const deleteVisible = ref(false)
const detailItem = ref(null)

// ---------- 加载列表 ----------
async function loadList(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const data = await getHistoryList({
      type: filterType.value,
      page: page.value,
      page_size: pageSize.value
    })
    list.value = data.items || []
    totalCount.value = data.total || list.value.length
    imageCount.value = list.value.filter(i => i.type === 'image').length
    videoCount.value = list.value.filter(i => i.type === 'video').length
  } catch (e) {
    // 已由 axios 拦截器弹出错误
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  page.value = p
  loadList()
}
function handleSizeChange(size) {
  pageSize.value = size
  page.value = 1
  loadList()
}

// ---------- 详情操作 ----------
function showDetail(item) {
  detailItem.value = item
  detailVisible.value = true
}
function copyLink(url) {
  if (!url) return
  navigator.clipboard?.writeText(url)
    .then(() => ElMessage.success('链接已复制'))
    .catch(() => {
      const ta = document.createElement('textarea')
      ta.value = url
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      ElMessage.success('链接已复制')
    })
}
function downloadDetail() {
  if (!detailItem.value?.result_url) return
  const a = document.createElement('a')
  a.href = detailItem.value.result_url
  a.download = `agnes-${detailItem.value.type}-${detailItem.value.id}`
  a.target = '_blank'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function confirmDelete() {
  deleteVisible.value = true
}
async function doDelete() {
  if (!detailItem.value) return
  try {
    await deleteHistoryRecord(detailItem.value.id)
    ElMessage.success('已删除')
    deleteVisible.value = false
    detailVisible.value = false
    loadList()
  } catch (e) {
    // 错误已在拦截器弹出
  }
}

// ---------- 工具函数 ----------
function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return String(t).slice(0, 19)
  return d.toLocaleString()
}

onMounted(() => loadList())
</script>

<style scoped>
.history-view { color: #e8eef7; }

.filter-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: rgba(15, 24, 42, 0.5);
  border-radius: 10px;
  border: 1px solid rgba(120, 170, 255, 0.15);
}

.loading-state, .empty-state {
  padding: 80px 20px;
  text-align: center;
  color: #6b84aa;
}
.spinner { animation: spin 1.2s linear infinite; color: #6b9cff; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-text { margin-top: 16px; font-size: 14px; }

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}
.history-card {
  background: rgba(15, 24, 42, 0.7);
  border: 1px solid rgba(120, 170, 255, 0.15);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
}
.history-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 32px rgba(100, 150, 255, 0.25);
  border-color: rgba(120, 170, 255, 0.4);
}
.card-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4/3;
  background: #0a1220;
  overflow: hidden;
}
.card-preview img,
.card-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.type-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(15, 24, 42, 0.75);
  backdrop-filter: blur(4px);
}
.type-badge.image { color: #8bb4ff; border: 1px solid rgba(139, 180, 255, 0.5); }
.type-badge.video { color: #c4a7ff; border: 1px solid rgba(196, 167, 255, 0.5); }
.card-meta { padding: 12px 14px; }
.card-prompt {
  font-size: 13px;
  color: #d5e3f7;
  line-height: 1.5;
  min-height: 40px;
  overflow: hidden;
}
.card-time {
  margin-top: 8px;
  font-size: 12px;
  color: #6b84aa;
}

.pagination-wrap {
  margin-top: 24px;
  text-align: center;
}

/* 详情弹窗 */
.detail-content { display: flex; gap: 24px; flex-direction: column; align-items: center; }
.detail-media { width: 100%; text-align: center; }
.detail-media img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 10px;
  object-fit: contain;
}
.detail-media video {
  max-width: 100%;
  max-height: 400px;
  border-radius: 10px;
  background: #000;
}
.detail-info {
  width: 100%;
  background: rgba(15, 24, 42, 0.5);
  padding: 16px;
  border-radius: 10px;
}
.info-row { padding: 6px 0; font-size: 13px; line-height: 1.6; color: #d5e3f7; }
.label { color: #8ba3c9; margin-right: 8px; font-weight: 500; }
</style>
