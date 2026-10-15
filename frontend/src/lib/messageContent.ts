import type { VeridianVisual } from '@/components/chat/visuals/types';

export interface AssistantStructuredContent {
  message_type: 'assistant_response';
  answer: string;
  response_mode?: 'text' | 'visual';
  visual?: VeridianVisual | null;
  next_step_suggestions?: string[];
  analysis_type?: string | null;
  analytics?: Record<string, unknown> | null;
  error?: string | null;
}

export interface ParsedAssistantMessage {
  answer: string;
  visual: VeridianVisual | null;
  nextStepSuggestions?: string[];
  analysisType?: string | null;
  analytics?: Record<string, unknown> | null;
}

/**
 * Safely parse an assistant message stored in DB.
 * Supports both legacy plain-text messages and the new structured JSON payload.
 */
export function parseAssistantContent(raw: string): ParsedAssistantMessage {
  if (!raw) {
    return { answer: '', visual: null };
  }
  const trimmed = raw.trim();

  // Attempt JSON parse if looks like object
  if (trimmed.startsWith('{')) {
    try {
      const obj = JSON.parse(trimmed) as Partial<AssistantStructuredContent>;
      if (obj && typeof obj.answer === 'string' && obj.answer.trim()) {
        const visual =
          obj.response_mode === 'visual' && obj.visual ? (obj.visual as VeridianVisual) : null;
        return {
          answer: obj.answer,
          visual,
          nextStepSuggestions:
            Array.isArray(obj.next_step_suggestions) && obj.next_step_suggestions.length > 0
              ? obj.next_step_suggestions
              : undefined,
          analysisType: obj.analysis_type ?? null,
          analytics: obj.analytics ?? null,
        };
      }
      // JSON parsed but no valid answer field — show nothing rather than JSON cru
      return { answer: '', visual: null };
    } catch {
      // JSON parse failed — check if it's markdown text that starts with {
      // (unlikely but safe)
    }
  }

  // Plain text fallback — but never show raw JSON strings to the user
  // If content looks like a serialized object that failed to parse, hide it
  if (trimmed.includes('"message_type"') || trimmed.includes('"answer"')) {
    return { answer: '', visual: null };
  }

  return { answer: raw, visual: null };
}

/**
 * Serialize an assistant response into the structured format we persist in DB.
 * This ensures future reloads can rehydrate visuals + suggestions.
 */
export function serializeAssistantContent(payload: AssistantStructuredContent): string {
  return JSON.stringify({
    message_type: 'assistant_response',
    answer: payload.answer,
    response_mode: payload.response_mode ?? (payload.visual ? 'visual' : 'text'),
    visual: payload.visual ?? null,
    next_step_suggestions: payload.next_step_suggestions ?? [],
    analysis_type: payload.analysis_type ?? null,
    analytics: payload.analytics ?? null,
    error: payload.error ?? null,
  });
}
