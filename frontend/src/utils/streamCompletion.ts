type TerminalPayload = {
  status?: string;
  error_type?: string;
  error_message?: string;
};

const INCOMPLETE_NOTICE = 'Câu trả lời chưa hoàn tất. Vui lòng gửi lại câu hỏi.';

/** Transport EOF alone does not establish that the backend completed a stream. */
export function requireStreamTerminal(terminalReceived: boolean): void {
  if (!terminalReceived) throw new Error('INCOMPLETE_STREAM');
}

/** Preserve received text and make a failed terminal SSE payload visible. */
export function completeStream(
  eventType: 'done' | 'error',
  payload: TerminalPayload,
  content: string,
  alreadyFailed = false,
): { content: string; failed: boolean } {
  if (alreadyFailed) return { content, failed: true };
  const failed = eventType === 'error' || payload.status === 'api_error';
  if (!failed) return { content, failed: false };
  const message = content.trim() ? INCOMPLETE_NOTICE : (payload.error_message || INCOMPLETE_NOTICE);
  return { content: content.trim() ? `${content}\n\n${message}` : message, failed: true };
}
