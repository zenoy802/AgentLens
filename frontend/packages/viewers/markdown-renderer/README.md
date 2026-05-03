# @agentlens/markdown-renderer

Markdown renderer for AgentLens cells, dialogs, and embedded trajectory views.

## Install

```sh
pnpm add @agentlens/markdown-renderer
```

This package expects React 18 or newer as a peer dependency.

## API

```tsx
import { MarkdownRenderer } from "@agentlens/markdown-renderer";

<MarkdownRenderer
  content={"# Result\n\n```sql\nselect * from traces\n```"}
  maxHeight={520}
/>;
```

### `MarkdownRendererProps`

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `content` | `string` | required | Markdown source to render. |
| `className` | `string` | `undefined` | Optional wrapper class. |
| `maxHeight` | `number` | `undefined` | Adds an internal vertical scroll area when set. |

## Behavior

- Uses `react-markdown`, `remark-gfm`, and `rehype-highlight`.
- Supports GFM tables.
- Opens links in a new tab with `rel="noopener"`.
- Caps images at `max-width: 100%`.
- Imports `highlight.js/styles/github.css` through `src/styles.css`.
