# Labeling Guide

AgentLens 的 label 系统用于结构化人工标注。它适合沉淀可筛选、可导出、可统计的 review 结果。

## Label 和 Annotation 的区别

Label 是结构化人工标注。
Annotation 是人类或 agent 写入的视觉提示。
两者都基于 `query_id + row_identity`，但语义不同，不要混用。

常见区别：

- Label: case 分类、错误类型、人工评分、review note。
- Annotation: 高亮某行、解释 suspicious step、标出 agent finding、提示 stale/orphan。
- Label 通常参与导出、筛选、统计。
- Annotation 通常用于 UI 反向可视化和 agent write-back。

## Label schema 设计建议

一个 label schema 绑定到一个 query。建议字段少而稳定：

- 用 `single_select` 表达互斥状态。
- 用 `multi_select` 表达可叠加错误类型。
- 用 `text` 记录人工解释或补充证据。
- field key 使用稳定英文 snake_case，例如 `case_quality`。
- option 名称尽量固定，避免中途改名影响统计。

## single_select 示例

```json
{
  "key": "case_quality",
  "label": "Case Quality",
  "type": "single_select",
  "options": [
    { "value": "good", "label": "Good" },
    { "value": "bad", "label": "Bad" },
    { "value": "unclear", "label": "Unclear" }
  ]
}
```

适合：

- pass / fail
- good / bad / unclear
- high / medium / low

## multi_select 示例

```json
{
  "key": "failure_modes",
  "label": "Failure Modes",
  "type": "multi_select",
  "options": [
    { "value": "tool_error", "label": "Tool error" },
    { "value": "hallucination", "label": "Hallucination" },
    { "value": "missed_instruction", "label": "Missed instruction" },
    { "value": "format_error", "label": "Format error" },
    { "value": "timeout", "label": "Timeout" }
  ]
}
```

适合一条 trajectory 同时有多个问题的场景。

## text 示例

```json
{
  "key": "review_note",
  "label": "Review Note",
  "type": "text"
}
```

适合写人工解释、复现步骤、修复建议或具体证据。

## API payload 形状

`PUT /api/v1/queries/{query_id}/label-schema` 接受的 payload 是：

```json
{
  "fields": [
    {
      "key": "case_quality",
      "label": "Case Quality",
      "type": "single_select",
      "options": [
        { "value": "good", "label": "Good" },
        { "value": "bad", "label": "Bad" }
      ]
    }
  ]
}
```

UI 的字段编辑器使用同样的 `key`、`label`、`type`、`options[].value` 和 `options[].label` 概念。

## bad case 分类示例

推荐 schema：

```json
{
  "fields": [
    {
      "key": "case_quality",
      "label": "Case Quality",
      "type": "single_select",
      "options": [
        { "value": "good", "label": "Good" },
        { "value": "bad", "label": "Bad" },
        { "value": "unclear", "label": "Unclear" }
      ]
    },
    {
      "key": "bad_case_type",
      "label": "Bad Case Type",
      "type": "single_select",
      "options": [
        { "value": "reasoning", "label": "Reasoning" },
        { "value": "tool_use", "label": "Tool use" },
        { "value": "retrieval", "label": "Retrieval" },
        { "value": "instruction_following", "label": "Instruction following" },
        { "value": "format", "label": "Format" }
      ]
    },
    {
      "key": "review_note",
      "label": "Review Note",
      "type": "text"
    }
  ]
}
```

## 错误类型标注示例

```json
{
  "key": "error_types",
  "label": "Error Types",
  "type": "multi_select",
  "options": [
    { "value": "wrong_tool", "label": "Wrong tool" },
    { "value": "bad_arguments", "label": "Bad arguments" },
    { "value": "ignored_tool_result", "label": "Ignored tool result" },
    { "value": "unsupported_claim", "label": "Unsupported claim" },
    { "value": "unsafe_action", "label": "Unsafe action" },
    { "value": "premature_stop", "label": "Premature stop" }
  ]
}
```

## 人工评分示例

```json
{
  "fields": [
    {
      "key": "score_bucket",
      "label": "Score",
      "type": "single_select",
      "options": [
        { "value": "5", "label": "5" },
        { "value": "4", "label": "4" },
        { "value": "3", "label": "3" },
        { "value": "2", "label": "2" },
        { "value": "1", "label": "1" }
      ]
    },
    {
      "key": "score_reason",
      "label": "Score Reason",
      "type": "text"
    }
  ]
}
```

## 批量打标

批量打标适合对选中行设置同一个字段值：

1. 在表格中勾选多行。
2. 打开 Batch Label。
3. 选择字段和值。
4. 确认写入。

典型用法：

- 把筛选出的失败样本批量标为 `case_quality = bad`。
- 给一组相同失败模式写入 `failure_modes = tool_error`。
- 给抽样 review 批次写入 `review_note = sampled on 2026-06-01`。

## label filter

Label filter 用于快速查看某类样本：

- 只看 bad cases。
- 只看未标注行。
- 只看包含某个 failure mode 的行。
- 与 SQL 中的 eval 字段组合筛选。

如果筛选结果需要和外部 agent 共享，先选中这些行，再使用 Copy Agent Prompt 生成 selection snapshot。

## 导出打标结果

导出 CSV/Excel 时可以包含 label 结果。建议 release 前保存：

- 原始 rows
- labels
- SQL 和 query id
- 导出日期

Context Export 也会输出 `labels.jsonl`，供本地 agent 或脚本分析。
