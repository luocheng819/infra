import {
  ApiOutlined,
  AppstoreOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  FileTextOutlined,
  KeyOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Avatar, Button, Dropdown, Layout, Menu, Space, Typography } from 'antd'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const { Header, Sider, Content } = Layout

const MENU = [
  { key: '/', icon: <DashboardOutlined />, label: '总览' },
  { key: '/models', icon: <AppstoreOutlined />, label: '模型仓库' },
  { key: '/deployments', icon: <DeploymentUnitOutlined />, label: '部署管理' },
  { key: '/playground', icon: <ThunderboltOutlined />, label: '推理测试台' },
  { key: '/logs', icon: <FileTextOutlined />, label: '请求日志' },
  { key: '/keys', icon: <KeyOutlined />, label: 'API Key' },
]

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  // /deployments/3 也选中「部署管理」
  const selectedKey =
    MENU.map((m) => m.key)
      .filter((key) => key !== '/' && location.pathname.startsWith(key))
      .pop() ?? '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} trigger={null} theme="dark" width={216}>
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            color: '#fff',
            fontWeight: 600,
            fontSize: collapsed ? 18 : 16,
            letterSpacing: 0.5,
          }}
        >
          <ApiOutlined style={{ fontSize: 20, color: '#4096ff' }} />
          {!collapsed && <span>LLM Deploy</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={MENU}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((c) => !c)}
          />
          <Space size="middle">
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              大模型部署推理管理平台
            </Typography.Text>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出登录',
                    onClick: () => {
                      logout()
                      navigate('/login')
                    },
                  },
                ],
              }}
            >
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size="small" icon={<UserOutlined />} />
                <span>{user?.username}</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <Content style={{ padding: 20, background: '#f5f7fa' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
