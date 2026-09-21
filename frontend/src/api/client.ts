import axios, { type AxiosError } from 'axios'

export const TOKEN_KEY = 'llmd_token'

export const http = axios.create({ baseURL: '', timeout: 60_000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<{ detail?: string }>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      // 避免在登录页反复跳转
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

/** 把后端返回的错误转成可直接展示的文案。 */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      // FastAPI 参数校验错误
      return detail
        .map((d) => {
          const item = d as { loc?: unknown[]; msg?: string }
          const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
          return field ? `${field}: ${item.msg}` : item.msg
        })
        .join('；')
    }
    if (error.code === 'ECONNABORTED') return '请求超时'
    if (!error.response) return '无法连接后端服务，请确认其已启动'
    return error.message
  }
  return String(error)
}
