const ONBOARDING_STORAGE_KEYS = {
  done: "agentlens_onboarding_done",
  promptCopied: "agentlens_onboarding_prompt_copied",
  annotationsSeen: "agentlens_onboarding_annotations_seen",
} as const;

export function isOnboardingDone(): boolean {
  return readBooleanFlag(ONBOARDING_STORAGE_KEYS.done);
}

export function markOnboardingDone(): void {
  writeBooleanFlag(ONBOARDING_STORAGE_KEYS.done);
}

export function didCopyAgentPrompt(): boolean {
  return readBooleanFlag(ONBOARDING_STORAGE_KEYS.promptCopied);
}

export function markAgentPromptCopied(): void {
  writeBooleanFlag(ONBOARDING_STORAGE_KEYS.promptCopied);
}

export function hasSeenAnnotations(): boolean {
  return readBooleanFlag(ONBOARDING_STORAGE_KEYS.annotationsSeen);
}

export function markAnnotationsSeen(): void {
  writeBooleanFlag(ONBOARDING_STORAGE_KEYS.annotationsSeen);
}

function readBooleanFlag(key: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(key) === "true";
}

function writeBooleanFlag(key: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(key, "true");
}
