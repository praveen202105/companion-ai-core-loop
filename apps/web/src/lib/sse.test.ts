import { describe, expect, it } from "vitest";

import type { SSEEvent } from "./contracts";
import { consumeSSE } from "./sse";

describe("consumeSSE", () => {
  it("parses events split across network chunks", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: message.delta\ndata: {"del'));
        controller.enqueue(encoder.encode('ta":"Hello"}\n\nevent: message.completed\n'));
        controller.enqueue(encoder.encode('data: {"id":"message-1"}\n\n'));
        controller.close();
      },
    });
    const events: SSEEvent[] = [];

    await consumeSSE(new Response(stream), (event) => events.push(event));

    expect(events).toEqual([
      { event: "message.delta", data: { delta: "Hello" } },
      { event: "message.completed", data: { id: "message-1" } },
    ]);
  });
});
