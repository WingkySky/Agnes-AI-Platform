/* =====================================================
 * 剪辑器撤销/重做 — 200 层结构共享快照栈
 *
 * - 不可变命令更新使未变子树天然共享，这里只存引用不深拷贝
 * - 满上限丢最旧；栈可持久化（serialize/restore，按工程 uid+revision 链校验，
 *   localStorage 体积钳制超限丢最旧——刷新/重开工程后撤销可续）
 * ===================================================== */

import type { EditorDocument } from './editor-types'

export const MAX_HISTORY_ENTRIES = 200
/** 持久化包体积钳制（JSON 字节数，超限逐条丢最旧） */
export const MAX_PERSISTED_BYTES = 3 * 1024 * 1024
/** 持久化条数上限（远小于内存栈：恢复只为续 undo，不需要 200 层） */
export const MAX_PERSISTED_ENTRIES = 40

export interface HistoryEntry {
  /** 操作前文档（undo 目标） */
  undoDoc: EditorDocument
  /** 操作后文档（redo 目标） */
  redoDoc: EditorDocument
  /** 展示用标签（组件层 i18n 后传入） */
  label: string
}

export interface HistorySnapshot {
  /** 持久化时工程 revision（恢复时与远端比对，链断即弃） */
  revision: number
  entries: HistoryEntry[]
  /** 指向 entries 的下标 */
  pointer: number
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

  /** 持久化快照：只留最近 MAX_PERSISTED_ENTRIES 条（指向 redo 链尾对齐），体积超限逐条丢最旧 */
  serialize(revision: number): HistorySnapshot | null {
    if (!this.entries.length) return null
    let entries = this.entries.slice(-MAX_PERSISTED_ENTRIES)
    entries = entries.map((e) => ({ ...e }))
    const snap = (): HistorySnapshot => ({
      revision,
      entries,
      pointer: entries.length - 1 + (this.pointer - (this.entries.length - 1)),
    })
    while (JSON.stringify(snap()).length > MAX_PERSISTED_BYTES) {
      if (entries.length <= 1) return null
      entries = entries.slice(1)
    }
    return snap()
  }

  /** 恢复：覆盖当前栈（仅当快照尾部 redoDoc 与当前文档一致——由调用方校验后调用） */
  restore(snapshot: HistorySnapshot): void {
    this.entries = snapshot.entries.map((e) => ({ ...e }))
    this.pointer = Math.min(Math.max(snapshot.pointer, -1), this.entries.length - 1)
  }

  /** 栈尾 redoDoc（恢复校验用：与远端文档一致才可信） */
  get tailRedoDoc(): EditorDocument | null {
    return this.entries.length ? this.entries[this.entries.length - 1].redoDoc : null
  }
}
