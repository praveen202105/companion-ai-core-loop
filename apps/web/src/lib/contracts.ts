export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type SSEEvent = {
  event: string;
  data: Record<string, unknown>;
};

export type MemorySummary = {
  id: string;
  canonical_key: string;
  memory_type: string;
  normalized_text: string;
  value: string;
  status: "active" | "superseded" | "expired";
  confidence: number;
  importance: number;
};
