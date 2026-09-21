import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeploymentUnitOutlined,
  HddOutlined,
  RiseOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Card, Col, Empty, Progress, Row, Space, Spin, Statistic, Table, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'
import { deploymentApi, overviewApi } from '../api'
import type { Deployment } from '../api/types'
import { StatusTag } from '../components/StatusTag'
import { usePolling } from '../hooks/usePolling'

export default function DashboardPage() {
  const overview = usePolling(() => overviewApi.get(), 5000)
  const deployments = usePolling(() => deploymentApi.list(), 5000)

  if (overview.loading && !overview.data) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  const stats = overview.data
  const running = deployments.data?.filter((d) => d.status === 'running') ?? []

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          平台总览
        </Typography.Title>
        <Typography.Text type="secondary">
          模型仓库、部署实例与推理流量的整体运行状况（每 5 秒自动刷新）
        </Typography.Text>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="模型仓库"
              value={stats?.total_models ?? 0}
              prefix={<HddOutlined />}
              suffix="个"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="部署实例"
              value={stats?.total_deployments ?? 0}
              prefix={<DeploymentUnitOutlined />}
              suffix="个"
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#8c8c8c' }}>
              运行中 <b style={{ color: '#52c41a' }}>{stats?.running_deployments ?? 0}</b>
              {' · '}
              失败 <b style={{ color: stats?.failed_deployments ? '#ff4d4f' : '#8c8c8c' }}>
                {stats?.failed_deployments ?? 0}
              </b>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="累计推理请求"
              value={stats?.total_requests ?? 0}
              prefix={<ThunderboltOutlined />}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#8c8c8c' }}>
              近 1 小时 <b>{stats?.requests_last_hour ?? 0}</b> 次
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均延迟"
              value={stats?.avg_latency_ms ?? 0}
              precision={1}
              suffix="ms"
              prefix={<RiseOutlined />}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#8c8c8c' }}>
              累计 token <b>{(stats?.total_tokens ?? 0).toLocaleString()}</b>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="请求成功率" style={{ height: '100%' }}>
            {(() => {
              const rate = stats ? (1 - stats.failure_rate) * 100 : 100
              return (
                <>
                  <div style={{ textAlign: 'center', marginBottom: 16 }}>
                    <Progress
                      type="dashboard"
                      percent={Number(rate.toFixed(2))}
                      strokeColor={rate > 95 ? '#52c41a' : rate > 80 ? '#faad14' : '#ff4d4f'}
                    />
                  </div>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>
                        <CheckCircleOutlined style={{ color: '#52c41a' }} /> 成功
                      </span>
                      <b>
                        {(
                          (stats?.total_requests ?? 0) -
                          Math.round((stats?.total_requests ?? 0) * (stats?.failure_rate ?? 0))
                        ).toLocaleString()}
                      </b>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>
                        <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> 失败
                      </span>
                      <b>
                        {Math.round(
                          (stats?.total_requests ?? 0) * (stats?.failure_rate ?? 0),
                        ).toLocaleString()}
                      </b>
                    </div>
                  </Space>
                </>
              )
            })()}
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          <Card
            title="运行中的部署"
            extra={<Link to="/deployments">查看全部</Link>}
            style={{ height: '100%' }}
          >
            {running.length === 0 ? (
              <Empty description="当前没有运行中的部署">
                <Link to="/deployments">去创建一个</Link>
              </Empty>
            ) : (
              <Table<Deployment>
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={running}
                columns={[
                  {
                    title: '名称',
                    dataIndex: 'name',
                    render: (name: string, row) => <Link to={`/deployments/${row.id}`}>{name}</Link>,
                  },
                  { title: '模型', dataIndex: 'model_name' },
                  {
                    title: '引擎',
                    dataIndex: 'engine',
                    render: (engine: string) => <Tag color="blue">{engine}</Tag>,
                  },
                  { title: '端口', dataIndex: 'host_port' },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (s) => <StatusTag status={s} />,
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="支持的推理引擎">
        <Space wrap>
          {(stats?.engines ?? []).map((engine) => (
            <Tag key={engine} color="geekblue" style={{ padding: '4px 12px', fontSize: 13 }}>
              {engine}
            </Tag>
          ))}
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          引擎通过统一适配器接口接入。当前默认使用 <b>mock</b> 仿真引擎，可在无 GPU 环境完整验证
          部署、推理、计量与监控链路；部署到 GPU 机器后切换到 <b>vllm</b> 即可跑真实模型，
          无需修改任何平台代码。
        </Typography.Paragraph>
      </Card>
    </Space>
  )
}
