import { describe, expect, it, vi } from 'vitest';
import {
  REALTIME_TOOL_NAME,
  RealtimeEventRouter,
  parseToolQuestion,
  type RealtimeClientEvent,
  type RealtimeVoiceState,
} from '@/lib/realtimeVoice';

function setup(answer: string | null = 'O gasto foi de 240 milhões de reais.') {
  const sent: RealtimeClientEvent[] = [];
  const states: RealtimeVoiceState[] = [];
  const onToolCall = vi.fn(async () => answer);
  const router = new RealtimeEventRouter({
    send: (event) => sent.push(event),
    onState: (state) => states.push(state),
    onToolCall,
  });
  return { router, sent, states, onToolCall };
}

function toolCall(callId: string, question: string, name = REALTIME_TOOL_NAME) {
  return {
    type: 'response.function_call_arguments.done',
    call_id: callId,
    name,
    arguments: JSON.stringify({ pergunta: question }),
  };
}

describe('parseToolQuestion', () => {
  it('reads the question from the JSON arguments', () => {
    expect(parseToolQuestion('{"pergunta":"  Quanto foi gasto em 2025? "}')).toBe(
      'Quanto foi gasto em 2025?',
    );
  });

  it('returns empty for invalid or missing arguments', () => {
    expect(parseToolQuestion('not json')).toBe('');
    expect(parseToolQuestion('{}')).toBe('');
    expect(parseToolQuestion(undefined)).toBe('');
  });
});

describe('RealtimeEventRouter', () => {
  it('answers a data question through the tool and asks for a new response', async () => {
    const { router, sent, states, onToolCall } = setup();
    await router.handle(toolCall('call_1', 'Quanto foi gasto em 2025?'));

    expect(onToolCall).toHaveBeenCalledWith('Quanto foi gasto em 2025?');
    expect(states).toContain('thinking');
    expect(sent).toHaveLength(2);
    expect(sent[0]).toMatchObject({
      type: 'conversation.item.create',
      item: { type: 'function_call_output', call_id: 'call_1' },
    });
    const output = JSON.parse((sent[0].item as { output: string }).output);
    expect(output).toEqual({ resposta: 'O gasto foi de 240 milhões de reais.' });
    expect(sent[1]).toEqual({ type: 'response.create' });
  });

  it('waits for response.done before asking for a new response', async () => {
    const { router, sent } = setup();
    await router.handle({ type: 'response.created' });
    await router.handle(toolCall('call_2', 'Quem mais gastou?'));

    expect(sent.map((e) => e.type)).toEqual(['conversation.item.create']);

    await router.handle({ type: 'response.done', response: { output: [] } });
    expect(sent.map((e) => e.type)).toEqual(['conversation.item.create', 'response.create']);
  });

  it('handles each call only once (args event and response.done)', async () => {
    const { router, onToolCall } = setup();
    const call = toolCall('call_3', 'Quanto em 2024?');
    await router.handle(call);
    await router.handle({
      type: 'response.done',
      response: {
        output: [
          { type: 'function_call', call_id: 'call_3', name: REALTIME_TOOL_NAME, arguments: call.arguments },
        ],
      },
    });
    expect(onToolCall).toHaveBeenCalledTimes(1);
  });

  it('reports an error to the model when the query fails', async () => {
    const { router, sent } = setup(null);
    await router.handle(toolCall('call_4', 'Quanto em 2023?'));
    const output = JSON.parse((sent[0].item as { output: string }).output);
    expect(output.erro).toBeTruthy();
    expect(output.resposta).toBeUndefined();
  });

  it('rejects an empty question without calling the data', async () => {
    const { router, sent, onToolCall } = setup();
    await router.handle({
      type: 'response.function_call_arguments.done',
      call_id: 'call_5',
      name: REALTIME_TOOL_NAME,
      arguments: '{}',
    });
    expect(onToolCall).not.toHaveBeenCalled();
    expect(JSON.parse((sent[0].item as { output: string }).output).erro).toBeTruthy();
  });

  it('maps audio events to voice states', async () => {
    const { router, states } = setup();
    await router.handle({ type: 'session.created' });
    await router.handle({ type: 'output_audio_buffer.started' });
    await router.handle({ type: 'output_audio_buffer.stopped' });
    expect(states).toEqual(['listening', 'speaking', 'listening']);
  });
});
