/** 与后端 schemas.py 一一对应的类型定义。 */

export type DeploymentStatus =
  | 'pending'
  | 'starting'
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'failed'

export type ModelSource = 'local' | 'huggingface' | 'modelscope'

export interface User {
  id: number
  username: string
  email: string | null
  is_admin: boolean
  created_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface ModelInfo {
  id: number
  name: string
  display_name: string
  description: string
  source: ModelSource
  source_ref: string
  revision: string
  parameter_count: string | null
  quantization: string | null
  size_bytes: number
  tags: string[]
  default_engine_params: Record<string, unknown>
  created_at: string
  updated_at: string
  deployment_count: number
}

export interface Deployment {
  id: number
  name: string
  model_id: number
  model_name: string
  engine: string
  status: DeploymentStatus
  replicas: number
  host_port: number | null
  endpoint: string | null
  engine_params: Record<string, unknown>
  runtime: Record<string, unknown>
  error_message: string | null
  created_by: string | null
  created_at: string
  started_at: string | null
  stopped_at: string | null
}

export interface DeploymentEvent {
  id: number
  level: string
  event: string
  message: string
  created_at: string
}

export interface DeploymentDetail extends Deployment {
  events: DeploymentEvent[]
}

export interface ParamField {
  key: string
  label: string
  type: 'string' | 'int' | 'float' | 'bool' | 'select' | 'password'
  default?: unknown
  min?: number
  max?: number
  step?: number
  options?: string[]
  required?: boolean
  help?: string
}

export interface EngineInfo {
  name: string
  display_name: string
  description: string
  available: boolean
  requires_gpu: boolean
  default_params: Record<string, unknown>
  param_schema: ParamField[]
}

export interface Usage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface CompletionResponse {
  id: string
  deployment: string
  model: string
  text: string
  finish_reason: string
  usage: Usage
  latency_ms: number
}

export interface MetricSample {
  timestamp: string
  qps: number
  tokens_per_second: number
  latency_p50_ms: number
  latency_p95_ms: number
  gpu_utilization: number
  gpu_memory_used_mb: number
  gpu_memory_total_mb: number
  total_requests: number
  failed_requests: number
  running_requests: number
  queue_depth: number
}

export interface MetricsSummary {
  deployment_id: number
  current: MetricSample | null
  samples: MetricSample[]
}

export interface RequestLog {
  id: number
  deployment_id: number
  request_id: string
  prompt_preview: string
  stream: boolean
  status: string
  error: string | null
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number
  created_at: string
}

export interface ApiKey {
  id: number
  name: string
  prefix: string
  owner: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export interface ApiKeyCreated extends ApiKey {
  key: string
}

export interface OverviewStats {
  total_models: number
  total_deployments: number
  running_deployments: number
  failed_deployments: number
  total_requests: number
  requests_last_hour: number
  failure_rate: number
  avg_latency_ms: number
  total_tokens: number
  engines: string[]
}
