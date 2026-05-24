export const locallyHandledMutationMeta = {
  suppressGlobalErrorToast: true,
} as const;

export function suppressesGlobalErrorToast(
  meta: Record<string, unknown> | undefined,
): boolean {
  return meta?.suppressGlobalErrorToast === true;
}
