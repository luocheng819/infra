import { http, TOKEN_KEY } from './client'
import type {
  ApiKey,
  ApiKeyCreated,
  Deployment,
  DeploymentDetail,
  EngineInfo,
  LoginResponse,
  MetricsSummary,
  ModelInfo,
  OverviewStats,
  RequestLog,
  User,
} from './types'

export const authApi = {
  login: (username: string, password: string) =>
    http.post<LoginResponse>('/api/auth/login', { username, password }).then((r) => r.data),
  me: () => http.get<User>('/api/auth/me').then((r) => r.data),
  logout: () => localStorage.removeItem(TOKEN_KEY),
}

export const modelApi = {
  list: (params?: { q?: string; source?: string }) =>
    http.get<ModelInfo[]>('/api/models', { params }).then((r) => r.data),
  get: (id: number) => http.get<ModelInfo>(`/api/models/${id}`).then((r) => r.data),
  create: (payload: Partial<ModelInfo>) =>
    http.post<ModelInfo>('/api/models', payload).then((r) => r.data),
  update: (id: number, payload: Partial<ModelInfo>) =>
    http.patch<ModelInfo>(`/api/models/${id}`, payload).then((r) => r.data),
  remove: (id: number) => http.delete(`/api/models/${id}`).then((r) => r.data),
}

export const deploymentApi = {
  list: (status?: string) =>
    http.get<Deployment[]>('/api/deployments', { params: { status } }).then((r) => r.data),
  get: (id: number) =>
    http.get<DeploymentDetail>(`/api/deployments/${id}`).then((r) => r.data),
  create: (payload: {
    name: string
    model_id: number
    engine: string
    replicas?: number
    engine_params?: Record<string, unknown>
  }) => http.post<Deployment>('/api/deployments', payload).then((r) => r.data),
  update: (id: number, payload: { replicas?: number; engine_params?: Record<string, unknown> }) =>
    http.patch<Deployment>(`/api/deployments/${id}`, payload).then((r) => r.data),
  start: (id: number) => http.post<Deployment>(`/api/deployments/${id}/start`).then((r) => r.data),
  stop: (id: number) => http.post<Deployment>(`/api/deployments/${id}/stop`).then((r) => r.data),
  restart: (id: number) =>
    http.post<Deployment>(`/api/deployments/${id}/restart`).then((r) => r.data),
  remove: (id: number) => http.delete(`/api/deployments/${id}`).then((r) => r.data),
  health: (id: number) =>
    http.get<{ healthy: boolean; status: string }>(`/api/deployments/${id}/health`).then((r) => r.data),
}

export const metricsApi = {
  forDeployment: (id: number, minutes = 30) =>
    http
      .get<MetricsSummary>(`/api/deployments/${id}/metrics`, { params: { minutes } })
      .then((r) => r.data),
  summary: () => http.get('/api/metrics/summary').then((r) => r.data),
  logs: (id: number, params?: { limit?: number; status?: string }) =>
    http.get<RequestLog[]>(`/api/deployments/${id}/logs`, { params }).then((r) => r.data),
  allLogs: (params?: { limit?: number; deployment_id?: number; status?: string }) =>
    http.get<RequestLog[]>('/api/logs', { params }).then((r) => r.data),
}

export const engineApi = {
  list: () => http.get<EngineInfo[]>('/api/engines').then((r) => r.data),
}

export const overviewApi = {
  get: () => http.get<OverviewStats>('/api/overview').then((r) => r.data),
}

export const keyApi = {
  list: () => http.get<ApiKey[]>('/api/keys').then((r) => r.data),
  create: (name: string) => http.post<ApiKeyCreated>('/api/keys', { name }).then((r) => r.data),
  toggle: (id: number) => http.post<ApiKey>(`/api/keys/${id}/toggle`).then((r) => r.data),
  remove: (id: number) => http.delete(`/api/keys/${id}`).then((r) => r.data),
}
