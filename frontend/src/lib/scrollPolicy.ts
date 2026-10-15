export function streamScrollBehavior(isStreaming: boolean): ScrollBehavior {
  return isStreaming ? "auto" : "smooth"
}
