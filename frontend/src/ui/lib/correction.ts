/** Pure visibility policy, shared by runtime and validator offers. */
export function canRequestCorrection(enabled: boolean, requested: boolean, errors: number, runtime: boolean): boolean {
  return enabled && !requested && (errors > 0 || runtime)
}
