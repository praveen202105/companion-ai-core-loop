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

export type MemoryEvent = {
  id: string;
  action: "add" | "update" | "supersede" | "ignore" | "extraction_failed";
  canonical_key: string | null;
  reason_code: string;
  created_at: string;
};

export type RetrievalSelection = {
  memory_id: string;
  canonical_key: string;
  score: number;
  factors: Record<string, number>;
};

export type MemoryInspectorPayload = {
  memories: MemorySummary[];
  events: MemoryEvent[];
  trace: {
    selected: RetrievalSelection[];
    candidate_count: number;
    degraded_mode: string | null;
  } | null;
};
