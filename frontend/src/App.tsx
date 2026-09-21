import { Spin } from 'antd'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import AppLayout from './layouts/AppLayout'
import DashboardPage from './pages/DashboardPage'
import DeploymentDetailPage from './pages/DeploymentDetailPage'
import DeploymentsPage from './pages/DeploymentsPage'
import KeysPage from './pages/KeysPage'
import LoginPage from './pages/LoginPage'
import LogsPage from './pages/LogsPage'
import ModelsPage from './pages/ModelsPage'
import PlaygroundPage from './pages/PlaygroundPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 160 }}>
        <Spin size="large" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="deployments" element={<DeploymentsPage />} />
        <Route path="deployments/:id" element={<DeploymentDetailPage />} />
        <Route path="playground" element={<PlaygroundPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="keys" element={<KeysPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
