let suppressedUntil = 0

export function suppressRowInteractions(durationMs = 300) {
  suppressedUntil = Date.now() + durationMs
}

export function areRowInteractionsSuppressed() {
  return Date.now() < suppressedUntil
}
