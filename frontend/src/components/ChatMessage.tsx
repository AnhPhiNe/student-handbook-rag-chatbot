import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import { Copy, ChevronDown, ChevronRight, Check, ThumbsUp, ThumbsDown, RotateCcw, Share2, FileText, Brain, ExternalLink, X } from 'lucide-react';
import type { Citation, Message, RelatedReference } from '../hooks/useChat';
import { getApiClientHeaders } from '../utils/clientIdentity';
import { useToast } from './Toast';
import { RelatedReferenceLink } from './RelatedReference';
import { useAccessibleDialog } from '../hooks/useAccessibleDialog';
import { StructuredResults } from './StructuredResults';
const userAvatarImg = '/user_avatar.png';
const botAvatarImg = '/bot_avatar.png';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

interface ChatMessageProps {
  message: Message;
  onRegenerate?: () => void;
  onRetry?: () => void;
  query?: string;
  onSuggestionClick?: (text: string) => void;
}


function getRelativeTime(timestamp: string): string {
  // Simple implementation since timestamp is just HH:MM
  return timestamp;
}

function escapeRegex(value: string): string {
  return value.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&');
}

function relatedReferenceHref(referenceId: string): string {
  return `#related-reference-${encodeURIComponent(referenceId)}`;
}

function relatedReferenceIdFromHref(href: string | undefined): string | null {
  const prefix = '#related-reference-';
  if (!href?.startsWith(prefix)) return null;
  return decodeURIComponent(href.slice(prefix.length));
}

function articleLabelFromText(value: string): string | null {
  const match = value.match(/(?:Điều|Dieu)[\s_-]*(\d+[a-z]?)/iu);
  return match ? `Điều ${match[1].toLocaleLowerCase('vi')}` : null;
}

function referenceArticleLabel(reference: RelatedReference): string | null {
  return articleLabelFromText(reference.article_label ?? '')
    ?? articleLabelFromText(reference.title);
}

function buildPrimaryArticleReferences(citations: Citation[]): RelatedReference[] {
  return citations.flatMap((citation, index) => {
    const content = (citation.parent_content || citation.content).trim();
    const article = articleLabelFromText(citation.parent_article ?? '')
      ?? articleLabelFromText(
        `${citation.source_section ?? ''} ${citation.title ?? ''} ${citation.content.slice(0, 600)}`,
      );
    if (!article || !content) return [];
    const parentTitle = citation.parent_title?.trim();
    const titleParts = [citation.source_section, citation.title]
      .filter((value, position, values): value is string => Boolean(value) && values.indexOf(value) === position);
    const baseTitle = titleParts.join(' — ') || citation.chunk_id;
    const title = parentTitle
      ? (parentTitle.includes(article) ? parentTitle : `${article} — ${parentTitle}`)
      : (baseTitle.includes(article) ? baseTitle : `${article} — ${baseTitle}`);

    const previewSource = citation.content.trim() || content;
    const preview = previewSource.slice(0, 480).trim();
    return [{
      id: `P${index + 1}`,
      primary_chunk_id: citation.chunk_id,
      related_chunk_id: citation.chunk_id,
      title,
      source_pages: citation.source_pages,
      source_url: citation.source_url,
      cohort: citation.cohort,
      preview: content.length > preview.length ? `${preview}…` : preview,
      content,
      article_label: article,
      source_kind: 'primary',
      table_name: citation.table_name,
      detail_kind: citation.detail_kind,
    }];
  });
}

function addArticleReferenceLinks(
  content: string,
  references: RelatedReference[],
): string {
  let linkedContent = content;
  const referencesByArticle = new Map<string, { reference: RelatedReference; article: string }>();
  for (const reference of references) {
    const article = referenceArticleLabel(reference);
    if (!article) continue;
    const key = article.toLocaleLowerCase('vi');
    const current = referencesByArticle.get(key);
    if (!current || reference.source_kind === 'primary') {
      referencesByArticle.set(key, { reference, article });
    }
  }
  const sortedReferences = [...referencesByArticle.values()]
    .filter((entry): entry is { reference: RelatedReference; article: string } => Boolean(entry.article))
    .sort((left, right) => right.article.length - left.article.length);

  for (const { reference, article } of sortedReferences) {
    const articlePattern = escapeRegex(article);
    const mentionPattern = new RegExp(
      `(^|[^\\p{L}\\p{N}_])(${articlePattern})(?![\\p{L}\\p{N}_])`,
      'giu',
    );
    linkedContent = linkedContent.replace(
      mentionPattern,
      `$1[$2](${relatedReferenceHref(reference.id)})`,
    );
  }
  return linkedContent;
}

const NORMALIZED_TABLE_MARKER = 'BẢNG/DANH SÁCH CHUẨN HÓA TỪ NGUỒN:';

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function parseMarkdownTableRow(line: string): string[] {
  return line
    .split('|')
    .slice(1, -1)
    .map((cell) => cell.trim());
}

function normalizedTableHeaders(tableBlock: string): string[][] {
  const content = tableBlock.replace(NORMALIZED_TABLE_MARKER, '').trim();
  const starts = [...content.matchAll(/(?:^|\s)(Bảng:\s*)/gu)];

  return starts.flatMap((match, index) => {
    const start = match.index ?? 0;
    const end = starts[index + 1]?.index ?? content.length;
    const block = content.slice(start, end).trim();
    const tableLines = block.slice(block.indexOf('|'))
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('|'));
    if (tableLines.length < 2) return [];

    const headers = parseMarkdownTableRow(tableLines[0]);
    const separator = parseMarkdownTableRow(tableLines[1]);
    return headers.length && separator.length === headers.length
      && separator.every((cell) => /^:?-{3,}:?$/u.test(cell))
      ? [headers]
      : [];
  });
}

function stripFlattenedSourceTables(text: string, normalizedTableBlock: string): string {
  const headers = normalizedTableHeaders(normalizedTableBlock);
  let cleaned = text;

  for (const headerRow of headers) {
    const headerPattern = headerRow
      .map((cell) => escapeRegex(cell).replace(/\s+/gu, '\\s+'))
      .join('\\s*\\n\\s*');
    // Suppress flattened copy from raw PDF text until the next section/marker
    const flattenedTablePattern = new RegExp(
      `(^|\\n)\\s*${headerPattern}(?:\\s*\\n[\\s\\S]*?)(?=\\n\\s*(?:${headerPattern}|[a-zđ]\\)\\d*\\s+|\\d+\\s+[A-ZÀ-Ỹ]|\\d+\\.\\s)|$)`,
      'gimu',
    );
    cleaned = cleaned.replace(flattenedTablePattern, '$1');
  }

  return cleaned.replace(/\n{3,}/gu, '\n\n').trim();
}

function renderNormalizedTables(tableBlock: string): string {
  const content = tableBlock.replace(NORMALIZED_TABLE_MARKER, '').trim();
  const starts = [...content.matchAll(/(?:^|\s)(Bảng:\s*)/gu)];
  if (!starts.length) return '';

  return starts.map((match, index) => {
    const start = match.index ?? 0;
    const end = starts[index + 1]?.index ?? content.length;
    const block = content.slice(start, end).trim();
    const title = block.match(/^Bảng:\s*(.*?)(?=\s+Phạm vi áp dụng:|\s+\||$)/su)?.[1]?.trim();
    const applicability = block.match(/Phạm vi áp dụng:\s*(.*?)(?=\s+\||$)/su)?.[1]?.trim();
    const pipeIndex = block.indexOf('|');
    if (!title || pipeIndex < 0) return '';

    // Markdown table rows must be parsed one line at a time. Splitting the
    // entire block on "|" makes the newline between rows look like an extra
    // cell, which shifts all columns after the separator row.
    const tableLines = block.slice(pipeIndex)
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('|'));
    if (tableLines.length < 3) return '';

    const headers = parseMarkdownTableRow(tableLines[0]);
    const separator = parseMarkdownTableRow(tableLines[1]);
    if (!headers.length || separator.length !== headers.length
      || !separator.every((cell) => /^:?-{3,}:?$/u.test(cell))) return '';

    const rows = tableLines.slice(2)
      .map(parseMarkdownTableRow)
      .filter((row) => row.length === headers.length && row.some(Boolean));

    if (!rows.length) return '';

    return [
      '<section class="citation-normalized-table">',
      '<div class="citation-normalized-table-heading">',
      '<span>Bảng trong tài liệu</span>',
      `<h4>${escapeHtml(title)}</h4>`,
      applicability ? `<p>${escapeHtml(applicability)}</p>` : '',
      '</div>',
      '<div class="citation-normalized-table-scroll">',
      '<table>',
      `<thead><tr>${headers.map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join('')}</tr></thead>`,
      `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`,
      '</table>',
      '</div>',
      '</section>',
    ].join('');
  }).filter(Boolean).join('\n\n');
}

function formatLegalSectionMarkers(text: string): string {
  // Only list markers at a physical line start are structural. Values such as
  // "thang điểm 10." and "nhận điểm 0." occur inside normal sentences.
  return text.replace(/(^|\n)\s*(\d+\.|[a-zđ]\))\s+/gimu, (_match, prefix, marker) => (
    `${prefix}\n\n**${marker}** `
  ));
}

function repairPdfLayoutArtifacts(text: string): string {
  return text
    // Footnote superscripts can be flattened immediately after a legal point,
    // for example "a)4 Hệ thống...". They are not part of the point label.
    .replace(/([a-zđ]\))\d+(?=\s+[A-ZÀ-ỸĐ])/gimu, '$1')
    // A PDF line wrap may split "học tập)" into "học tậ\np)". The trailing
    // p is part of the word, not a new point p).
    .replace(/học\s+tậ\s*\n\s*p\)(?=\s)/giu, 'học tập)');
}

function formatAmendmentFootnotes(text: string): string {
  return text.replace(
    /(^|\n)(\d+)\s+(Điểm này (?:(?:đã\s+)?được sửa đổi|được bổ sung)[\s\S]*?Cụ thể như sau:)/gimu,
    (_match, prefix, footnoteNumber, note) => (
      `${prefix}\n\n**Ghi chú cập nhật ${footnoteNumber}:** ${note}`
    ),
  );
}

function renderAllMarkdownTables(text: string): string {
  if (!text || !text.includes('|')) return text;

  // Split any flattened `||` or `| |` into separate lines safely
  const safeText = text.replace(/\|\s*\|\s*/g, '|\n|');
  const lines = safeText.split('\n');
  const result: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|') && i + 1 < lines.length) {
      const nextLine = lines[i + 1].trim();
      const headers = parseMarkdownTableRow(line);
      const separator = parseMarkdownTableRow(nextLine);

      if (
        headers.length > 0 &&
        separator.length === headers.length &&
        separator.every((cell) => /^:?-{2,}:?$/u.test(cell))
      ) {
        const bodyRows: string[][] = [];
        let j = i + 2;
        while (j < lines.length) {
          const bodyLine = lines[j].trim();
          if (bodyLine.startsWith('|') && bodyLine.endsWith('|')) {
            const row = parseMarkdownTableRow(bodyLine);
            if (row.length === headers.length) {
              bodyRows.push(row);
              j++;
              continue;
            }
          }
          break;
        }

        const thead = `<thead><tr>${headers.map((h) => `<th scope="col">${h}</th>`).join('')}</tr></thead>`;
        const tbody = `<tbody>${bodyRows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody>`;
        result.push(
          `\n\n<section class="citation-normalized-table"><div class="citation-normalized-table-scroll"><table>${thead}${tbody}</table></div></section>\n\n`
        );

        i = j;
        continue;
      }
    }

    result.push(lines[i]);
    i++;
  }

  return result.join('\n');
}

function formatCitationContentForDisplay(text: string): string {
  let cleaned = repairPdfLayoutArtifacts(text);

  if (cleaned.includes('THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:')) {
    cleaned = cleaned.split('THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:')[0].trim();
  }

  if (cleaned.includes('Nội dung:')) {
    cleaned = cleaned.split('Nội dung:').slice(1).join('Nội dung:').trim();
  }

  const tableMarkerIndex = cleaned.indexOf(NORMALIZED_TABLE_MARKER);
  const normalizedTables = tableMarkerIndex >= 0
    ? renderNormalizedTables(cleaned.slice(tableMarkerIndex))
    : '';
  if (tableMarkerIndex >= 0) {
    cleaned = stripFlattenedSourceTables(
      cleaned.slice(0, tableMarkerIndex).trim(),
      cleaned.slice(tableMarkerIndex),
    );
  }

  let formattedText = formatLegalSectionMarkers(formatAmendmentFootnotes(cleaned))
    .replace(/(?:^|\n)(\d+\.)\s/g, '\n\n**$1** ')
    .replace(/(?:^|\n)([a-zđ]\))\s/gi, '\n\n*$1* ')
    .replace(/(?:^|\n)([-•])\s/g, '\n\n$1 ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  formattedText = renderAllMarkdownTables(formattedText);

  return [formattedText, normalizedTables].filter(Boolean).join('\n\n');
}

function getCitationTypeLabel(citation: Citation): string {
  return citation.source_label || citation.table_name || 'Nguồn tham khảo';
}

function getCompactExcerpt(text: string, maxLength = 220): string {
  // Clean markdown tables out of the compact plain-text excerpt safely without nested regex
  const lines = text.split('\n');
  const nonTableLines = lines.filter((line) => {
    const trimmed = line.trim();
    return !(trimmed.startsWith('|') && trimmed.endsWith('|'));
  });

  const withoutTable = nonTableLines.join('\n').trim();

  if (!withoutTable) {
    return 'Bảng quy định và số liệu chi tiết trong Sổ tay sinh viên HCMUE. Nhấn để mở xem toàn bộ bảng.';
  }

  const plain = withoutTable
    .replace(/<[^>]+>/g, ' ')
    .replace(/\*\*/g, '')
    .replace(/\n+/g, ' ')
    .trim();

  if (plain.length <= maxLength) return plain;
  return `${plain.slice(0, maxLength).trim()}...`;
}

function highlightKeywords(text: string, query?: string): string {
  if (!query || !text) return text;
  
  const cleanQuery = query.replace(/[?!.,;:()[\]{}"'`/\\–—]/gu, ' ').trim();
  const words = cleanQuery.split(/\s+/).filter(Boolean);
  if (words.length === 0) return text;

  // Linguistic stopwords (conjunctions, prepositions, question particles)
  const STOPWORDS = new Set([
    'là', 'gì', 'như', 'thế', 'nào', 'ở', 'đâu', 'khi', 'có', 'được', 'không',
    'cho', 'tôi', 'làm', 'sao', 'và', 'hoặc', 'thì', 'của', 'về', 'trong',
    'đến', 'này', 'đó', 'tại', 'với', 'các', 'những', 'một', 'hai', 'ba',
    'bạn', 'em', 'mình', 'hỏi', 'giúp', 'đã', 'sẽ', 'đang', 'bao', 'nhiêu', 'mấy', 'ai',
    'theo', 'quy', 'định', 'việc', 'ra'
  ]);

  const phrases: string[] = [];

  // Extract multi-word n-gram phrases (>= 2 words) directly from user question
  const maxN = Math.min(words.length, 6);
  for (let n = maxN; n >= 2; n--) {
    for (let i = 0; i <= words.length - n; i++) {
      const slice = words.slice(i, i + n);
      // Strip leading and trailing stopwords
      while (slice.length > 1 && STOPWORDS.has(slice[0].toLowerCase())) slice.shift();
      while (slice.length > 1 && STOPWORDS.has(slice[slice.length - 1].toLowerCase())) slice.pop();
      if (slice.length >= 2) {
        phrases.push(slice.join(' '));
      }
    }
  }

  // Standalone alphanumeric codes / technical abbreviations from query (e.g. K51, GPA, 3.6)
  words.forEach(w => {
    const isCodeOrNumber = /^[a-zA-Z0-9+\-_.]+$/u.test(w) && (/\d/.test(w) || (w.length >= 3 && w.toUpperCase() === w));
    if (isCodeOrNumber && !STOPWORDS.has(w.toLowerCase())) {
      phrases.push(w);
    }
  });

  const validPhrases = [...new Set(phrases.map(p => p.trim()).filter(p => p.length >= 3))]
    .sort((a, b) => b.length - a.length);

  if (validPhrases.length === 0) return text;

  const escapeRegex = (s: string) => s.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&');
  const pattern = new RegExp(`(?<![<a-zA-Z0-9À-ỹ])(${validPhrases.map(escapeRegex).join('|')})(?![>a-zA-Z0-9À-ỹ])`, 'giu');
  
  // Exclude tables from highlighting
  const tableSectionRegex = /(<section class="citation-normalized-table">[\s\S]*?<\/section>|<table[\s\S]*?<\/table>)/giu;
  const parts = text.split(tableSectionRegex);

  return parts
    .map((part) => {
      if (part.startsWith('<section class="citation-normalized-table"') || part.startsWith('<table')) {
        return part;
      }
      return part.replace(pattern, '<mark>$1</mark>');
    })
    .join('');
}

export function ChatMessage({ message, onRegenerate, onRetry, query, onSuggestionClick }: ChatMessageProps) {
  const effectiveQuery = message.userQuery || query;
  const defaultShowSources = !!(message.citations && message.citations.length > 0 && message.citations.length <= 2);
  const [showSources, setShowSources] = useState(defaultShowSources);
  const [expandedCitations, setExpandedCitations] = useState<Set<number>>(() => {
    // Auto-expand citation cards that contain structured tables so the table renders immediately
    const initial = new Set<number>();
    if (message.citations) {
      message.citations.forEach((c, idx) => {
        if (c.chunk_type === 'structured_lookup' || c.table_name || (c.content && c.content.includes('| --- |'))) {
          initial.add(idx);
        }
      });
    }
    return initial;
  });
  const [activeRelatedReference, setActiveRelatedReference] = useState<RelatedReference | null>(null);
  const [copied, setCopied] = useState(false);
  const relatedReferenceCloseRef = useRef<HTMLButtonElement>(null);
  const relatedReferenceDialogRef = useAccessibleDialog<HTMLDivElement>({
    isOpen: activeRelatedReference !== null,
    onClose: () => setActiveRelatedReference(null),
    initialFocusRef: relatedReferenceCloseRef,
  });

  const toggleCitation = (idx: number) => {
    setExpandedCitations(prev => {
      const newSet = new Set(prev);
      if (newSet.has(idx)) {
        newSet.delete(idx);
      } else {
        newSet.add(idx);
      }
      return newSet;
    });
  };
  const [feedback, setFeedback] = useState<'like'|'dislike'|null>(null);
  const toast = useToast();

  const [showInlineFeedback, setShowInlineFeedback] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [justFinished, setJustFinished] = useState(false);
  const feedbackInputRef = useRef<HTMLTextAreaElement>(null);
  const prevStreamingRef = useRef(message.isStreaming);
  
  // Sàn hiển thị tối thiểu 500ms (Min Display Threshold)
  const [isMinDelayPassed, setIsMinDelayPassed] = useState(!message.isStreaming);

  useEffect(() => {
    if (message.isStreaming && !isMinDelayPassed) {
      const timer = setTimeout(() => {
        setIsMinDelayPassed(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [message.isStreaming, isMinDelayPassed]);

  useEffect(() => {
    if (showInlineFeedback && feedbackInputRef.current) {
        feedbackInputRef.current.focus();
        feedbackInputRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [showInlineFeedback]);

  useEffect(() => {
    if (prevStreamingRef.current === true && message.isStreaming === false) {
       setJustFinished(true);
       setTimeout(() => setJustFinished(false), 2000);
    }
    prevStreamingRef.current = message.isStreaming;
  }, [message.isStreaming]);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.show("Đã sao chép nội dung!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = () => {
    const text = `📚 HCMUE AI Assistant\n\n💬 ${message.content}\n\n🔗 https://hcmuebot.id.vn`;
    navigator.clipboard.writeText(text);
    toast.show("Đã sao chép nội dung để chia sẻ!", "success");
  };

  const submitFeedbackToApi = async (type: 'like' | 'dislike', text: string = "") => {
    if (!message.runId) return;
    setIsSubmitting(true);
    try {
      await fetch(`${API_BASE_URL}/chat/feedback`, {
        method: 'POST',
        headers: getApiClientHeaders(),
        body: JSON.stringify({
          run_id: message.runId,
          score: type === 'like' ? 1.0 : 0.0,
          comment: text || undefined
        })
      });
      toast.show("Cảm ơn bạn đã đánh giá!", "success");
    } catch {
      toast.show("Có lỗi xảy ra khi gửi đánh giá.", "error");
    } finally {
      setIsSubmitting(false);
      setShowInlineFeedback(false);
    }
  };

  const handleFeedbackClick = (type: 'like' | 'dislike') => {
    if (feedback !== null) return;
    setFeedback(type);
    if (type === 'dislike' && message.runId) {
      setShowInlineFeedback(true);
      setFeedbackText("");
    } else if (type === 'like' && message.runId) {
      submitFeedbackToApi('like');
    } else {
      toast.show("Cảm ơn bạn đã đánh giá!", "success");
    }
  };

  if (message.role === 'user') {
    return (
      <div className="message-wrapper user">
        <img src={userAvatarImg} alt="User" className="avatar user" style={{ backgroundColor: 'transparent' }} />
        <div className="message-content">
          <div className="message-header">
            <span className="message-time">{getRelativeTime(message.timestamp)}</span>
          </div>
          <div className="message-bubble">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  const isErrorMsg = !message.isStreaming && message.content.includes("Xin lỗi, đã có lỗi");

  let displayContent = message.content;
  let thinkContent = "";
  
  const thinkMatch = displayContent.match(/<think>([\s\S]*?)<\/think>/);
  if (thinkMatch) {
    thinkContent = thinkMatch[1].trim();
    displayContent = displayContent.replace(/<think>[\s\S]*?<\/think>/, '').trim();
  } else if (displayContent.includes('<think>')) {
    const parts = displayContent.split('<think>');
    displayContent = parts[0].trim();
    thinkContent = parts[1].trim();
  }
  const relatedReferences = message.relatedReferences ?? [];
  const primaryReferences = buildPrimaryArticleReferences(message.citations ?? []);
  const articleReferences = [...primaryReferences, ...relatedReferences];
  const renderedContent = addArticleReferenceLinks(displayContent, articleReferences);

  return (
    <div className="message-wrapper bot" aria-live="polite">
      <div className={`avatar-container ${message.isStreaming && (!displayContent || !isMinDelayPassed) ? 'halo-breathing' : ''}`}>
        <img src={botAvatarImg} alt="HCMUE AI" className="avatar bot" />
      </div>
      <div className="message-content">
        <div className={`message-bubble ${message.isStreaming && (!displayContent || !isMinDelayPassed) && !thinkContent ? 'typing-indicator' : ''}`}>
          {message.isStreaming && (!displayContent || !isMinDelayPassed) && !thinkContent ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div className="typing-dots-wrapper" aria-busy="true">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
              {message.queuePosition != null && (
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontStyle: 'italic', whiteSpace: 'nowrap' }}>
                  (Úi đông quá! Còn {message.queuePosition} lượt chờ nữa là tới bạn, nhâm nhi ngụm nước đợi AI xíu nha ☕)
                </span>
              )}
            </div>
          ) : (
            <>
              {thinkContent && (
                <div className="thinking-block" style={{ marginBottom: '1rem', borderLeft: '3px solid var(--border-color)', paddingLeft: '0.75rem' }}>
                  <div 
                    className="thinking-header" 
                    onClick={() => setShowThinking(!showThinking)}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: showThinking ? '0.5rem' : '0' }}
                  >
                    <Brain size={16} />
                    <span>Quá trình suy luận</span>
                    {showThinking ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </div>
                  {showThinking && (
                    <div className="thinking-content" style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', fontStyle: 'italic', whiteSpace: 'pre-wrap' }}>
                      {thinkContent}
                    </div>
                  )}
                </div>
              )}
              {displayContent && (
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => {
                      const referenceId = relatedReferenceIdFromHref(href);
                      const reference = referenceId
                        ? articleReferences.find((item) => item.id === referenceId)
                        : undefined;
                      if (reference) {
                        return (
                          <RelatedReferenceLink
                            reference={reference}
                            onOpenDetail={setActiveRelatedReference}
                          >
                            {children}
                          </RelatedReferenceLink>
                        );
                      }
                      return <a href={href}>{children}</a>;
                    },
                  }}
                >
                  {renderedContent}
                </ReactMarkdown>
              )}
            </>
          )}

          {message.isStreaming && displayContent && (
            <span style={{ display: 'inline-block', width: '8px', height: '16px', background: 'var(--accent-color)', animation: 'blink 1s step-end infinite', marginLeft: '4px', verticalAlign: 'middle' }}></span>
          )}

          {!message.isStreaming && message.structuredResults && message.structuredResults.length > 0 && (
            <StructuredResults results={message.structuredResults} />
          )}

          {!message.isStreaming && message.citations && message.citations.length > 0 && (
            <div className="citation-container">
              <div 
                className="citation-header" 
                onClick={() => setShowSources(!showSources)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}
              >
                <span>Nguồn tham khảo ({message.citations.length})</span>
                {showSources ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </div>
              
              {showSources && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                  {message.citations.map((cit, idx) => {
                    const isExpanded = expandedCitations.has(idx);
                    const pagesLabel = cit.source_pages?.length ? `Trang ${cit.source_pages.join(', ')}` : '';
                    const excerpt = cit.content ? getCompactExcerpt(cit.content) : '';
                    const citationTitle = cit.title || cit.chunk_id;
                    const applicability = cit.applicability;
                    return (
                      <div key={idx} className="citation-card">
                        <div className="citation-card-header" onClick={() => toggleCitation(idx)}>
                          <div className="citation-card-icon"><FileText size={16} /></div>
                          <div className="citation-card-body">
                            <span className="citation-title">{citationTitle}</span>
                            <div className="citation-meta-row">
                              <span className="citation-badge">{getCitationTypeLabel(cit)}</span>
                              {cit.cohort && <span className="citation-badge">{cit.cohort}</span>}
                              {pagesLabel && <span className="citation-pages">{pagesLabel}</span>}
                            </div>
                            {applicability && <span className="citation-applicability">{applicability}</span>}
                            {!isExpanded && excerpt && (
                              <div className="citation-excerpt-wrap">
                                <span className="citation-excerpt-label">Trích đoạn liên quan</span>
                                <p 
                                  className="citation-excerpt"
                                  dangerouslySetInnerHTML={{
                                    __html: highlightKeywords(excerpt, effectiveQuery)
                                  }}
                                />
                              </div>
                            )}
                          </div>
                          {cit.source_url && (
                            <a
                              className="citation-source-link"
                              href={cit.source_url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <ExternalLink size={14} />
                              <span>Mở nguồn</span>
                            </a>
                          )}
                          <div className="citation-card-toggle">
                            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          </div>
                        </div>
                        {isExpanded && cit.content && (
                          <div className="citation-card-content citation-markdown">
                            <ReactMarkdown rehypePlugins={[rehypeRaw]}>
                              {highlightKeywords(formatCitationContentForDisplay(cit.content), effectiveQuery)}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {isErrorMsg && (
          <button className="retry-btn" onClick={() => onRetry?.()}>
            <RotateCcw size={14} /> Thử lại
          </button>
        )}

        {!message.isStreaming && !isErrorMsg && (
          <div className="message-metadata" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div style={{ display: 'flex', width: '100%', alignItems: 'center' }}>
              <div className="meta-actions">
                <button className="action-btn" title="Chia sẻ" onClick={handleShare}>
                  <Share2 size={16} />
                  <span className="action-btn-label">Chia sẻ</span>
                </button>
                <button 
                  className={`action-btn ${feedback === 'like' ? 'active' : ''} ${justFinished ? 'pulse-glow' : ''}`} 
                  title="Hữu ích" 
                  onClick={() => handleFeedbackClick('like')}
                  disabled={feedback !== null}
                >
                  <ThumbsUp size={16} />
                </button>
                <button 
                  className={`action-btn ${feedback === 'dislike' ? 'active' : ''} ${justFinished ? 'pulse-glow' : ''}`} 
                  title="Chưa chính xác" 
                  onClick={() => handleFeedbackClick('dislike')}
                  disabled={feedback !== null}
                >
                  <ThumbsDown size={16} />
                </button>
                <button className="action-btn" title="Copy" onClick={handleCopy}>
                  {copied ? <Check size={16} style={{color: 'var(--success)'}}/> : <Copy size={16} />}
                  <span className="action-btn-label">{copied ? 'Đã copy' : 'Copy'}</span>
                </button>
                <button className="action-btn" title="Tạo lại" onClick={() => onRegenerate?.()}>
                  <RotateCcw size={16} />
                  <span className="action-btn-label">Tạo lại</span>
                </button>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: 'auto' }}>
                {message.usedCache ? (
                  <span className="metadata-badge cache" title="Câu trả lời được lấy từ bộ nhớ đệm giúp tốc độ phản hồi tức thì">
                    ⚡ Từ bộ nhớ đệm
                  </span>
                ) : message.responseTimeMs ? (
                  <span 
                    className="metadata-badge latency" 
                    title={`Tổng thời gian phản hồi: ${(message.responseTimeMs / 1000).toFixed(2)}s${message.ttftMs ? ` (Từ đầu tiên: ${(message.ttftMs / 1000).toFixed(2)}s)` : ''}`}
                  >
                    ⏱️ {(message.responseTimeMs / 1000).toFixed(1)}s
                  </span>
                ) : null}
              </div>
            </div>

            {showInlineFeedback && (
              <div className="inline-feedback-container">
                <div className="inline-feedback-header">
                  Câu trả lời sai hoặc thiếu thông tin gì? (Không bắt buộc)
                </div>
                <textarea 
                  ref={feedbackInputRef}
                  className="inline-feedback-input"
                  value={feedbackText} 
                  onChange={e => setFeedbackText(e.target.value)} 
                  placeholder="VD: Trả lời sai điều kiện học bổng K51."
                  rows={2}
                  disabled={isSubmitting}
                />
                <div className="inline-feedback-actions">
                  <button className="btn-secondary" onClick={() => setShowInlineFeedback(false)} disabled={isSubmitting}>Bỏ qua</button>
                  <button className="btn-primary" onClick={() => submitFeedbackToApi('dislike', feedbackText)} disabled={isSubmitting}>
                    {isSubmitting ? "Đang gửi..." : "Gửi góp ý"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {!message.isStreaming && !isErrorMsg && message.role === 'bot' && message.suggestions && message.suggestions.length > 0 && (
          <div className="suggestion-pills-container">
            <span className="suggestion-pills-label">Hỏi nhanh:</span>
            {message.suggestions.slice(0, 6).map((sugg, idx) => (
              <button key={idx} className="suggestion-pill" onClick={() => {
                if (onSuggestionClick) onSuggestionClick(sugg);
              }}>
                {sugg}
              </button>
            ))}
          </div>
        )}

        {activeRelatedReference && createPortal(
          <div
            className="related-reference-dialog-overlay"
            onClick={() => setActiveRelatedReference(null)}
          >
            <div
              ref={relatedReferenceDialogRef}
              className="related-reference-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="related-reference-dialog-title"
              tabIndex={-1}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="related-reference-dialog-header">
                <div>
                  <span className="related-reference-dialog-eyebrow">
                    {activeRelatedReference.source_kind === 'primary'
                      ? 'Căn cứ từ nguồn chính'
                      : 'Điều khoản được nguồn chính dẫn chiếu'}
                  </span>
                  <h3 id="related-reference-dialog-title">{activeRelatedReference.title}</h3>
                  <div className="related-reference-dialog-meta">
                    {activeRelatedReference.cohort && <span>{activeRelatedReference.cohort}</span>}
                    {activeRelatedReference.source_pages?.length ? <span>Trang {activeRelatedReference.source_pages.join(', ')}</span> : null}
                  </div>
                </div>
                <button
                  ref={relatedReferenceCloseRef}
                  type="button"
                  className="related-reference-dialog-close"
                  onClick={() => setActiveRelatedReference(null)}
                  aria-label="Đóng nội dung điều khoản liên quan"
                >
                  <X size={20} />
                </button>
              </div>
              {activeRelatedReference.detail_kind === 'table' && activeRelatedReference.table_name && (
                <div className="related-reference-dialog-table-context">
                  <span>Bảng liên quan trong Điều này</span>
                  <strong>{activeRelatedReference.table_name}</strong>
                </div>
              )}
              <div className="related-reference-dialog-content citation-markdown">
                <ReactMarkdown rehypePlugins={[rehypeRaw]}>
                  {highlightKeywords(
                    formatCitationContentForDisplay(activeRelatedReference.content || activeRelatedReference.preview || ''),
                    effectiveQuery || activeRelatedReference.title
                  )}
                </ReactMarkdown>
              </div>
              {activeRelatedReference.source_url && (
                <div className="related-reference-dialog-actions">
                  <a
                    className="citation-source-link"
                    href={activeRelatedReference.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={14} /> Mở tài liệu gốc
                  </a>
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}


      </div>
    </div>
  );
}
