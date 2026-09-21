import { useEffect, useRef, useState } from 'react'
import { TOKEN_KEY } from '../api/client'

export interface StreamHandlers {
  onDelta: (text: string) => void
  onDone?: (info: { latency_ms: number }) => void
  onError?: (message: string) => void
}

/**
 * 调用控制台的流式接口并解析 SSE。
 *
 * 这里没有用 EventSource，因为它不支持 POST；改用 fetch + ReadableStream 手动切帧。
 */
export function useStream() {
  const [streaming, setStreaming] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => controllerRef.current?.abort(), [])

  const start = async (
    url: string,
    body: unknown,
    handlers: StreamHandlers,
  ): Promise<void> => {
    const controller = new AbortController()
    controllerRef.current = controller
    setStreaming(true)

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY) ?? ''}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!resp.ok) {
        const text = await resp.text()
        let message = `请求失败（${resp.status}）`
        try {
          message = JSON.parse(text).detail ?? message
        } catch {
          /* 保持默认文案 */
        }
        handlers.onError?.(message)
        return
      }
      if (!resp.body) {
        handlers.onError?.('响应不支持流式读取')
        return
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE 以空行分隔事件
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          const eventLine = frame.split('\n').find((l) => l.startsWith('event:'))
          const dataLine = frame.split('\n').find((l) => l.startsWith('data:'))
          if (!dataLine) continue
          const event = eventLine?.slice(6).trim() ?? 'message'
          let payload: Record<string, unknown>
          try {
            payload = JSON.parse(dataLine.slice(5).trim())
          } catch {
            continue
          }
          if (event === 'delta' && typeof payload.text === 'string') {
            handlers.onDelta(payload.text)
          } else if (event === 'done') {
            handlers.onDone?.(payload as { latency_ms: number })
          } else if (event === 'error') {
            handlers.onError?.(String(payload.message ?? '推理中断'))
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        handlers.onError?.((err as Error).message)
      }
    } finally {
      setStreaming(false)
      controllerRef.current = null
    }
  }

  const stop = () => controllerRef.current?.abort()

  return { streaming, start, stop }
}
