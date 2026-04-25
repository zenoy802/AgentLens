# @agentlens/json-renderer

Collapsible JSON tree renderer for AgentLens cells, dialogs, and embedded views.

## Install

```sh
pnpm add @agentlens/json-renderer
```

This package expects React 18 or newer as a peer dependency.

## API

```tsx
import { JsonRenderer } from "@agentlens/json-renderer";

<JsonRenderer value={{ ok: true, items: [1, 2, 3] }} collapsed maxDepth={10} />;
```

### `JsonRendererProps`

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `value` | `unknown` | required | Already parsed JSON-like value. |
| `collapsed` | `boolean` | `true` | Initial collapse state for expandable nodes. |
| `maxDepth` | `number` | `10` | Nodes at or beyond this depth render as `...` until expanded. |
| `className` | `string` | `undefined` | Optional wrapper class. |

## Behavior

- Renders objects and arrays recursively.
- Each nested object/array has independent collapse state.
- Colors primitives by type: string, number, boolean, and null.
- Shows object and array summaries while collapsed.
- Includes a copy button for the full JSON payload.
- Handles bigint and circular references when stringifying for copy.
