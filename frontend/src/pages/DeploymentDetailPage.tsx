import {
  ArrowLeftOutlined,
  CaretRightOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Segmented,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { deploymentApi, metricsApi } from '../api'
import { errorMessage } from '../api/client'
import type { MetricSample, RequestLog } from '../api/types'
import { StatusTag, statusColor } from '../components/StatusTag'
import { usePolling } from '../hooks/usePolling'

const RANGES = [
  { label: '近 5 分钟', value: 5 },
  { label: '近 30 分钟', value: 30 },
  { label: '近 2 小时', value: 120 },
]

const LEVEL_COLOR: Record<string, string> = {
  info: 'blue',
  warning: 'orange',
  error: 'red',
}

export default function DeploymentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const deploymentId = Number(id)
  const navigate = useNavigate()
  const [minutes, setMinutes] = useState(30)
  const [acting, setActing] = useState(false)

  const detail = usePolling(() => deploymentApi.get(deploymentId), 4000, [deploymentId])
  const metrics = usePolling(
    () => metricsApi.forDeployment(deploymentId, minutes),
    5000,
    [deploymentId, minutes],
  )
  const logs = usePolling(
    () => metricsApi.logs(deploymentId, { limit: 20 }),
    5000,
    [deploymentId],
  )

  const act = async (action: 'start' | 'stop' | 'restart') => {
    setActing(true)
    try {
      await deploymentApi[action](deploymentId)
      message.success({ start: '已启动', stop: '已停止', restart: '已重启' }[action])
      detail.refresh()
      metrics.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    } finally {
      setActing(false)
    }
  }

  if (detail.loading && !detail.data) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!detail.data) {
    return <Alert type="error" showIcon message="部署不存在或已被删除" />
  }

  const d = detail.data
  const current = metrics.data?.current
  const chartData = (metrics.data?.samples ?? []).map((s: MetricSample) => ({
    ...s,
    time: dayjs(s.timestamp).format('HH:mm:ss'),
    gpu_mem_gb: Number((s.gpu_memory_used_mb / 1024).toFixed(2)),
    gpu_mem_total_gb: Number((s.gpu_memory_total_mb / 1024).toFixed(2)),
  }))

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/deployments')}>
          返回
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {d.name}
        </Typography.Title>
        <StatusTag status={d.status} />
      </Space>

      {d.error_message && (
        <Alert type="error" showIcon message="实例异常" description={d.error_message} />
      )}

      <Card
        title="实例信息"
        extra={
          <Space>
            {d.status === 'running' ? (
              <>
                <Button
                  icon={<ThunderboltOutlined />}
                  onClick={() => navigate(`/playground?deployment=${d.id}`)}
                >
                  去测试台
                </Button>
                <Button icon={<PoweroffOutlined />} loading={acting} onClick={() => act('stop')}>
                  停止
                </Button>
              </>
            ) : (
              <Button
                type="primary"
                icon={<CaretRightOutlined />}
                loading={acting}
                onClick={() => act('start')}
              >
                启动
              </Button>
            )}
            <Button icon={<ReloadOutlined />} loading={acting} onClick={() => act('restart')}>
              重启
            </Button>
          </Space>
        }
      >
        <Descriptions column={{ xs: 1, sm: 2, lg: 3 }} size="small" bordered>
          <Descriptions.Item label="部署 ID">{d.id}</Descriptions.Item>
          <Descriptions.Item label="模型">
            <Link to="/models">{d.model_name || `#${d.model_id}`}</Link>
          </Descriptions.Item>
          <Descriptions.Item label="引擎">
            <Tag color="blue">{d.engine}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="副本数">{d.replicas}</Descriptions.Item>
          <Descriptions.Item label="主机端口">{d.host_port ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="创建人">{d.created_by ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="推理入口" span={2}>
            {d.endpoint ? (
              <Typography.Text copyable>{d.endpoint}</Typography.Text>
            ) : (
              <Typography.Text type="secondary">实例未运行</Typography.Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="OpenAI 兼容模型名">
            <Typography.Text copyable>{d.name}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {dayjs(d.created_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="启动时间">
            {d.started_at ? dayjs(d.started_at).format('YYYY-MM-DD HH:mm:ss') : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="停止时间">
            {d.stopped_at ? dayjs(d.stopped_at).format('YYYY-MM-DD HH:mm:ss') : '—'}
          </Descriptions.Item>
        </Descriptions>

        {Object.keys(d.engine_params ?? {}).length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Typography.Text type="secondary">生效参数：</Typography.Text>
            <Space wrap style={{ marginTop: 6 }}>
              {Object.entries(d.engine_params).map(([key, value]) => (
                <Tag key={key}>
                  {key} = {String(value) || '（空）'}
                </Tag>
              ))}
            </Space>
          </div>
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Card>
            <Statistic title="累计请求" value={current?.total_requests ?? 0} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card>
            <Statistic
              title="失败请求"
              value={current?.failed_requests ?? 0}
              valueStyle={{ color: current?.failed_requests ? '#ff4d4f' : undefined }}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card>
            <Statistic title="P95 延迟" value={current?.latency_p95_ms ?? 0} precision={1} suffix="ms" />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card>
            <Statistic
              title="GPU 利用率"
              value={current?.gpu_utilization ?? 0}
              precision={1}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Card
        title="性能指标"
        extra={
          <Segmented
            options={RANGES}
            value={minutes}
            onChange={(v) => setMinutes(v as number)}
          />
        }
      >
        {chartData.length === 0 ? (
          <Empty description="暂无采样数据（实例运行后每 5 秒采集一次）" />
        ) : (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <Typography.Text type="secondary">QPS 与吞吐</Typography.Text>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="qpsFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1677ff" stopOpacity={0.7} />
                      <stop offset="95%" stopColor="#1677ff" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" fontSize={11} minTickGap={40} />
                  <YAxis fontSize={11} />
                  <RTooltip />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="qps"
                    name="QPS"
                    stroke="#1677ff"
                    fill="url(#qpsFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Col>

            <Col xs={24} lg={12}>
              <Typography.Text type="secondary">延迟分位（ms）</Typography.Text>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" fontSize={11} minTickGap={40} />
                  <YAxis fontSize={11} />
                  <RTooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="latency_p50_ms"
                    name="P50"
                    stroke="#52c41a"
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="latency_p95_ms"
                    name="P95"
                    stroke="#faad14"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Col>

            <Col xs={24} lg={12}>
              <Typography.Text type="secondary">显存占用（GB）</Typography.Text>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="memFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#722ed1" stopOpacity={0.7} />
                      <stop offset="95%" stopColor="#722ed1" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" fontSize={11} minTickGap={40} />
                  <YAxis fontSize={11} />
                  <RTooltip />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="gpu_mem_gb"
                    name="已用"
                    stroke="#722ed1"
                    fill="url(#memFill)"
                  />
                  <Line
                    type="monotone"
                    dataKey="gpu_mem_total_gb"
                    name="总量"
                    stroke="#bfbfbf"
                    strokeDasharray="4 4"
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Col>

            <Col xs={24} lg={12}>
              <Typography.Text type="secondary">GPU 利用率（%）</Typography.Text>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="utilFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#13c2c2" stopOpacity={0.7} />
                      <stop offset="95%" stopColor="#13c2c2" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" fontSize={11} minTickGap={40} />
                  <YAxis fontSize={11} domain={[0, 100]} />
                  <RTooltip />
                  <Area
                    type="monotone"
                    dataKey="gpu_utilization"
                    name="利用率"
                    stroke="#13c2c2"
                    fill="url(#utilFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Col>
          </Row>
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="最近请求">
            <Table<RequestLog>
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={logs.data ?? []}
              locale={{ emptyText: <Empty description="暂无请求" /> }}
              columns={[
                {
                  title: '时间',
                  dataIndex: 'created_at',
                  width: 80,
                  render: (v: string) => dayjs(v).format('HH:mm:ss'),
                },
                {
                  title: '输入',
                  dataIndex: 'prompt_preview',
                  ellipsis: true,
                  render: (v: string) => v || '—',
                },
                {
                  title: '耗时',
                  dataIndex: 'latency_ms',
                  width: 80,
                  render: (v: number) => `${v.toFixed(0)}ms`,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 70,
                  render: (s: string) => (
                    <Tag color={s === 'success' ? 'green' : 'red'}>
                      {s === 'success' ? '成功' : '失败'}
                    </Tag>
                  ),
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="生命周期事件">
            {d.events.length === 0 ? (
              <Empty description="暂无事件" />
            ) : (
              <Timeline
                style={{ marginTop: 8 }}
                items={d.events.map((e) => ({
                  color: LEVEL_COLOR[e.level] ?? 'blue',
                  children: (
                    <Space direction="vertical" size={0}>
                      <Space size={6}>
                        <Tag color={LEVEL_COLOR[e.level] ?? 'blue'}>{e.event}</Tag>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {dayjs(e.created_at).format('MM-DD HH:mm:ss')}
                        </Typography.Text>
                      </Space>
                      <span>{e.message}</span>
                    </Space>
                  ),
                }))}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="状态图例">
        <Space wrap>
          {['pending', 'starting', 'running', 'stopping', 'stopped', 'failed'].map((s) => (
            <Tag key={s} color={statusColor(s)}>
              {s}
            </Tag>
          ))}
        </Space>
      </Card>
    </Space>
  )
}
