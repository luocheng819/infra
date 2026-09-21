import { Tag, Tooltip } from 'antd'
import type { DeploymentStatus } from '../api/types'

const STATUS_META: Record<
  DeploymentStatus,
  { color: string; label: string; hint: string }
> = {
  pending: { color: 'default', label: '待启动', hint: '已创建，尚未分配资源' },
  starting: { color: 'processing', label: '启动中', hint: '正在加载权重、初始化引擎' },
  running: { color: 'success', label: '运行中', hint: '实例就绪，可接受推理请求' },
  stopping: { color: 'warning', label: '停止中', hint: '正在停止实例并释放端口' },
  stopped: { color: 'default', label: '已停止', hint: '实例已停止' },
  failed: { color: 'error', label: '失败', hint: '启动或健康检查失败，请查看事件' },
}

export function StatusTag({ status }: { status: DeploymentStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.pending
  return (
    <Tooltip title={meta.hint}>
      <Tag color={meta.color}>{meta.label}</Tag>
    </Tooltip>
  )
}

export function statusLabel(status: string): string {
  return STATUS_META[status as DeploymentStatus]?.label ?? status
}

export function statusColor(status: string): string {
  return STATUS_META[status as DeploymentStatus]?.color ?? 'default'
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`
}
