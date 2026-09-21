import { useEffect, useRef, useState } from 'react'

/**
 * 定时轮询。用于部署列表、指标与日志这类需要准实时刷新的数据。
 * 返回的 refresh 可手动触发一次立即刷新。
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  deps: unknown[] = [],
): { data: T | null; error: string | null; loading: boolean; refresh: () => void } {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const [tick, setTick] = useState(0)
  const refresh = () => setTick((t) => t + 1)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const run = async () => {
      try {
        const result = await fetcherRef.current()
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message ?? '加载失败')
      } finally {
        if (!cancelled) {
          setLoading(false)
          if (intervalMs > 0) timer = window.setTimeout(run, intervalMs)
        }
      }
    }

    run()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps])

  return { data, error, loading, refresh }
}
