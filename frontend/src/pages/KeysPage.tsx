import { CopyOutlined, DeleteOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { keyApi } from '../api'
import { errorMessage } from '../api/client'
import type { ApiKey, ApiKeyCreated } from '../api/types'
import { usePolling } from '../hooks/usePolling'

export default function KeysPage() {
  const [createOpen, setCreateOpen] = useState(false)
  const [created, setCreated] = useState<ApiKeyCreated | null>(null)
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const keys = usePolling(() => keyApi.list(), 30_000)

  const submit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      const result = await keyApi.create(values.name)
      setCreated(result)
      setCreateOpen(false)
      form.resetFields()
      keys.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const toggle = async (row: ApiKey) => {
    try {
      await keyApi.toggle(row.id)
      keys.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    }
  }

  const remove = async (row: ApiKey) => {
    try {
      await keyApi.remove(row.id)
      message.success('已删除')
      keys.refresh()
    } catch (err) {
      message.error(errorMessage(err))
    }
  }

  const baseUrl = `${location.origin}`

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          API Key
        </Typography.Title>
        <Typography.Text type="secondary">
          业务系统通过 API Key 调用 OpenAI 兼容接口，与平台登录态相互独立。
        </Typography.Text>
      </div>

      <Alert
        type="info"
        showIcon
        message="调用方式"
        description={
          <Space direction="vertical" size={4} style={{ marginTop: 6 }}>
            <Typography.Text code>
              POST {baseUrl}/v1/chat/completions
            </Typography.Text>
            <Typography.Text code>Authorization: Bearer sk-llmd-...</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              请求体中的 <b>model</b> 字段填部署名称；也可用 <b>X-Deployment</b> 头显式指定。
              该接口与 OpenAI SDK 兼容，可直接把 base_url 指向 {baseUrl}/v1 使用。
            </Typography.Text>
          </Space>
        }
      />

      <Card
        title="密钥列表"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            创建密钥
          </Button>
        }
      >
        <Table<ApiKey>
          rowKey="id"
          loading={keys.loading}
          dataSource={keys.data ?? []}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          columns={[
            {
              title: '名称',
              dataIndex: 'name',
              render: (name: string) => (
                <Space>
                  <KeyOutlined />
                  {name}
                </Space>
              ),
            },
            {
              title: '前缀',
              dataIndex: 'prefix',
              render: (prefix: string) => <Typography.Text code>{prefix}…</Typography.Text>,
            },
            { title: '创建人', dataIndex: 'owner', width: 120 },
            {
              title: '最近使用',
              dataIndex: 'last_used_at',
              width: 180,
              render: (v: string | null) =>
                v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '从未使用',
            },
            {
              title: '状态',
              dataIndex: 'is_active',
              width: 110,
              render: (active: boolean, row) => (
                <Space>
                  <Switch size="small" checked={active} onChange={() => toggle(row)} />
                  <Tag color={active ? 'green' : 'default'}>{active ? '启用' : '禁用'}</Tag>
                </Space>
              ),
            },
            {
              title: '操作',
              width: 80,
              render: (_, row) => (
                <Popconfirm title="删除后使用该密钥的调用将立即失效，确认？" onConfirm={() => remove(row)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="创建 API Key"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={submit}
        confirmLoading={submitting}
        okText="创建"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="例如：检索服务、数据标注流水线" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="密钥创建成功"
        open={!!created}
        onCancel={() => setCreated(null)}
        footer={[
          <Button
            key="copy"
            type="primary"
            icon={<CopyOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(created?.key ?? '')
              message.success('已复制到剪贴板')
            }}
          >
            复制密钥
          </Button>,
          <Button key="close" onClick={() => setCreated(null)}>
            我已保存
          </Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          message="请立即保存"
          description="出于安全考虑，明文密钥只在本次响应中返回一次，关闭后无法再次查看。"
          style={{ marginBottom: 12 }}
        />
        <Typography.Paragraph
          copyable
          code
          style={{ background: '#fafafa', padding: 12, borderRadius: 6, wordBreak: 'break-all' }}
        >
          {created?.key}
        </Typography.Paragraph>
      </Modal>
    </Space>
  )
}
