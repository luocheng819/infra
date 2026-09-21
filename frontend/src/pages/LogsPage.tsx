import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { deploymentApi, metricsApi } from '../api'
import type { RequestLog } from '../api/types'
import { usePolling } from '../hooks/usePolling'

export default function LogsPage() {
  const [deploymentFilter, setDeploymentFilter] = useState<number | undefined>()
  const [statusFilter, setStatusFilter] = useState<string | undefined>()

  const deployments = usePolling(() => deploymentApi.list(), 30_000)
  const logs = usePolling(
    () =>
      metricsApi.allLogs({
        limit: 200,
        deployment_id: deploymentFilter,
        status: statusFilter,
      }),
    5000,
    [deploymentFilter, statusFilter],
  )

  const nameOf = (id: number) =>
    deployments.data?.find((d) => d.id === id)?.name ?? `#${id}`

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          请求日志
        </Typography.Title>
        <Typography.Text type="secondary">
          所有推理调用的明细，含 token 计量与耗时，可用于排查问题与容量评估。
        </Typography.Text>
      </div>

      {logs.error && <Alert type="error" showIcon message="加载日志失败" description={logs.error} />}

      <Card
        title="调用明细"
        extra={
          <Space>
            <Select
              allowClear
              placeholder="全部部署"
              style={{ width: 200 }}
              value={deploymentFilter}
              onChange={setDeploymentFilter}
              options={(deployments.data ?? []).map((d) => ({ value: d.id, label: d.name }))}
            />
            <Select
              allowClear
              placeholder="全部状态"
              style={{ width: 130 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: 'success', label: '成功' },
                { value: 'failed', label: '失败' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={logs.refresh} />
          </Space>
        }
      >
        <Table<RequestLog>
          rowKey="id"
          size="small"
          loading={logs.loading}
          dataSource={logs.data ?? []}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: 1100 }}
          columns={[
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 165,
              render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
            },
            {
              title: '部署',
              dataIndex: 'deployment_id',
              width: 160,
              render: (id: number) => nameOf(id),
            },
            {
              title: '请求 ID',
              dataIndex: 'request_id',
              width: 190,
              render: (v: string) => (
                <Typography.Text copyable style={{ fontSize: 12 }}>
                  {v}
                </Typography.Text>
              ),
            },
            {
              title: '输入摘要',
              dataIndex: 'prompt_preview',
              ellipsis: true,
              render: (v: string) => v || '—',
            },
            {
              title: '方式',
              dataIndex: 'stream',
              width: 80,
              render: (stream: boolean) =>
                stream ? <Tag color="purple">流式</Tag> : <Tag>一次性</Tag>,
            },
            {
              title: 'Token',
              width: 110,
              render: (_, row) => (
                <Tooltip title={`输入 ${row.prompt_tokens} / 输出 ${row.completion_tokens}`}>
                  <span>{row.prompt_tokens + row.completion_tokens}</span>
                </Tooltip>
              ),
            },
            {
              title: '耗时',
              dataIndex: 'latency_ms',
              width: 90,
              sorter: (a, b) => a.latency_ms - b.latency_ms,
              render: (v: number) => `${v.toFixed(0)} ms`,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (status: string, row) => (
                <Tooltip title={row.error ?? undefined}>
                  <Tag color={status === 'success' ? 'green' : 'red'}>
                    {status === 'success' ? '成功' : '失败'}
                  </Tag>
                </Tooltip>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  )
}
