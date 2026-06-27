import { useState, useCallback, useEffect } from 'react';

export interface Citation {
  chunk_id: string;
  content: string;
  metadata?: Record<string, unknown>;
  score?: number;
  title?: string;
  source_pages?: number[];
  chunk_type?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
  isStreaming?: boolean;
  timestamp: string;
  responseTimeMs?: number;
  confidence?: 'high' | 'medium' | 'low';
  citations?: Citation[];
  runId?: string;
  usedCache?: boolean;
  suggestions?: string[];
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
    let currentBotContent = "";
    let capturedCitations: Citation[] = [];
    let capturedRunId: string | null = null;
    let capturedUsedCache = false;

    setMessages(prev => [...prev, { 
      id: botMsgId, 
      role: 'bot', 
      content: "", 
      isStreaming: true,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }]);

    try {
      const chatHistory = messages
        .filter(m => !m.isStreaming)
        .map(m => ({
          role: m.role === 'bot' ? 'assistant' : 'user',
          content: m.content
        }));

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userMsg.content, chat_history: chatHistory, cohort }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
            // SSE data co the bi tach thanh nhieu dong, nen gom tat ca data: truoc khi JSON.parse.
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
                if (data.run_id) {
                  capturedRunId = data.run_id;
                }
                if (data.used_cache) {
                  capturedUsedCache = data.used_cache;
                }
              } else if (eventType === 'progress') {
                setProgressMessage(data.message);
              } else if (eventType === 'token') {
                currentBotContent += data.text;
                setMessages(prev => prev.map(m => 
                  m.id === botMsgId ? { ...m, content: currentBotContent } : m
                ));
              } else if (eventType === 'done' || eventType === 'error') {
                setIsTyping(false);
                setProgressMessage('');
                const responseTimeMs = Date.now() - startTime;
                
                // Mock confidence based on citations if not provided
                let confidence: 'high' | 'medium' | 'low' = 'low';
                if (capturedCitations.length > 0) confidence = 'high';

                // Check for fallback error string from Gemini
                if (currentBotContent.includes("Hiện tại mình chưa gọi được mô hình AI")) {
                  setSystemStatus('error');
                } else {
                  setSystemStatus('normal');
                }

                setMessages(prev => prev.map(m => 
                  m.id === botMsgId ? { 
                    ...m, 
                    isStreaming: false,
                    responseTimeMs,
                    confidence,
                    citations: capturedCitations,
                    runId: capturedRunId || undefined,
                    usedCache: capturedUsedCache
                  } : m
                ));
              }
            } catch (err) {
              console.error("Parse error", err);
            }
          }
        }
      }
    } catch (error) {
      console.error("Fetch error:", error);
      setSystemStatus('error');
      const responseTimeMs = Date.now() - startTime;
      const isTimeout = error instanceof Error && error.name === 'AbortError';
      const errMsg = isTimeout 
        ? "Hệ thống AI hiện đang quá tải hoặc phản hồi chậm. Vui lòng thử lại sau nhé!"
        : "Xin lỗi, đã có lỗi kết nối xảy ra.";
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
  // BẮT BUỘC phải truyền `messages` và `cohort` vào dependency array.
  }, [messages, isTyping, cohort]);

  const sendHardcodedMessage = useCallback((userText: string, botResponse: string, suggestions?: string[]) => {
    if (isTyping) return;
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    // User message
    const userMsg: Message = { 
      id: Date.now().toString(), 
      role: 'user', 
      content: userText,
      timestamp 
    };
    
    // Bot message
    const botMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'bot',
      content: botResponse,
      isStreaming: false,
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
