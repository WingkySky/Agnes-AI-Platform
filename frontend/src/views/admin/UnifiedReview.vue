<!-- =====================================================
     统一审核管理页 - UnifiedReview
     - 聚合：作品审核、预设审核、模板审核（替代旧 ModerationView + PresetAudit）
     - Tab 切换类型 + 状态筛选 + 作品子类型筛选（image/video）
     - 关键词 / 内容 ID / 创作者用户名 / AI 预审结果 多维搜索
     - 列表（含缩略图、AI 预审结果 Tag、命中敏感词、点赞浏览、作者信息）
     - 详情预览（图片/视频播放 + AI 审核结果高亮卡片）
     - 通过/驳回 + 批量操作 + 一键通过/一键驳回当前筛选条件下全部作品
     - 30s 自动轮询 + 手动刷新 + 最后更新时间显示，让管理员实时感知 AI 审核结果
     ===================================================== -->

<template>
  <div class="unified-review">
    <!-- 头部 -->
    <div class="review-header">
      <h2 class="review-title">{{ t('admin.review.title') }}</h2>
      <div class="header-actions">
        <!-- 最后更新时间 -->
        <span v-if="lastUpdated" class="last-updated">
          <el-icon size="12"><Clock /></el-icon>
          {{ t('admin.review.lastUpdated') }}: {{ formatTime(lastUpdated) }}
        </span>
        <!-- 自动刷新开关 -->
        <el-tooltip :content="t('admin.review.autoRefreshTip')" placement="top">
          <el-switch
            v-model="autoRefresh"
            size="small"
            inline-prompt
            :active-text="t('admin.review.autoRefreshOn')"
            :inactive-text="t('admin.review.autoRefreshOff')" />
        </el-tooltip>
        <el-button :loading="loading" @click="loadList">
          <el-icon><Refresh /></el-icon>
          {{ t('common.refresh') }}
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="3">
        <el-card class="stat-card" shadow="hover" @click="switchType('all')">
          <div class="stat-num">{{ stats.total_pending || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.stats.total') }}</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card class="stat-card stat-work" shadow="hover" @click="switchType('work')">
          <div class="stat-num">{{ stats.work_pending || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.types.work') }}</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card class="stat-card stat-preset" shadow="hover" @click="switchType('preset')">
          <div class="stat-num">{{ stats.preset_pending || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.types.preset') }}</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card class="stat-card stat-template" shadow="hover" @click="switchType('template')">
          <div class="stat-num">{{ stats.template_pending || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.types.template') }}</div>
        </el-card>
      </el-col>
      <!-- 模板修订待审核数 -->
      <el-col :span="3">
        <el-card class="stat-card stat-template-revision" shadow="hover" @click="switchType('template_revision')">
          <div class="stat-num">{{ stats.template_revision_pending || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.types.templateRevision') }}</div>
        </el-card>
      </el-col>
      <!-- AI 预审通过，待人工复审 -->
      <el-col :span="3">
        <el-card class="stat-card stat-ai-passed" shadow="hover" @click="quickFilterAi('passed')">
          <div class="stat-num">{{ stats.ai_passed_pending || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.stats.aiPassedPending') }}</div>
        </el-card>
      </el-col>
      <!-- AI 判违规 -->
      <el-col :span="3">
        <el-card class="stat-card stat-ai-violated" shadow="hover" @click="quickFilterAi('violated')">
          <div class="stat-num">{{ stats.ai_violated || 0 }}</div>
          <div class="stat-label">{{ t('admin.review.stats.aiViolated') }}</div>
        </el-card>
      </el-col>
      <!-- 右侧留白占位（保持 24 栅格对齐） -->
      <el-col :span="3" class="stat-spacer" />
    </el-row>

    <!-- 筛选区 -->
    <el-card class="filter-card" shadow="never">
      <!-- 类型 Tab -->
      <el-tabs v-model="filters.review_type" class="type-tabs" @tab-change="onTypeChange">
        <el-tab-pane :label="t('admin.review.types.all')" name="all" />
        <el-tab-pane :label="t('admin.review.types.work')" name="work" />
        <el-tab-pane :label="t('admin.review.types.preset')" name="preset" />
        <el-tab-pane :label="t('admin.review.types.template')" name="template" />
        <!-- 模板修订：公开已审核模板被编辑后产生的 revision 草稿 -->
        <el-tab-pane :label="t('admin.review.types.templateRevision')" name="template_revision" />
      </el-tabs>

      <!-- 待审核状态下显示一键操作快捷条 -->
      <div v-if="filters.status === 'pending'" class="quick-actions">
        <span class="quick-label">
          <el-icon size="14" color="#e6a23c"><Warning /></el-icon>
          {{ t('admin.review.pendingTip', { count: total }) }}
        </span>
        <el-button
          type="success"
          size="small"
          :disabled="total === 0 || loading"
          :loading="quickLoading"
          @click="onQuickApproveAll">
          <el-icon><Check /></el-icon>
          {{ t('admin.review.quickApprove') }}
        </el-button>
        <el-button
          type="danger"
          size="small"
          :disabled="total === 0 || loading"
          :loading="quickLoading"
          @click="onQuickRejectAll">
          <el-icon><Close /></el-icon>
          {{ t('admin.review.quickReject') }}
        </el-button>
      </div>

      <!-- 筛选条件表单 -->
      <el-form :inline="true" :model="filters" class="filter-form">
        <div class="filter-grid">
          <!-- 状态筛选 -->
          <el-form-item :label="t('admin.review.status')" class="filter-item">
            <el-select v-model="filters.status" class="filter-control" @change="loadList(1)">
              <el-option :label="t('admin.review.statusAll')" value="all" />
              <el-option :label="t('admin.review.statusPending')" value="pending" />
              <el-option :label="t('admin.review.statusApproved')" value="approved" />
              <el-option :label="t('admin.review.statusRejected')" value="rejected" />
            </el-select>
          </el-form-item>

          <!-- 作品子类型筛选（仅 all/work 类型时显示） -->
          <el-form-item
            v-if="filters.review_type === 'all' || filters.review_type === 'work'"
            :label="t('admin.review.workType')"
            class="filter-item">
            <el-select v-model="filters.work_type" class="filter-control filter-control-sm" @change="loadList(1)">
              <el-option :label="t('admin.review.filterAll')" value="" />
              <el-option :label="t('admin.review.filterImage')" value="image" />
              <el-option :label="t('admin.review.filterVideo')" value="video" />
            </el-select>
          </el-form-item>

          <!-- AI 预审结果筛选（仅 all/work 类型时显示） -->
          <el-form-item
            v-if="filters.review_type === 'all' || filters.review_type === 'work'"
            :label="t('admin.review.aiStatus')"
            class="filter-item">
            <el-select v-model="filters.ai_status" class="filter-control" @change="loadList(1)">
              <el-option :label="t('admin.review.filterAll')" value="" />
              <el-option :label="t('admin.review.aiStatusPending')" value="pending" />
              <el-option :label="t('admin.review.aiStatusPassed')" value="passed" />
              <el-option :label="t('admin.review.aiStatusViolated')" value="violated" />
              <el-option :label="t('admin.review.aiStatusFailed')" value="failed" />
              <el-option :label="t('admin.review.aiStatusNone')" value="none" />
            </el-select>
          </el-form-item>

          <!-- 内容 ID 搜索 -->
          <el-form-item :label="t('admin.review.contentId')" class="filter-item">
            <el-input
              v-model="itemIdInput"
              :placeholder="t('admin.review.contentIdPlaceholder')"
              class="filter-control filter-control-sm"
              clearable
              @keyup.enter="onSearch"
              @clear="onSearch" />
          </el-form-item>

          <!-- 创作者用户名搜索 -->
          <el-form-item :label="t('admin.review.creator')" class="filter-item">
            <el-input
              v-model="filters.username"
              :placeholder="t('admin.review.creatorPlaceholder')"
              class="filter-control"
              clearable
              @keyup.enter="onSearch"
              @clear="onSearch" />
          </el-form-item>
        </div>

        <!-- 关键词搜索行 -->
        <div class="filter-search-row">
          <!-- 关键词搜索 -->
          <el-form-item :label="t('admin.review.keyword')" class="filter-item filter-item-keyword">
            <el-input
              v-model="filters.keyword"
              :placeholder="t('admin.review.keywordPlaceholder')"
              class="filter-control filter-control-keyword"
              clearable
              @keyup.enter="onSearch"
              @clear="onSearch">
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item class="filter-item filter-item-search-btn">
            <el-button type="primary" @click="onSearch">
              <el-icon><Search /></el-icon>
              {{ t('common.search') }}
            </el-button>
          </el-form-item>
        </div>
      </el-form>
    </el-card>

    <!-- 批量操作 -->
    <div v-if="selectedIds.length > 0" class="batch-bar">
      <span class="batch-info">
        {{ t('admin.review.selectedCount', { count: selectedIds.length }) }}
      </span>
      <el-button size="small" type="success" :loading="batchLoading" @click="handleBatchApprove">
        <el-icon><Check /></el-icon>
        {{ t('admin.review.batchApprove') }}
      </el-button>
      <el-button size="small" type="danger" :loading="batchLoading" @click="handleBatchReject">
        <el-icon><Close /></el-icon>
        {{ t('admin.review.batchReject') }}
      </el-button>
      <el-button size="small" link @click="clearSelection">{{ t('common.clear') }}</el-button>
    </div>

    <!-- 列表 -->
    <el-card class="list-card" shadow="never">
      <el-table
        :data="list"
        v-loading="loading"
        stripe
        @selection-change="onSelectionChange"
        :empty-text="t('admin.review.empty')">
        <el-table-column type="selection" width="48" />
        <!-- 内容 ID -->
        <el-table-column :label="t('admin.review.colItemId')" width="90" align="center">
          <template #default="{ row }">
            <span class="muted">{{ row.item_id }}</span>
          </template>
        </el-table-column>
        <!-- 类型 -->
        <el-table-column :label="t('admin.review.colType')" width="100">
          <template #default="{ row }">
            <div class="type-cell">
              <el-tag size="small" :type="getTypeTagType(row.review_type)">
                {{ t(`admin.review.types.${row.review_type}`) }}
              </el-tag>
              <el-tag
                v-if="row.review_type === 'work' && row.work_type"
                size="small"
                :type="row.work_type === 'image' ? 'primary' : 'warning'"
                effect="plain"
                style="margin-left: 4px">
                {{ row.work_type === 'image' ? t('admin.review.filterImage') : t('admin.review.filterVideo') }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <!-- 预览（作品类型显示缩略图） -->
        <el-table-column
          v-if="filters.review_type === 'all' || filters.review_type === 'work' || filters.review_type === 'template_revision'"
          :label="t('admin.review.colPreview')"
          width="90"
          align="center">
          <template #default="{ row }">
            <div v-if="row.review_type === 'work' && row.result_url" class="preview-cell" @click="handleView(row)">
              <el-image
                v-if="row.work_type === 'image'"
                :src="row.result_url"
                :preview-src-list="[row.result_url]"
                fit="cover"
                style="width: 56px; height: 56px; border-radius: 6px; cursor: pointer"
                :preview-teleported="true" />
              <div v-else class="video-preview">
                <el-image
                  :src="row.thumbnail_url"
                  fit="cover"
                  style="width: 56px; height: 56px; border-radius: 6px" />
                <el-icon class="play-icon"><VideoPlay /></el-icon>
              </div>
            </div>
            <el-image
              v-else-if="(row.review_type === 'template' || row.review_type === 'preset') && row.thumbnail_url"
              :src="row.thumbnail_url"
              fit="cover"
              style="width: 56px; height: 56px; border-radius: 6px; cursor: pointer"
              @click="handleView(row)" />
            <!-- 模板修订：显示原模板缩略图 -->
            <el-image
              v-else-if="row.review_type === 'template_revision' && (row.template_thumbnail_url || row.thumbnail_url)"
              :src="row.template_thumbnail_url || row.thumbnail_url"
              fit="cover"
              style="width: 56px; height: 56px; border-radius: 6px; cursor: pointer"
              @click="handleView(row)" />
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <!-- 名称 -->
        <el-table-column :label="t('admin.review.colName')" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tooltip
              v-if="row.review_type === 'work' && row.prompt"
              :content="row.prompt"
              placement="top"
              :show-after="300">
              <span class="prompt-text">{{ truncatePrompt(row.prompt) }}</span>
            </el-tooltip>
            <!-- 模板修订：显示原模板名 + 修订描述 tooltip -->
            <el-tooltip
              v-else-if="row.review_type === 'template_revision'"
              :content="row.description || t('admin.review.noDescription')"
              placement="top"
              :show-after="300">
              <span class="prompt-text">{{ row.template_name || row.name || '-' }}</span>
            </el-tooltip>
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 模板修订：提交说明列（仅 template_revision 类型显示） -->
        <el-table-column
          v-if="filters.review_type === 'template_revision'"
          :label="t('admin.review.colSubmitReason')"
          min-width="180"
          show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.submit_reason" class="prompt-text">{{ row.submit_reason }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <!-- 分类 -->
        <el-table-column :label="t('admin.review.colCategory')" width="100">
          <template #default="{ row }">
            {{ row.category || (row.preset_type) || '-' }}
          </template>
        </el-table-column>
        <!-- 创作者 -->
        <el-table-column :label="t('admin.review.colCreator')" width="140" align="center">
          <template #default="{ row }">
            <div class="author-cell">
              <span class="author-name">{{ row.nickname || row.username || t('admin.review.anonymous') }}</span>
              <span v-if="row.user_id" class="author-id muted">ID: {{ row.user_id }}</span>
            </div>
          </template>
        </el-table-column>
        <!-- 状态 -->
        <el-table-column :label="t('admin.review.colStatus')" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="getStatusTagType(row.status)">
              {{ t(`admin.review.statusLabels.${row.status}`) }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- AI 预审结果（仅作品类型显示） -->
        <el-table-column
          v-if="filters.review_type === 'all' || filters.review_type === 'work'"
          :label="t('admin.review.colAiStatus')"
          width="110"
          align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.review_type === 'work' && row.ai_moderation_status"
              size="small"
              :type="getAiStatusTagType(row.ai_moderation_status)"
              effect="dark">
              {{ t(`admin.review.aiStatusLabels.${row.ai_moderation_status}`) }}
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <!-- 命中敏感词（仅作品类型显示） -->
        <el-table-column
          v-if="filters.review_type === 'all' || filters.review_type === 'work'"
          :label="t('admin.review.colHitWords')"
          min-width="150">
          <template #default="{ row }">
            <div v-if="row.review_type === 'work' && row.moderation_flags && row.moderation_flags.length > 0" class="flags-wrap">
              <el-tag
                v-for="flag in row.moderation_flags"
                :key="flag"
                type="danger"
                size="small"
                effect="light"
                style="margin-right: 4px; margin-bottom: 4px">
                {{ flag }}
              </el-tag>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <!-- 点赞/浏览（仅作品类型显示） -->
        <el-table-column
          v-if="filters.review_type === 'all' || filters.review_type === 'work'"
          :label="t('admin.review.colLikesViews')"
          width="120"
          align="center">
          <template #default="{ row }">
            <div v-if="row.review_type === 'work'" class="stats-text">
              <span>{{ row.likes_count || 0 }} {{ t('admin.review.likes') }}</span>
              <span class="muted">/</span>
              <span>{{ row.views_count || 0 }} {{ t('admin.review.views') }}</span>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <!-- 提交时间 -->
        <el-table-column :label="t('admin.review.colSubmitTime')" width="170">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at || row.submitted_at) }}</span>
          </template>
        </el-table-column>
        <!-- 操作 -->
        <el-table-column :label="t('common.actions')" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="handleView(row)">
              {{ t('common.view') }}
            </el-button>
            <!-- 已驳回的可再通过（与旧 ModerationView 行为一致，允许审核状态回退） -->
            <el-button
              v-if="row.status !== 'approved'"
              size="small"
              link
              type="success"
              @click="handleApprove(row)">
              {{ t('admin.review.approve') }}
            </el-button>
            <!-- 已通过的可再驳回（与旧 ModerationView 行为一致，允许审核状态回退） -->
            <el-button
              v-if="row.status !== 'rejected'"
              size="small"
              link
              type="danger"
              @click="handleReject(row)">
              {{ t('admin.review.reject') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="filters.page"
          v-model:page-size="filters.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="loadList(1)"
          @current-change="loadList()" />
      </div>
    </el-card>

    <!-- 详情预览弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="t('admin.review.detailTitle')"
      width="720px"
      destroy-on-close>
      <template v-if="currentItem">
        <!-- AI 预审结果高亮卡片（仅作品类型） -->
        <div
          v-if="currentItem.review_type === 'work' && currentItem.ai_moderation_status"
          class="ai-result-card"
          :class="`ai-result-${currentItem.ai_moderation_status}`">
          <div class="ai-result-header">
            <el-icon size="16"><MagicStick /></el-icon>
            <span class="ai-result-title">{{ t('admin.review.aiResultCardTitle') }}</span>
            <el-tag
              size="small"
              :type="getAiStatusTagType(currentItem.ai_moderation_status)"
              effect="dark"
              style="margin-left: 8px">
              {{ t(`admin.review.aiStatusLabels.${currentItem.ai_moderation_status}`) }}
            </el-tag>
          </div>
          <div v-if="currentItem.moderation_reason" class="ai-result-reason">
            {{ currentItem.moderation_reason }}
          </div>
        </div>

        <!-- 作品类型：图片/视频播放器 -->
        <div v-if="currentItem.review_type === 'work' && currentItem.result_url" class="detail-media">
          <el-image
            v-if="currentItem.work_type === 'image'"
            :src="currentItem.result_url"
            fit="contain"
            style="width: 100%; max-height: 400px"
            preview-teleported />
          <video
            v-else
            :src="currentItem.result_url"
            :poster="currentItem.work_type === 'video' && currentItem.item_id ? `/api/history/video/${currentItem.item_id}/thumbnail` : ''"
            controls
            style="width: 100%; max-height: 400px" />
        </div>
        <!-- 模板/预设类型：缩略图 -->
        <div v-else-if="currentItem.thumbnail_url" class="detail-thumb">
          <el-image
            :src="currentItem.thumbnail_url"
            fit="contain"
            style="max-height: 300px"
            preview-teleported />
        </div>
        <!-- 模板修订：原模板缩略图（优先 template_thumbnail_url） -->
        <div
          v-else-if="currentItem.review_type === 'template_revision' && (currentItem.template_thumbnail_url || currentItem.thumbnail_url)"
          class="detail-thumb">
          <el-image
            :src="currentItem.template_thumbnail_url || currentItem.thumbnail_url"
            fit="contain"
            style="max-height: 300px"
            preview-teleported />
        </div>

        <el-descriptions :column="2" border style="margin-top: 16px">
          <el-descriptions-item :label="t('admin.review.colItemId')">
            {{ currentItem.item_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.review.colType')">
            <el-tag size="small" :type="getTypeTagType(currentItem.review_type)">
              {{ t(`admin.review.types.${currentItem.review_type}`) }}
            </el-tag>
            <el-tag
              v-if="currentItem.review_type === 'work' && currentItem.work_type"
              size="small"
              :type="currentItem.work_type === 'image' ? 'primary' : 'warning'"
              effect="plain"
              style="margin-left: 4px">
              {{ currentItem.work_type === 'image' ? t('admin.review.filterImage') : t('admin.review.filterVideo') }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.review.colStatus')">
            <el-tag size="small" :type="getStatusTagType(currentItem.status)">
              {{ t(`admin.review.statusLabels.${currentItem.status}`) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.review.colCreator')">
            {{ currentItem.nickname || currentItem.username || t('admin.review.anonymous') }}
            <span v-if="currentItem.user_id" class="muted">(ID: {{ currentItem.user_id }})</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="currentItem.review_type === 'work'" :label="t('admin.review.colModel')" :span="2">
            {{ currentItem.model || '-' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentItem.review_type === 'work'" :label="t('admin.review.colLikesViews')" :span="2">
            {{ currentItem.likes_count || 0 }} / {{ currentItem.views_count || 0 }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.review.colCategory')">
            {{ currentItem.category || currentItem.preset_type || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.review.colSubmitTime')">
            {{ formatTime(currentItem.created_at || currentItem.submitted_at) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentItem.review_type === 'work' && currentItem.prompt" :label="t('admin.review.colPrompt')" :span="2">
            <div class="desc-text">{{ currentItem.prompt }}</div>
          </el-descriptions-item>
          <el-descriptions-item v-else-if="currentItem.description" :label="t('admin.review.colDescription')" :span="2">
            <div class="desc-text">{{ currentItem.description }}</div>
          </el-descriptions-item>
          <el-descriptions-item v-if="currentItem.submit_reason" :label="t('admin.review.colSubmitReason')" :span="2">
            <div class="desc-text">{{ currentItem.submit_reason }}</div>
          </el-descriptions-item>
          <el-descriptions-item
            v-if="currentItem.review_type === 'work' && currentItem.moderation_flags && currentItem.moderation_flags.length > 0"
            :label="t('admin.review.colHitWords')"
            :span="2">
            <div class="flags-wrap">
              <el-tag
                v-for="flag in currentItem.moderation_flags"
                :key="flag"
                type="danger"
                size="small"
                effect="light"
                style="margin-right: 4px">
                {{ flag }}
              </el-tag>
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 模板修订专属字段：展示修订后的新值 -->
        <template v-if="currentItem.review_type === 'template_revision'">
          <div class="revision-section-title">{{ t('admin.review.templateRevisionFields.title') }}</div>
          <el-descriptions :column="2" border>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.templateId')">
              {{ currentItem.template_id ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.templateKey')">
              {{ currentItem.template_key || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.templateName')" :span="2">
              {{ currentItem.template_name || currentItem.name || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.newName')">
              {{ currentItem.name || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.newCategory')">
              {{ currentItem.category || '-' }}
            </el-descriptions-item>
            <el-descriptions-item v-if="currentItem.tags && currentItem.tags.length > 0" :label="t('admin.review.templateRevisionFields.newTags')" :span="2">
              <el-tag
                v-for="tag in currentItem.tags"
                :key="tag"
                size="small"
                effect="plain"
                style="margin-right: 4px; margin-bottom: 4px">
                {{ tag }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.inputsCount')">
              {{ Array.isArray(currentItem.inputs_config) ? currentItem.inputs_config.length : 0 }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.review.templateRevisionFields.stepsCount')">
              {{ Array.isArray(currentItem.steps_config) ? currentItem.steps_config.length : 0 }}
            </el-descriptions-item>
            <el-descriptions-item v-if="currentItem.estimated_credits != null" :label="t('admin.review.templateRevisionFields.estimatedCredits')">
              {{ currentItem.estimated_credits }}
            </el-descriptions-item>
            <el-descriptions-item v-if="currentItem.estimated_time_minutes != null" :label="t('admin.review.templateRevisionFields.estimatedTime')">
              {{ currentItem.estimated_time_minutes }}
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">{{ t('common.close') }}</el-button>
        <template v-if="currentItem">
          <el-button
            v-if="currentItem.status !== 'approved'"
            type="success"
            @click="detailVisible = false; handleApprove(currentItem)">
            {{ t('admin.review.approve') }}
          </el-button>
          <el-button
            v-if="currentItem.status !== 'rejected'"
            type="danger"
            @click="openRejectDialog(currentItem)">
            {{ t('admin.review.reject') }}
          </el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 驳回理由弹窗 -->
    <el-dialog v-model="rejectVisible" :title="t('admin.review.rejectTitle')" width="480px">
      <el-form :model="rejectForm">
        <el-form-item :label="t('admin.review.rejectReason')">
          <el-input
            v-model="rejectForm.reason"
            type="textarea"
            :rows="4"
            :placeholder="t('admin.review.rejectReasonPlaceholder')"
            maxlength="500"
            show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="rejectLoading" @click="confirmReject">
          {{ t('admin.review.confirmReject') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, Check, Close, Warning, VideoPlay, Clock, MagicStick } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import client from '@/api/client'

const { t } = useI18n()

interface ReviewItem {
  id: string | number
  review_type: 'work' | 'preset' | 'template' | 'template_revision'
  item_id: number
  name?: string
  description?: string
  prompt?: string
  category?: string
  preset_type?: string
  user_id?: number
  username?: string | null
  nickname?: string | null
  author?: string
  status: 'pending' | 'approved' | 'rejected' | 'private'
  created_at?: string
  submitted_at?: string
  thumbnail_url?: string
  cover_url?: string
  result_url?: string
  work_type?: 'image' | 'video'
  model?: string
  submit_reason?: string
  reject_reason?: string
  moderation_reason?: string | null
  moderation_flags?: string[]
  moderated_at?: string | null
  public_shared_at?: string | null
  likes_count?: number
  views_count?: number
  is_public?: boolean
  tags?: string[]
  estimated_credits?: number
  estimated_time_minutes?: number
  // template_revision 专属字段
  template_id?: number
  template_name?: string
  template_key?: string
  template_thumbnail_url?: string
  reviewed_at?: string | null
  // AI 预审状态：null / pending / passed / violated / failed
  ai_moderation_status?: 'pending' | 'passed' | 'violated' | 'failed' | null
  [key: string]: any
}

// ---- 状态 ----
const loading = ref(false)
const batchLoading = ref(false)
const quickLoading = ref(false)
const rejectLoading = ref(false)
const list = ref<ReviewItem[]>([])
const total = ref(0)
const stats = reactive<Record<string, number>>({
  work_pending: 0,
  preset_pending: 0,
  template_pending: 0,
  template_revision_pending: 0,
  total_pending: 0,
  ai_passed_pending: 0,
  ai_violated: 0,
  ai_failed: 0,
  ai_pending: 0,
})
const selectedIds = ref<ReviewItem[]>([])

// 最后更新时间（用于展示）
const lastUpdated = ref<string>('')

// 自动刷新开关（默认开启，30s 轮询）
const autoRefresh = ref(true)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const filters = reactive({
  review_type: 'all',
  status: 'pending',
  keyword: '',
  username: '',
  work_type: '',
  ai_status: '',
  item_id: undefined as number | undefined,
  page: 1,
  page_size: 20,
})

// 内容 ID 输入独立维护（避免输入过程中触发类型转换）
const itemIdInput = ref<string>('')

// 详情相关
const detailVisible = ref(false)
const currentItem = ref<ReviewItem | null>(null)

// 驳回相关
const rejectVisible = ref(false)
const rejectItem = ref<ReviewItem | null>(null)
const rejectForm = reactive({ reason: '' })

// ---- 自动刷新定时器 ----
function startAutoRefresh() {
  if (refreshTimer) return
  refreshTimer = setInterval(() => {
    // 静默刷新（不显示 loading，不打断用户操作）
    silentRefresh()
  }, 30000) // 30s
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

watch(autoRefresh, (val) => {
  if (val) startAutoRefresh()
  else stopAutoRefresh()
})

// ---- 方法 ----
function switchType(type: string) {
  filters.review_type = type
  loadList(1)
}

function onTypeChange() {
  // 切换类型时重置作品相关筛选（避免不可用场景下还带着参数）
  filters.work_type = ''
  filters.ai_status = ''
  loadList(1)
}

// 点击 AI 统计卡片：快速跳转到对应筛选
function quickFilterAi(status: 'passed' | 'violated') {
  filters.review_type = 'work'
  filters.status = status === 'violated' ? 'rejected' : 'pending'
  filters.ai_status = status
  loadList(1)
}

function onSearch() {
  // 将输入的内容 ID 转换为数字
  const v = itemIdInput.value.trim()
  if (v) {
    const n = parseInt(v)
    if (!isNaN(n)) {
      filters.item_id = n
    } else {
      filters.item_id = undefined
    }
  } else {
    filters.item_id = undefined
  }
  loadList(1)
}

async function loadList(page?: number) {
  if (page != null) filters.page = page
  loading.value = true
  try {
    // 构造请求参数（移除空值）
    const params: Record<string, any> = {
      review_type: filters.review_type,
      status: filters.status,
      page: filters.page,
      page_size: filters.page_size,
    }
    if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
    if (filters.username.trim()) params.username = filters.username.trim()
    if (filters.work_type) params.work_type = filters.work_type
    if (filters.ai_status) params.ai_status = filters.ai_status
    if (filters.item_id != null) params.item_id = filters.item_id

    const res = await client.get('/api/admin/review/list', { params })
    list.value = res.items
    total.value = res.total
    selectedIds.value = []
    lastUpdated.value = new Date().toISOString()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('admin.review.loadFailed'))
  } finally {
    loading.value = false
  }
}

// 静默刷新（不打断用户操作，不显示 loading、不显示错误）
async function silentRefresh() {
  try {
    const params: Record<string, any> = {
      review_type: filters.review_type,
      status: filters.status,
      page: filters.page,
      page_size: filters.page_size,
    }
    if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
    if (filters.username.trim()) params.username = filters.username.trim()
    if (filters.work_type) params.work_type = filters.work_type
    if (filters.ai_status) params.ai_status = filters.ai_status
    if (filters.item_id != null) params.item_id = filters.item_id

    const res = await client.get('/api/admin/review/list', { params })
    list.value = res.items
    total.value = res.total
    lastUpdated.value = new Date().toISOString()
    // 同步刷新统计
    loadStats()
  } catch {
    // 静默失败
  }
}

async function loadStats() {
  try {
    const res = await client.get('/api/admin/review/stats')
    Object.assign(stats, res)
  } catch (e: any) {
    // 静默失败
  }
}

function onSelectionChange(rows: ReviewItem[]) {
  // 允许跨状态批量选择（与旧 ModerationView 行为一致）
  selectedIds.value = rows
}

function clearSelection() {
  selectedIds.value = []
  loadList()
}

function getTypeTagType(type: string): 'primary' | 'success' | 'warning' | 'info' {
  const map: Record<string, any> = {
    work: 'primary',
    preset: 'warning',
    template: 'success',
    // 模板修订：使用 info 与 template 区分
    template_revision: 'info',
  }
  return map[type] || 'info'
}

function getStatusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, any> = {
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    private: 'info',
  }
  return map[status] || 'info'
}

// AI 预审状态对应 Tag 类型
function getAiStatusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, any> = {
    pending: 'primary',     // 审核中（蓝色）
    passed: 'success',      // 通过（绿色）
    violated: 'danger',     // 违规（红色）
    failed: 'warning',      // 失败（橙色）
  }
  return map[status] || 'info'
}

function formatTime(isoStr?: string | null): string {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return isoStr
  }
}

function truncatePrompt(prompt?: string): string {
  if (!prompt) return ''
  return prompt.length > 60 ? prompt.slice(0, 60) + '...' : prompt
}

// ---- 操作 ----
function handleView(row: ReviewItem) {
  currentItem.value = row
  detailVisible.value = true
}

async function handleApprove(row: ReviewItem) {
  try {
    await ElMessageBox.confirm(
      t('admin.review.approveConfirm', { name: row.name || `#${row.item_id}` }),
      t('admin.review.approve'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await client.post(`/api/admin/review/${row.review_type}/${row.item_id}/approve`)
    ElMessage.success(t('admin.review.approveSuccess'))
    await Promise.all([loadList(), loadStats()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('admin.review.operateFailed'))
  }
}

function openRejectDialog(row: ReviewItem) {
  rejectItem.value = row
  rejectForm.reason = ''
  rejectVisible.value = true
}

async function handleReject(row: ReviewItem) {
  openRejectDialog(row)
}

async function confirmReject() {
  if (!rejectItem.value) return
  rejectLoading.value = true
  try {
    await client.post(`/api/admin/review/${rejectItem.value.review_type}/${rejectItem.value.item_id}/reject`, {
      reason: rejectForm.reason,
    })
    ElMessage.success(t('admin.review.rejectSuccess'))
    rejectVisible.value = false
    await Promise.all([loadList(), loadStats()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('admin.review.operateFailed'))
  } finally {
    rejectLoading.value = false
  }
}

async function handleBatchApprove() {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      t('admin.review.batchApproveConfirm', { count: selectedIds.value.length }),
      t('admin.review.batchApprove'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  batchLoading.value = true
  try {
    const items = selectedIds.value.map((r) => ({ review_type: r.review_type, item_id: r.item_id }))
    await client.post('/api/admin/review/batch-approve', { items })
    ElMessage.success(t('admin.review.batchSuccess'))
    await Promise.all([loadList(), loadStats()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('admin.review.operateFailed'))
  } finally {
    batchLoading.value = false
  }
}

async function handleBatchReject() {
  if (selectedIds.value.length === 0) return
  try {
    const { value } = await ElMessageBox.prompt(
      t('admin.review.batchRejectConfirm', { count: selectedIds.value.length }),
      t('admin.review.batchReject'),
      {
        confirmButtonText: t('admin.review.confirmReject'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: t('admin.review.rejectReasonPlaceholder'),
        inputType: 'textarea',
        type: 'warning',
      }
    )
    batchLoading.value = true
    const items = selectedIds.value.map((r) => ({ review_type: r.review_type, item_id: r.item_id }))
    await client.post('/api/admin/review/batch-reject', {
      items,
      reason: (value || '').trim(),
    })
    ElMessage.success(t('admin.review.batchSuccess'))
    await Promise.all([loadList(), loadStats()])
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.message || t('admin.review.operateFailed'))
    }
  } finally {
    batchLoading.value = false
  }
}

// ---- 一键审核（拉取当前筛选条件下所有 pending，再批量操作）----
async function fetchAllPendingItems(): Promise<ReviewItem[]> {
  const all: ReviewItem[] = []
  let currentPage = 1
  const size = 100
  while (true) {
    const params: Record<string, any> = {
      review_type: filters.review_type,
      status: 'pending',
      page: currentPage,
      page_size: size,
    }
    if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
    if (filters.username.trim()) params.username = filters.username.trim()
    if (filters.work_type) params.work_type = filters.work_type
    if (filters.ai_status) params.ai_status = filters.ai_status
    if (filters.item_id != null) params.item_id = filters.item_id

    const res = await client.get('/api/admin/review/list', { params })
    const items: ReviewItem[] = res.items || []
    all.push(...items)
    if (items.length < size) break
    currentPage++
    // 安全阀，防止极端情况死循环
    if (currentPage > 100) break
  }
  return all
}

async function onQuickApproveAll() {
  try {
    await ElMessageBox.confirm(
      t('admin.review.quickApproveConfirm', { count: total.value }),
      t('admin.review.quickApprove'),
      { type: 'success' }
    )
  } catch {
    return
  }
  quickLoading.value = true
  try {
    const items = await fetchAllPendingItems()
    if (items.length === 0) {
      ElMessage.info(t('admin.review.noPending'))
      return
    }
    const payload = items.map((r) => ({ review_type: r.review_type, item_id: r.item_id }))
    await client.post('/api/admin/review/batch-approve', { items: payload })
    ElMessage.success(t('admin.review.quickApproveSuccess', { count: items.length }))
    await Promise.all([loadList(), loadStats()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('admin.review.operateFailed'))
  } finally {
    quickLoading.value = false
  }
}

async function onQuickRejectAll() {
  try {
    const { value } = await ElMessageBox.prompt(
      t('admin.review.quickRejectConfirm', { count: total.value }),
      t('admin.review.quickReject'),
      {
        confirmButtonText: t('admin.review.confirmReject'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: t('admin.review.rejectReasonPlaceholder'),
        inputType: 'textarea',
        type: 'warning',
      }
    )
    quickLoading.value = true
    const items = await fetchAllPendingItems()
    if (items.length === 0) {
      ElMessage.info(t('admin.review.noPending'))
      return
    }
    const payload = items.map((r) => ({ review_type: r.review_type, item_id: r.item_id }))
    await client.post('/api/admin/review/batch-reject', {
      items: payload,
      reason: (value || '').trim(),
    })
    ElMessage.success(t('admin.review.quickRejectSuccess', { count: items.length }))
    await Promise.all([loadList(), loadStats()])
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.message || t('admin.review.operateFailed'))
    }
  } finally {
    quickLoading.value = false
  }
}

// ---- 生命周期 ----
onMounted(async () => {
  await Promise.all([loadList(), loadStats()])
  if (autoRefresh.value) startAutoRefresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.unified-review {
  padding: 0;
}

.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.review-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.last-updated {
  font-size: 12px;
  color: var(--agnes-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  cursor: pointer;
  transition: transform 0.2s;
}
.stat-card:hover {
  transform: translateY(-2px);
}
.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--agnes-text-primary);
}
.stat-label {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  margin-top: 4px;
}
.stat-work .stat-num { color: var(--el-color-primary); }
.stat-preset .stat-num { color: var(--el-color-warning); }
.stat-template .stat-num { color: var(--el-color-success); }
.stat-template-revision .stat-num { color: var(--el-color-info); }
.stat-ai-passed .stat-num { color: var(--el-color-success); }
.stat-ai-violated .stat-num { color: var(--el-color-danger); }

/* 占位列（保持栅格对齐） */
.stat-spacer {
  min-height: 0;
  visibility: hidden;
}

/* 模板修订专属字段区块标题 */
.revision-section-title {
  margin-top: 20px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  padding-left: 8px;
  border-left: 3px solid var(--el-color-info);
}

/* AI 审核结果高亮卡片 */
.ai-result-card {
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  border-left: 4px solid;
}
.ai-result-card.ai-result-pending {
  background: var(--el-color-primary-light-9);
  border-left-color: var(--el-color-primary);
}
.ai-result-card.ai-result-passed {
  background: var(--el-color-success-light-9);
  border-left-color: var(--el-color-success);
}
.ai-result-card.ai-result-violated {
  background: var(--el-color-danger-light-9);
  border-left-color: var(--el-color-danger);
}
.ai-result-card.ai-result-failed {
  background: var(--el-color-warning-light-9);
  border-left-color: var(--el-color-warning);
}
.ai-result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}
.ai-result-title {
  font-size: 14px;
}
.ai-result-reason {
  margin-top: 8px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.filter-card {
  margin-bottom: 12px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 10px;
}

/* 类型 Tab 样式 */
.type-tabs {
  margin-bottom: 4px;
}
.type-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

/* 筛选表单布局 */
.filter-form :deep(.el-form-item) {
  margin-bottom: 16px;
  margin-right: 0;
}

/* 筛选条件网格 - 第一行：下拉选择类筛选项 */
.filter-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;
  align-items: center;
}

/* 关键词搜索行 - 第二行：宽输入框 + 搜索按钮 */
.filter-search-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;
  align-items: center;
  margin-top: 4px;
}

/* 筛选项通用样式 */
.filter-item {
  margin-bottom: 0 !important;
}

/* 筛选控件宽度 */
.filter-control {
  width: 160px;
}
.filter-control-sm {
  width: 130px;
}
.filter-control-keyword {
  width: 320px;
}

/* 快捷操作条 */
.quick-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin: 12px 0 16px 0;
  background: linear-gradient(90deg, #fff7e6 0%, #fffbe6 100%);
  border: 1px solid #ffe58f;
  border-radius: 8px;
}

.quick-label {
  font-size: 13px;
  color: #ad6800;
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 6px;
}
.batch-info {
  font-size: 13px;
  color: var(--el-color-primary);
  margin-right: 8px;
}

.list-card {
  background: var(--el-bg-color);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.desc-text {
  line-height: 1.6;
  white-space: pre-wrap;
}
.reject-text {
  color: var(--el-color-danger);
}

.detail-media {
  display: flex;
  justify-content: center;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  padding: 12px;
}

.detail-thumb {
  margin-top: 16px;
  text-align: center;
}

.muted {
  color: var(--agnes-text-muted);
  font-size: 12px;
}

.type-cell {
  display: flex;
  align-items: center;
}

.preview-cell {
  display: flex;
  justify-content: center;
}

.video-preview {
  position: relative;
  width: 56px;
  height: 56px;
}

.play-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 22px;
  color: #fff;
  text-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
}

.prompt-text {
  color: var(--agnes-text-primary);
  cursor: default;
}

.flags-wrap {
  display: flex;
  flex-wrap: wrap;
}

.author-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
}

.author-name {
  color: var(--agnes-text-primary);
  font-size: 13px;
  font-weight: 500;
}

.author-id {
  font-size: 11px;
}

.stats-text {
  font-size: 13px;
  color: var(--agnes-text-secondary);
}

.stats-text .muted {
  margin: 0 4px;
}
</style>
