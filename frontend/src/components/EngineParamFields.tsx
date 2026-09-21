import { Checkbox, Form, Input, InputNumber, Select } from 'antd'
import type { ParamField } from '../api/types'

/**
 * 依据引擎自描述的 param_schema 动态渲染部署参数表单。
 *
 * 新增引擎时前端无需改动 —— 这是「可插拔」在前端的落点。
 */
export function EngineParamFields({ schema }: { schema: ParamField[] }) {
  return (
    <>
      {schema.map((field) => {
        const rules = field.required
          ? [{ required: true, message: `请填写${field.label}` }]
          : undefined
        const help = field.help

        let control: React.ReactNode
        switch (field.type) {
          case 'int':
          case 'float':
            control = (
              <InputNumber
                style={{ width: '100%' }}
                min={field.min}
                max={field.max}
                step={field.step ?? (field.type === 'int' ? 1 : 0.05)}
                placeholder={String(field.default ?? '')}
              />
            )
            break
          case 'bool':
            control = <Checkbox />
            break
          case 'select':
            control = (
              <Select
                allowClear
                options={(field.options ?? []).map((o) => ({
                  value: o,
                  label: o === '' ? '（不指定）' : o,
                }))}
              />
            )
            break
          case 'password':
            control = <Input.Password placeholder={String(field.default ?? '')} />
            break
          default:
            control = <Input placeholder={String(field.default ?? '')} />
        }

        return (
          <Form.Item
            key={field.key}
            name={['engine_params', field.key]}
            label={field.label}
            rules={rules}
            tooltip={help}
            valuePropName={field.type === 'bool' ? 'checked' : 'value'}
          >
            {control}
          </Form.Item>
        )
      })}
    </>
  )
}
