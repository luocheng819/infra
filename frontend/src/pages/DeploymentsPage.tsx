import {
  CaretRightOutlined,
  DeleteOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { deploymentApi, engineApi, modelApi } from '../api'
import { errorMessage } from '../api/client'
import type { Deployment, EngineInfo, ModelInfo } from '../api/types'
import { EngineParamFields } from '../components/EngineParamFields'
import { StatusTag } from '../components/StatusTag'
import { usePolling } from '../hooks/usePolling'

export default function DeploymentsPage() {
  const navigate = useNavigate()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [acting, setActing] = useState<number | null>(null)

  const deployments = usePolling(() => deploymentApi.list(), 4000)
  const models = usePolling(() => modelApi.list(), 60_000)
  const engines = usePolling(() => engineApi.list(), 60_000)

  const selectedEngine = Form.useWatch('engine', form) as string | undefined
  const engineSchema: EngineInfo | undefined = engines.data?.find(
    (e) => e.name === selectedEngine,
  )

  /** 切换引擎时，用该引擎的默认参数重置表单参数区。 */
  const onEngineChange = (name: string) => {
    const engine = engines.data?.find((e) => e.name === name)
    form.setFieldValue('engine_params', engine ? { ...engine.default_params } : {})
  }

  const onModelChange = (modelId: number) => {
    const model = models.data?.find((m) => m.id === modelId)
    if (model && Object.keys(model.default_engine_params ?? {}).length) {
      form.setFieldValue('engine_params', {
        ...(form.getFieldValue('engine_params') ?? {}),
        ...model.default_engine_params,
      })
    }
  }

  const openCreate = () => {
    form.resetFields()
    const defaultEngine = engines.data?.[0]
    form.setFieldsValue({
      engine: defaultEngine?.name ?? 'mock',
      replicas: 1,
      engine_params: defaultEngine ? { ...defaultEngine.default_params } : {},
    })
    setDrawerOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      const created = await deploymentApi.create(values)
      if (created.status === 'failed') {
        message.warning(`部署已创建但启动失败：${created.error_message ?? '未知原因'}`)
      } else {
        message.success('部署已启动')
      }
      setDrawerOpen(false)
      deployments.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const act = async (id: number, action: 'start' | 'stop' | 'restart') => {
    setActing(id)
    try {
      const result = await deploymentApi[action](id)
      if (result.status === 'failed') {
        message.warning(`操作完成但状态为失败：${result.error_message ?? ''}`)
      } else {
        message.success(
          { start: '已启动', stop: '已停止', restart: '已重启' }[action],
        )
      }
      deployments.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    } finally {
      setActing(null)
    }
  }

  const remove = async (id: number) => {
    try {
      await deploymentApi.remove(id)
      message.success('已删除')
      deployments.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          部署管理
        </Typography.Title>
        <Typography.Text type="secondary">
          把模型仓库中的模型部署为可调用的推理实例。每个部署独立占用一个端口，
          并自动接入监控与日志。
        </Typography.Text>
      </div>

      {deployments.error && (
        <Alert type="error" showIcon message="加载部署列表失败" description={deployments.error} />
      )}

      <Card
        title={`共 ${deployments.data?.length ?? 0} 个部署`}
        extra={
          <Space>
            <Tooltip title="刷新">
              <Button icon={<ReloadOutlined />} onClick={deployments.refresh} />
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建部署
            </Button>
          </Space>
        }
      >
        <Table<Deployment>
          rowKey="id"
          loading={deployments.loading}
          dataSource={deployments.data ?? []}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 1100 }}
          columns={[
            {
              title: '部署名',
              dataIndex: 'name',
              fixed: 'left',
              render: (name: string, row) => <Link to={`/deployments/${row.id}`}>{name}</Link>,
            },
            { title: '模型', dataIndex: 'model_name', width: 180, ellipsis: true },
            {
              title: '引擎',
              dataIndex: 'engine',
              width: 110,
              render: (engine: string) => {
                const info = engines.data?.find((e) => e.name === engine)
                return (
                  <Tooltip title={info?.display_name ?? engine}>
                    <Tag color={info?.requires_gpu ? 'volcano' : 'blue'}>{engine}</Tag>
                  </Tooltip>
                )
              },
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (status, row) => (
                <Tooltip title={row.error_message ?? undefined}>
                  <span>
                    <StatusTag status={status} />
                  </span>
                </Tooltip>
              ),
            },
            {
              title: '访问入口',
              width: 220,
              render: (_, row) =>
                row.status === 'running' ? (
                  <Typography.Text copyable style={{ fontSize: 12 }}>
                    {row.endpoint}
                  </Typography.Text>
                ) : (
                  <Typography.Text type="secondary">—</Typography.Text>
                ),
            },
            {
              title: '创建人',
              dataIndex: 'created_by',
              width: 100,
              render: (v: string | null) => v ?? '—',
            },
            {
              title: '操作',
              width: 220,
              fixed: 'right',
              render: (_, row) => (
                <Space size={4}>
                  {row.status === 'running' ? (
                    <>
                      <Tooltip title="测试台">
                        <Button
                          size="small"
                          icon={<ThunderboltOutlined />}
                          onClick={() => navigate(`/playground?deployment=${row.id}`)}
                        />
                      </Tooltip>
                      <Tooltip title="停止">
                        <Button
                          size="small"
                          icon={<PoweroffOutlined />}
                          loading={acting === row.id}
                          onClick={() => act(row.id, 'stop')}
                        />
                      </Tooltip>
                      <Tooltip title="重启">
                        <Button
                          size="small"
                          icon={<ReloadOutlined />}
                          loading={acting === row.id}
                          onClick={() => act(row.id, 'restart')}
                        />
                      </Tooltip>
                    </>
                  ) : (
                    <Tooltip title="启动">
                      <Button
                        size="small"
                        type="primary"
                        icon={<CaretRightOutlined />}
                        loading={acting === row.id}
                        onClick={() => act(row.id, 'start')}
                      />
                    </Tooltip>
                  )}
                  <Popconfirm
                    title="确认删除该部署？"
                    description="会先停止实例再删除相关日志与指标。"
                    onConfirm={() => remove(row.id)}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Drawer
        title="新建部署"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={560}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={submitting} onClick={submit}>
              创建并启动
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="创建后会自动启动实例"
          description="若启动失败，部署会以「失败」状态保留，可在列表中查看原因并重试。"
        />

        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="部署名称"
            tooltip="同时作为 OpenAI 兼容接口中的 model 名称"
            rules={[
              { required: true, message: '请输入部署名称' },
              { pattern: /^[a-zA-Z0-9._-]+$/, message: '仅允许字母、数字、. _ -' },
            ]}
          >
            <Input placeholder="qwen7b-prod" />
          </Form.Item>

          <Form.Item name="model_id" label="选择模型" rules={[{ required: true, message: '请选择模型' }]}>
            <Select
              placeholder="从模型仓库中选择"
              onChange={onModelChange}
              options={(models.data ?? []).map((m: ModelInfo) => ({
                value: m.id,
                label: `${m.display_name}（${m.name}）`,
              }))}
            />
          </Form.Item>

          <Form.Item name="engine" label="推理引擎" rules={[{ required: true }]}>
            <Select onChange={onEngineChange} optionLabelProp="label">
              {(engines.data ?? []).map((e) => (
                <Select.Option key={e.name} value={e.name} label={e.display_name} disabled={!e.available}>
                  <Space direction="vertical" size={0}>
                    <Space>
                      <b>{e.display_name}</b>
                      {e.requires_gpu && <Tag color="volcano">需 GPU</Tag>}
                      {!e.available && <Tag>不可用</Tag>}
                    </Space>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {e.description}
                    </Typography.Text>
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="replicas" label="副本数" tooltip="预留的横向扩缩容位">
            <InputNumber min={1} max={8} style={{ width: '100%' }} />
          </Form.Item>

          {engineSchema && engineSchema.param_schema.length > 0 && (
            <Card size="small" title={`${engineSchema.display_name} 参数`} style={{ marginBottom: 16 }}>
              <EngineParamFields schema={engineSchema.param_schema} />
            </Card>
          )}
        </Form>
      </Drawer>
    </Space>
  )
}
