/* =====================================================
 * 共享对话 UI 视图模型（components/chat）
 *
 * 组件零业务依赖：宿主 store（chat / agent）把各自消息模型
 * 映射成以下结构后以 props 传入，事件回传宿主动作。
 * ===================================================== */

/** 工具步骤时间线的一行（label 由宿主完成 i18n 与领域转译） */
export interface ChatStepView {
  callId: string
  label: string
  /** 悬停提示（如英文工具名） */
  tooltip?: string
  status: 'pending' | 'running' | 'done' | 'error' | 'rejected'
  /** 工具结果原文（宿主插槽可用于领域渲染，如画布风格卡片） */
  result?: string | null
  /** 运行态实时进度文本（agent_delegate 子任务进度，宿主 i18n 组装） */
  progress?: string
}

/** 用户消息附图（缩略图，点击预览） */
export interface ChatImageView {
  /** data URL 或 http URL */
  src: string
}

/** 用户消息附件卡（对话页的文档/视频/图片链接附件） */
export interface ChatAttachmentView {
  kind: 'image' | 'video' | 'document'
  name: string
  url: string
}

/** assistant 生成产物（媒体三态：生成中/成功/失败） */
export interface ChatMediaView {
  type: 'image' | 'video'
  url: string
  taskId?: string
  status: 'pending' | 'processing' | 'success' | 'failed'
}

/** 一条消息的渲染视图 */
export interface ChatBubbleItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 流式中：assistant 内容尾部渲染光标 */
  streaming?: boolean
  images?: ChatImageView[]
  attachments?: ChatAttachmentView[]
  media?: ChatMediaView[]
  steps?: ChatStepView[]
  createdAt?: string
}

/** 会话列表条目（侧栏展示用） */
export interface ChatSessionView {
  id: number | string
  title: string
  updatedAt?: string
  /** 画布 Agent 会话：侧栏带角标，点击由宿主跳转画布 */
  canvas?: boolean
  /** 该会话正在后台生成回复（侧栏转圈角标） */
  generating?: boolean
}

/** 侧栏三点菜单的扩展命令（宿主自定义，如「AI 总结」） */
export interface ChatSessionCommand {
  command: string
  label: string
}
