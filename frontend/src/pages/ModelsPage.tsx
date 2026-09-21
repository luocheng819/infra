import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
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
import { modelApi } from '../api'
import { errorMessage } from '../api/client'
import type { ModelInfo, ModelSource } from '../api/types'
import { formatBytes } from '../components/StatusTag'
import { usePolling } from '../hooks/usePolling'

const SOURCE_OPTIONS: { value: ModelSource; label: string }[] = [
  { value: 'huggingface', label: 'HuggingFace 仓库' },
  { value: 'modelscope', label: 'ModelScope 仓库' },
  { value: 'local', label: '本地目录' },
]

const SOURCE_COLOR: Record<ModelSource, string> = {
  huggingface: 'gold',
  modelscope: 'purple',
  local: 'cyan',
}

export default function ModelsPage() {
  const [keyword, setKeyword] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<ModelInfo | null>(null)
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const { data, loading, refresh } = usePolling(
    () => modelApi.list(keyword ? { q: keyword } : undefined),
    30_000,
    [keyword],
  )

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ source: 'huggingface', revision: 'main', tags: [] })
    setDrawerOpen(true)
  }

  const openEdit = (record: ModelInfo) => {
    setEditing(record)
    form.setFieldsValue({ ...record, size_bytes: record.size_bytes })
    setDrawerOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      if (editing) {
        await modelApi.update(editing.id, values)
        message.success('模型已更新')
      } else {
        await modelApi.create(values)
        message.success('模型已登记')
      }
      setDrawerOpen(false)
      refresh()
    } catch (err) {
      message.error(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const remove = async (record: ModelInfo) => {
    try {
      await modelApi.remove(record.id)
      message.success('已删除')
      refresh()
    } catch (err) {
      message.error(errorMessage(err))
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          模型仓库
        </Typography.Title>
        <Typography.Text type="secondary">
          登记可供部署的模型制品。远程仓库在部署时由引擎按引用拉取，本地目录需先放入数据目录。
        </Typography.Text>
      </div>

      <Card
        styles={{ body: { paddingBottom: 12 } }}
        title={
          <Space>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索名称或描述"
              style={{ width: 260 }}
              onChange={(e) => setKeyword(e.target.value)}
            />
          </Space>
        }
        extra={
          <Space>
            <Tooltip title="刷新">
              <Button icon={<ReloadOutlined />} onClick={refresh} />
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              登记模型
            </Button>
          </Space>
        }
      >
        <Table<ModelInfo>
          rowKey="id"
          loading={loading}
          dataSource={data ?? []}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 1000 }}
          columns={[
            {
              title: '名称',
              dataIndex: 'display_name',
              fixed: 'left',
              render: (text: string, row) => (
                <Space direction="vertical" size={0}>
                  <b>{text}</b>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {row.name}
                  </Typography.Text>
                </Space>
              ),
            },
            {
              title: '来源',
              dataIndex: 'source',
              width: 140,
              render: (source: ModelSource, row) => (
                <Space direction="vertical" size={2}>
                  <Tag color={SOURCE_COLOR[source]}>{source}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }} copyable>
                    {row.source_ref}
                  </Typography.Text>
                </Space>
              ),
            },
            {
              title: '规格',
              width: 150,
              render: (_, row) => (
                <Space size={4} wrap>
                  {row.parameter_count && <Tag>{row.parameter_count}</Tag>}
                  {row.quantization && <Tag color="orange">{row.quantization}</Tag>}
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {formatBytes(row.size_bytes)}
                  </Typography.Text>
                </Space>
              ),
            },
            {
              title: '标签',
              dataIndex: 'tags',
              width: 180,
              render: (tags: string[]) => (
                <>
                  {(tags ?? []).map((t) => (
                    <Tag key={t} color="blue">
                      {t}
                    </Tag>
                  ))}
                </>
              ),
            },
            {
              title: '部署数',
              dataIndex: 'deployment_count',
              width: 80,
              align: 'center',
            },
            {
              title: '描述',
              dataIndex: 'description',
              ellipsis: true,
            },
            {
              title: '操作',
              width: 130,
              fixed: 'right',
              render: (_, row) => (
                <Space>
                  <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
                  <Popconfirm
                    title="确认删除该模型？"
                    description="其历史部署记录也会一并删除。"
                    onConfirm={() => remove(row)}
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
        title={editing ? `编辑模型 · ${editing.name}` : '登记新模型'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={520}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={submitting} onClick={submit}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="模型标识"
            tooltip="唯一标识，建议与仓库名一致，创建后不可修改"
            rules={[
              { required: !editing, message: '请输入模型标识' },
              { pattern: /^[a-zA-Z0-9._-]+$/, message: '仅允许字母、数字、. _ -' },
            ]}
          >
            <Input placeholder="qwen2.5-7b-instruct" disabled={!!editing} />
          </Form.Item>

          <Form.Item
            name="display_name"
            label="展示名称"
            rules={[{ required: true, message: '请输入展示名称' }]}
          >
            <Input placeholder="Qwen2.5-7B-Instruct" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="用途、能力边界、注意事项" />
          </Form.Item>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="source" label="来源类型" style={{ flex: 1 }} rules={[{ required: true }]}>
              <Select options={SOURCE_OPTIONS} />
            </Form.Item>
            <Form.Item name="revision" label="版本/分支" style={{ flex: 1 }}>
              <Input placeholder="main" />
            </Form.Item>
          </Space>

          <Form.Item
            name="source_ref"
            label="来源引用"
            tooltip="远程填仓库 ID（如 Qwen/Qwen2.5-7B-Instruct）；本地填数据目录下的子目录名"
            rules={[{ required: true, message: '请输入来源引用' }]}
          >
            <Input placeholder="Qwen/Qwen2.5-7B-Instruct" />
          </Form.Item>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="parameter_count" label="参数量" style={{ flex: 1 }}>
              <Input placeholder="7B" />
            </Form.Item>
            <Form.Item name="quantization" label="量化方式" style={{ flex: 1 }}>
              <Select
                allowClear
                placeholder="无"
                options={['awq', 'gptq', 'fp8', 'int8', 'int4'].map((v) => ({
                  value: v,
                  label: v,
                }))}
              />
            </Form.Item>
          </Space>

          <Form.Item name="size_bytes" label="制品大小（字节）">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="15200000000" />
          </Form.Item>

          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="回车添加，如：中文、对话" />
          </Form.Item>
        </Form>
      </Drawer>
    </Space>
  )
}
