import { useState, useCallback, useEffect } from 'react';
import { getApiClientHeaders } from '../utils/clientIdentity';

export interface Citation {
  chunk_id: string;
  content: string;
  relevant_excerpt?: string;
  metadata?: Record<string, unknown>;
  score?: number;
  title?: string;
  source_section?: string;
  source_pages?: number[];
  source_label?: string;
  source_url?: string;
  cohort?: string;
  applicability?: string;
  chunk_type?: string;
  parent_section_id?: string;
  article_label?: string;
  parent_article?: string;
  parent_title?: string;
  parent_content?: string;
  table_name?: string;
  detail_kind?: 'article' | 'table';
  canonical_source_id?: string;
  document_identity?: string;
  source_parent_id?: string;
}

export interface RelatedReference {
  id: string;
  primary_chunk_id: string;
  related_chunk_id: string;
  title: string;
  source_pages?: number[];
  source_url?: string;
  cohort?: string;
  graph_depth?: number;
  preview?: string;
  content?: string;
  relevant_excerpt?: string;
  article_label?: string;
  source_kind?: 'primary' | 'related';
  table_name?: string;
  detail_kind?: 'article' | 'table';
  canonical_source_id?: string;
  document_identity?: string;
  display_label?: string;
}

export type StructuredCellValue = string | number | boolean | null;

export interface StructuredResult {
  id: string;
  lookup_type: string;
  presentation_type?: 'table' | 'contact_card';
  title: string;
  cohort?: string;
  applicability?: string;
  columns: string[];
  rows: Array<Record<string, StructuredCellValue>>;
  provenance: {
    source_type: 'structured_dataset' | 'curated_registry';
    source_label?: string;
    document_id?: string;
    source_pages?: number[];
    source_reference?: Citation | null;
  };
  field_provenance?: Record<string, {
    source_type: 'curated_registry';
    source_label: string;
    registry?: string;
    mapping_methods?: string[];
  }>;
}

export interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
  isStreaming?: boolean;
  isHardcoded?: boolean;
  timestamp: string;
  responseTimeMs?: number;
  ttftMs?: number;
  confidence?: 'high' | 'medium' | 'low';
  citations?: Citation[];
  structuredResults?: StructuredResult[];
  relatedReferences?: RelatedReference[];
  runId?: string;
  usedCache?: boolean;
  suggestions?: string[];
  queuePosition?: number | null;
  userQuery?: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
const API_URL = `${API_BASE_URL}/chat/stream`;

export function useChat(cohort: string = 'K48-K49') {
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = sessionStorage.getItem('chat_messages');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        // Ignore parse error
      }
    }
    return [];
  });
  const [isTyping, setIsTyping] = useState(false);
  const [progressMessage, setProgressMessage] = useState<string>('');
  const [systemStatus, setSystemStatus] = useState<'normal' | 'error'>('normal');

  useEffect(() => {
    if (!isTyping) {
      sessionStorage.setItem('chat_messages', JSON.stringify(messages));
    }
  }, [messages, isTyping]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isTyping) return;

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg: Message = { 
      id: Date.now().toString(), 
      role: 'user', 
      content: text,
      timestamp 
    };
    
    setMessages(prev => [...prev, userMsg]);
    setIsTyping(true);
    setProgressMessage('');

    const botMsgId = (Date.now() + 1).toString();
    const startTime = Date.now();
    let ttftMs: number | null = null;
    let capturedCitations: Citation[] = [];
    let capturedStructuredResults: StructuredResult[] = [];
    let capturedRelatedReferences: RelatedReference[] = [];
    let capturedRunId: string | null = null;
    let capturedUsedCache = false;

    setMessages(prev => [...prev, { 
      id: botMsgId, 
      role: 'bot', 
      content: "", 
      isStreaming: true,
      userQuery: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }]);

    let targetBotContent = "";
    let displayedBotContent = "";
    let streamDone = false;
    let streamError = false;
    let donePayload: {
      responseTimeMs: number;
      confidence: 'high' | 'medium' | 'low';
      citations: Citation[];
      structuredResults: StructuredResult[];
      relatedReferences: RelatedReference[];
      runId?: string;
      usedCache: boolean;
    } | null = null;

    // Bộ đệm làm mịn hiệu ứng gõ chữ (Smooth Typewriter Ticker: 16ms/frame)
    const typingTimer = setInterval(() => {
      if (displayedBotContent.length < targetBotContent.length) {
        const diff = targetBotContent.length - displayedBotContent.length;
        // Tự động điều chỉnh số ký tự mỗi tick để gõ nhịp nhàng:
        const step = diff > 100 ? 8 : diff > 40 ? 4 : diff > 15 ? 2 : 1;
        displayedBotContent = targetBotContent.slice(0, displayedBotContent.length + step);

        setMessages(prev => prev.map(m => 
          m.id === botMsgId ? { ...m, content: displayedBotContent, userQuery: text, queuePosition: null } : m
        ));
      } else if (streamDone || streamError) {
        clearInterval(typingTimer);
        setIsTyping(false);
        setProgressMessage('');

        if (donePayload) {
          setMessages(prev => prev.map(m => 
            m.id === botMsgId ? { 
              ...m, 
              content: targetBotContent,
              userQuery: text,
              isStreaming: false,
              responseTimeMs: donePayload!.responseTimeMs,
              ttftMs: ttftMs || undefined,
              confidence: donePayload!.confidence,
              citations: donePayload!.citations,
              structuredResults: donePayload!.structuredResults,
              relatedReferences: donePayload!.relatedReferences,
              runId: donePayload!.runId,
              usedCache: donePayload!.usedCache
            } : m
          ));
        }
      }
    }, 16);

    try {
      const chatHistory = messages
        .filter(m => !m.isStreaming && !m.isHardcoded)
        .map(m => ({
          role: m.role === 'bot' ? 'assistant' : 'user',
          content: m.content
        }));

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: getApiClientHeaders(),
        body: JSON.stringify({ query: userMsg.content, chat_history: chatHistory, cohort }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        if (response.status === 429) throw new Error("RATE_LIMIT");
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (part.startsWith('event: ')) {
            const lines = part.split('\n');
            const eventType = lines.find(line => line.startsWith('event: '))?.replace('event: ', '') || '';
            const dataStr = lines
              .filter(line => line.startsWith('data: '))
              .map(line => line.replace('data: ', ''))
              .join('\n');
            
            if (!dataStr) continue;
            
            try {
              const data = JSON.parse(dataStr);
              if (eventType === 'metadata') {
                if (data.citations_used) {
                  capturedCitations = data.citations_used;
                }
                if (data.structured_results) {
                  capturedStructuredResults = data.structured_results;
                }
                if (data.related_references) {
                  capturedRelatedReferences = data.related_references;
                }
                if (data.run_id) {
                  capturedRunId = data.run_id;
                }
                if (data.used_cache) {
                  capturedUsedCache = data.used_cache;
                }
              } else if (eventType === 'queued') {
                setMessages(prev => prev.map(m => 
                  m.id === botMsgId ? { ...m, queuePosition: data.position } : m
                ));
              } else if (eventType === 'progress') {
                setProgressMessage(data.message);
                setMessages(prev => prev.map(m => 
                  m.id === botMsgId ? { ...m, queuePosition: null } : m
                ));
              } else if (eventType === 'token') {
                if (ttftMs === null) {
                  ttftMs = Date.now() - startTime;
                }
                targetBotContent += (data.text || "");
              } else if (eventType === 'done' || eventType === 'error') {
                const responseTimeMs = Date.now() - startTime;

                if (eventType === 'done' && Array.isArray(data.citations_used)) {
                  capturedCitations = data.citations_used;
                }
                
                if (eventType === 'error' && data.error_message) {
                  targetBotContent = data.error_message;
                  streamError = true;
                }
                
                let confidence: 'high' | 'medium' | 'low' = 'low';
                if (capturedCitations.length > 0 || capturedStructuredResults.length > 0) confidence = 'high';

                if (targetBotContent.includes("Hiện tại mình chưa gọi được mô hình AI")) {
                  setSystemStatus('error');
                } else {
                  setSystemStatus('normal');
                }

                donePayload = {
                  responseTimeMs,
                  confidence,
                  citations: capturedCitations,
                  structuredResults: capturedStructuredResults,
                  relatedReferences: capturedRelatedReferences,
                  runId: capturedRunId || undefined,
                  usedCache: capturedUsedCache
                };
                streamDone = true;
              }
            } catch (err) {
              console.error("Parse error", err);
            }
          }
        }
      }
    } catch (error) {
      clearInterval(typingTimer);
      console.error("Fetch error:", error);
      setSystemStatus('error');
      const responseTimeMs = Date.now() - startTime;
      const isTimeout = error instanceof Error && error.name === 'AbortError';
      const isRateLimit = error instanceof Error && error.message === 'RATE_LIMIT';
      let errMsg = "Xin lỗi, đã có lỗi kết nối xảy ra.";
      if (isTimeout) errMsg = "Hệ thống AI hiện đang quá tải hoặc phản hồi chậm. Vui lòng thử lại sau nhé!";
      if (isRateLimit) errMsg = "Bạn hỏi hơi nhanh rồi đấy! Vui lòng đợi khoảng 1 phút rồi hỏi tiếp để tránh spam hệ thống nhé 🛑";
      
      setMessages(prev => prev.map(m => 
        m.id === botMsgId ? { 
          ...m, 
          content: errMsg, 
          isStreaming: false,
          responseTimeMs,
          confidence: 'low'
        } : m
      ));
      setIsTyping(false);
    }
  }, [messages, isTyping, cohort]);

  const sendHardcodedMessage = useCallback((userText: string, botResponse: string, suggestions?: string[]) => {
    if (isTyping) return;
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    // User message
    const userMsg: Message = { 
      id: Date.now().toString(), 
      role: 'user', 
      content: userText,
      isHardcoded: true,
      timestamp 
    };
    
    // Bot message
    const botMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'bot',
      content: botResponse,
      isStreaming: false,
      isHardcoded: true,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      confidence: 'high',
      suggestions
    };

    setMessages(prev => [...prev, userMsg, botMsg]);
  }, [isTyping]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setIsTyping(false);
    sessionStorage.removeItem('chat_messages');
  }, []);

  const retryLastMessage = useCallback(async () => {
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUserMsg || isTyping) return;
    setMessages(prev => {
      const newMessages = [...prev];
      const lastBotIdx = newMessages.findLastIndex(m => m.role === 'bot');
      if (lastBotIdx > -1) newMessages.splice(lastBotIdx, 1);
      return newMessages;
    });
    await sendMessage(lastUserMsg.content);
  }, [messages, isTyping, sendMessage]);

  const regenerateLastMessage = useCallback(async () => {
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUserMsg || isTyping) return;
    setMessages(prev => prev.slice(0, -1));
    await sendMessage(lastUserMsg.content);
  }, [messages, isTyping, sendMessage]);

  return {
    messages,
    isTyping,
    progressMessage,
    sendMessage,
    sendHardcodedMessage,
    clearMessages,
    systemStatus,
    retryLastMessage,
    regenerateLastMessage
  };
}
