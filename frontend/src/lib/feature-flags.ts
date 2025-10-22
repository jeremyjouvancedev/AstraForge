const flags = new Map<string, boolean>();

export function setFeatureFlag(flag: string, enabled: boolean) {
  flags.set(flag, enabled);
}

export function isFeatureEnabled(flag: string) {
  return flags.get(flag) ?? false;
}

setFeatureFlag("diff-view", true);
setFeatureFlag("test-report", true);
