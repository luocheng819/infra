import { Button, Card, Form, Input, Typography, message } from 'antd'
import { ApiOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      await login(values.username, values.password)
      message.success('登录成功')
      navigate('/')
    } catch (err) {
      message.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%)',
      }}
    >
      <Card style={{ width: 400, boxShadow: '0 12px 40px rgba(0,0,0,.35)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <ApiOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          <Typography.Title level={3} style={{ marginTop: 12, marginBottom: 4 }}>
            LLM Deploy
          </Typography.Title>
          <Typography.Text type="secondary">大模型部署推理管理平台</Typography.Text>
        </div>

        <Form layout="vertical" onFinish={onFinish} initialValues={{ username: 'admin' }}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>

        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          首次启动默认账号：admin / admin123，请在登录后尽快修改。
        </Typography.Text>
      </Card>
    </div>
  )
}
