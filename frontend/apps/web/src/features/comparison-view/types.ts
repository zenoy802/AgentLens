export type ColumnDisplayMode = "all" | "user-assistant" | "assistant" | "custom";

export const COLUMN_WIDTH_PRESETS = [300, 400, 500] as const;
export const DEFAULT_COLUMN_WIDTH = 400;
export const MIN_COLUMN_WIDTH = 300;
export const MAX_COLUMN_WIDTH = 600;
