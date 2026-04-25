# @agentlens/code-renderer

Syntax-highlighted code block renderer for AgentLens cells and dialogs.

## Install

```sh
pnpm add @agentlens/code-renderer
```

This package expects React 18 or newer as a peer dependency.

## API

```tsx
import { CodeRenderer } from "@agentlens/code-renderer";

<CodeRenderer code={"select * from traces"} language="sql" showLineNumbers />;
```

### `CodeRendererProps`

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `code` | `string` | required | Source code to display. |
| `language` | `"sql" \| "python" \| "javascript" \| "typescript" \| "json" \| "plain" \| string` | required | Highlight.js language key. Unsupported languages render as escaped plain text. |
| `maxHeight` | `number` | `undefined` | Adds an internal vertical scroll limit when set. |
| `showLineNumbers` | `boolean` | `false` | Shows stable line numbers beside the highlighted code. |

## Behavior

- Uses `highlight.js/lib/core` and pre-registers SQL, Python, JavaScript, TypeScript, JSON, and plain text.
- Includes a copy button for the raw code.
- Unknown languages do not throw; they render safely as plain escaped text.
- Imports `highlight.js/styles/github.css` through `src/styles.css`.
