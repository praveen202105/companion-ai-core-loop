import type { SSEEvent } from "./contracts";

export async function consumeSSE(
  response: Response,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  if (!response.ok || !response.body) {
    throw new Error(`Stream request failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) parseFrame(frame, onEvent);
    if (done) break;
  }
  if (buffer.trim()) parseFrame(buffer, onEvent);
}

function parseFrame(frame: string, onEvent: (event: SSEEvent) => void): void {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!data.length) return;
  onEvent({ event, data: JSON.parse(data.join("\n")) as Record<string, unknown> });
}
