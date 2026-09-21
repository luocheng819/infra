import { ClearOutlined, SendOutlined, StopOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Segmented,
  Select,
  Slider,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { deploymentApi } from '../api'
import { http, errorMessage } from '../api/client'
import type { CompletionResponse, Deployment } from '../api/types'
import { usePolling } from '../hooks/usePolling'
import { useStream } from '../hooks/useStream'

interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export default function PlaygroundPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [mode, setMode] = useState<'chat' | 'completion'>('chat')
  const [deploymentId, setDeploymentId] = useState<number | undefined>(
    searchParams.get('deployment') ? Number(searchParams.get('deployment')) : undefined,
  )

  const [streamEnabled, setStreamEnabled] = useState(true)
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(512)

  const [chatInput, setChatInput] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('你是一个乐于助人的运维助手。')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [completionInput, setCompletionInput] = useState('')
  const [completionOutput, setCompletionOutput] = useState('')
  const [busy, setBusy] = useState(false)
  const [lastMeta, setLastMeta] = useState<{ latency: number; tokens: number } | null>(null)

  const outputRef = useRef<HTMLDivElement>(null)
  const { streaming, start, stop } = useStream()

  const deployments = usePolling(() => deploymentApi.list('running'), 8000)
  const running = useMemo(() => deployments.data ?? [], [deployments.data])

  // 未显式指定时自动选中第一个运行中的部署
  useEffect(() => {
    if (!deploymentId && running.length > 0) {
      setDeploymentId(running[0].id)
    }
  }, [running, deploymentId])

  useEffect(() => {
    if (deploymentId) setSearchParams({ deployment: String(deploymentId) }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deploymentId])

  useEffect(() => {
    outputRef.current?.scrollTo({ top: outputRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, completionOutput])

  const current: Deployment | undefined = running.find((d) => d.id === deploymentId)

  // ------------------------------------------------------------------ #
  const sendChat = async () => {
    const text = chatInput.trim()
    if (!text || !deploymentId) return
    const history: ChatTurn[] = [...turns, { role: 'user', content: text }]
    setTurns(history)
    setChatInput('')
    setBusy(true)

    const messages = [
      ...(systemPrompt.trim() ? [{ role: 'system', content: systemPrompt }] : []),
      ...history.map((t) => ({ role: t.role, content: t.content })),
    ]
    const body = {
      messages,
      temperature,
      max_tokens: maxTokens,
      stream: streamEnabled,
    }
    const url = `/api/inference/${deploymentId}/chat/completions`

    if (streamEnabled) {
      // 先占位一条空回复，再逐块填充
      setTurns((prev) => [...prev, { role: 'assistant', content: '' }])
      await start(url, body, {
        onDelta: (chunk) =>
          setTurns((prev) => {
            const next = [...prev]
            next[next.length - 1] = {
              role: 'assistant',
              content: next[next.length - 1].content + chunk,
            }
            return next
          }),
        onDone: (info) =>
          setLastMeta({ latency: info.latency_ms ?? 0, tokens: 0 }),
        onError: (msg) => {
          message.error(msg)
          setTurns((prev) => prev.slice(0, -1))
        },
      })
    } else {
      try {
        const { data } = await http.post<CompletionResponse>(url, body)
        setTurns((prev) => [...prev, { role: 'assistant', content: data.text }])
        setLastMeta({
          latency: 0,
          tokens: data.usage.total_tokens,
        })
      } catch (err) {
        message.error(errorMessage(err))
        setTurns((prev) => prev.slice(0, -1))
      }
    }
    setBusy(false)
  }

  const sendCompletion = async () => {
    const text = completionInput.trim()
    if (!text || !deploymentId) return
    setCompletionOutput('')
    setBusy(true)

    const body = { prompt: text, temperature, max_tokens: maxTokens, stream: streamEnabled }
    const url = `/api/inference/${deploymentId}/completions`

    if (streamEnabled) {
      await start(url, body, {
        onDelta: (chunk) => setCompletionOutput((prev) => prev + chunk),
        onDone: (info) => setLastMeta({ latency: info.latency_ms ?? 0, tokens: 0 }),
        onError: (msg) => message.error(msg),
      })
    } else {
      try {
        const { data } = await http.post<CompletionResponse>(url, body)
        setCompletionOutput(data.text)
        setLastMeta({ latency: 0, tokens: data.usage.total_tokens })
      } catch (err) {
        message.error(errorMessage(err))
      }
    }
    setBusy(false)
  }

  const disabled = !deploymentId || busy

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          推理测试台
        </Typography.Title>
        <Typography.Text type="secondary">
          直接对运行中的部署发起推理，验证模型效果与接口连通性。支持流式输出。
        </Typography.Text>
      </div>

      {running.length === 0 && !deployments.loading && (
        <Alert
          type="warning"
          showIcon
          message="没有运行中的部署"
          description="请先到「部署管理」创建一个部署并启动，然后回到这里测试。"
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7}>
          <Card title="请求配置" size="small">
            <Form layout="vertical" size="small">
              <Form.Item label="目标部署" style={{ marginBottom: 12 }}>
                <Select
                  placeholder="选择运行中的部署"
                  value={deploymentId}
                  onChange={setDeploymentId}
                  options={running.map((d) => ({
                    value: d.id,
                    label: `${d.name} · ${d.model_name || d.engine}`,
                  }))}
                />
              </Form.Item>

              <Form.Item label="模式" style={{ marginBottom: 12 }}>
                <Segmented
                  block
                  value={mode}
                  onChange={(v) => setMode(v as 'chat' | 'completion')}
                  options={[
                    { label: '对话', value: 'chat' },
                    { label: '文本补全', value: 'completion' },
                  ]}
                />
              </Form.Item>

              {mode === 'chat' && (
                <Form.Item label="系统提示词" style={{ marginBottom: 12 }}>
                  <Input.TextArea
                    rows={2}
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                  />
                </Form.Item>
              )}

              <Form.Item label={`温度 (${temperature})`} style={{ marginBottom: 12 }}>
                <Slider
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={setTemperature}
                />
              </Form.Item>

              <Form.Item label="最大生成长度" style={{ marginBottom: 12 }}>
                <InputNumber
                  min={1}
                  max={8192}
                  value={maxTokens}
                  onChange={(v) => setMaxTokens(v ?? 512)}
                  style={{ width: '100%' }}
                />
              </Form.Item>

              <Form.Item label="输出方式" style={{ marginBottom: 0 }}>
                <Segmented
                  block
                  value={streamEnabled ? 'stream' : 'once'}
                  onChange={(v) => setStreamEnabled(v === 'stream')}
                  options={[
                    { label: '流式', value: 'stream' },
                    { label: '一次性', value: 'once' },
                  ]}
                />
              </Form.Item>
            </Form>
          </Card>

          {current && (
            <Card title="实例信息" size="small" style={{ marginTop: 16 }}>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <div>
                  <Typography.Text type="secondary">引擎：</Typography.Text>{' '}
                  <Tag color="blue">{current.engine}</Tag>
                </div>
                <div>
                  <Typography.Text type="secondary">模型：</Typography.Text> {current.model_name}
                </div>
                <div>
                  <Typography.Text type="secondary">端口：</Typography.Text> {current.host_port}
                </div>
                <div>
                  <Typography.Text type="secondary">OpenAI 模型名：</Typography.Text>
                  <Typography.Text copyable>{current.name}</Typography.Text>
                </div>
              </Space>
            </Card>
          )}

          {lastMeta && (
            <Card title="上次调用" size="small" style={{ marginTop: 16 }}>
              <Space direction="vertical" size={2}>
                <span>耗时：{lastMeta.latency.toFixed(0)} ms</span>
                {lastMeta.tokens > 0 && <span>Token：{lastMeta.tokens}</span>}
              </Space>
            </Card>
          )}
        </Col>

        <Col xs={24} lg={17}>
          <Card
            title={mode === 'chat' ? '对话' : '文本补全'}
            extra={
              <Space>
                {streaming && (
                  <Button danger icon={<StopOutlined />} onClick={stop}>
                    中断
                  </Button>
                )}
                <Button
                  icon={<ClearOutlined />}
                  onClick={() => {
                    setTurns([])
                    setCompletionOutput('')
                    setLastMeta(null)
                  }}
                >
                  清空
                </Button>
              </Space>
            }
          >
            {mode === 'chat' ? (
              <div
                ref={outputRef}
                style={{
                  height: 420,
                  overflowY: 'auto',
                  padding: 12,
                  background: '#fafafa',
                  borderRadius: 8,
                  marginBottom: 12,
                }}
              >
                {turns.length === 0 ? (
                  <Empty description="发送一条消息开始测试" style={{ marginTop: 120 }} />
                ) : (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {turns.map((turn, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          justifyContent: turn.role === 'user' ? 'flex-end' : 'flex-start',
                        }}
                      >
                        <div
                          style={{
                            maxWidth: '78%',
                            padding: '9px 13px',
                            borderRadius: 10,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            background: turn.role === 'user' ? '#1677ff' : '#fff',
                            color: turn.role === 'user' ? '#fff' : 'inherit',
                            border: turn.role === 'user' ? 'none' : '1px solid #f0f0f0',
                          }}
                        >
                          {turn.content || (streaming ? '▌' : '')}
                        </div>
                      </div>
                    ))}
                  </Space>
                )}
              </div>
            ) : (
              <>
                <Input.TextArea
                  rows={5}
                  placeholder="输入提示词，例如：用三句话解释什么是模型量化"
                  value={completionInput}
                  onChange={(e) => setCompletionInput(e.target.value)}
                  style={{ marginBottom: 12 }}
                />
                {completionOutput && (
                  <div
                    style={{
                      minHeight: 200,
                      maxHeight: 360,
                      overflowY: 'auto',
                      padding: 12,
                      background: '#fafafa',
                      borderRadius: 8,
                      whiteSpace: 'pre-wrap',
                      marginBottom: 12,
                      border: '1px solid #f0f0f0',
                    }}
                  >
                    {completionOutput}
                  </div>
                )}
              </>
            )}

            <Space.Compact style={{ width: '100%' }}>
              {mode === 'chat' ? (
                <Input
                  placeholder="输入消息，回车发送"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onPressEnter={sendChat}
                  disabled={disabled || streaming}
                />
              ) : (
                <Input
                  placeholder="输入提示词，回车发送"
                  value={completionInput}
                  onChange={(e) => setCompletionInput(e.target.value)}
                  onPressEnter={sendCompletion}
                  disabled={disabled || streaming}
                />
              )}
              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={busy || streaming}
                disabled={!deploymentId}
                onClick={mode === 'chat' ? sendChat : sendCompletion}
              >
                发送
              </Button>
            </Space.Compact>
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
