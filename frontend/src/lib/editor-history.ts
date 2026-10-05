/* =====================================================
 * 剪辑器撤销/重做 — 200 层结构共享快照栈
 *
 * - 不可变命令更新使未变子树天然共享，这里只存引用不深拷贝
 * - 满上限丢最旧；栈仅内存（刷新即清空，document 为最后保存版）
 * ===================================================== */

import type { EditorDocument } from './editor-types'

export const MAX_HISTORY_ENTRIES = 200

export interface HistoryEntry {
  /** 操作前文档（undo 目标） */
  undoDoc: EditorDocument
  /** 操作后文档（redo 目标） */
  redoDoc: EditorDocument
  /** 展示用标签（组件层 i18n 后传入） */
  label: string
}

export class EditorHistory {
  private entries: HistoryEntry[] = []
  /** 当前指向 entries 的下标（长度表示可 redo 深度） */
  private pointer = -1

  push(entry: HistoryEntry): void {
    // 在中间位置push 时丢弃后续 redo 分支
    this.entries = this.entries.slice(0, this.pointer + 1)
    this.entries.push(entry)
    if (this.entries.length > MAX_HISTORY_ENTRIES) {
      this.entries = this.entries.slice(this.entries.length - MAX_HISTORY_ENTRIES)
    }
    this.pointer = this.entries.length - 1
  }

  undo(): HistoryEntry | null {
    if (this.pointer < 0) return null
    const entry = this.entries[this.pointer]
    this.pointer -= 1
    return entry
  }

  redo(): HistoryEntry | null {
    if (this.pointer >= this.entries.length - 1) return null
    this.pointer += 1
    return this.entries[this.pointer]
  }

  get canUndo(): boolean {
    return this.pointer >= 0
  }

  get canRedo(): boolean {
    return this.pointer < this.entries.length - 1
  }

  get depth(): number {
    return this.pointer + 1
  }

  clear(): void {
    this.entries = []
    this.pointer = -1
  }
}
