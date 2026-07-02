import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronsLeftRight, CircleHelp, ExternalLink, GraduationCap, LineChart, Search, ShieldCheck, Sparkles } from 'lucide-react';
import {
  ADMISSION_DATA_NOTE,
  ADMISSION_METHOD_LABELS,
  ADMISSION_RAW_SCORE_SCALE,
  ADMISSION_SCORE_INPUT_MAX,
  type AdmissionMethod,
} from '../../data/admissions';
import {
  calculateAdmissionTotal,
  getSubjectGroupDefinition,
} from '../../data/admissionSubjectGroups';
import {
  estimateAdmissionChance,
  getAdmissionPlanForProgram,
  getAdmissionPrograms,
  getCutoffsForProgram,
  getMethodsForProgram,
  getNearScorePrograms,
  getSubjectGroupsForProgram,
  searchAdmissionPrograms,
  type AdmissionChanceLevel,
} from '../../utils/admissionEstimator';
import { Tooltip } from '../Tooltip';

const ADMISSION_GUIDE_ACK_KEY = 'hcmue-admission-guide-ack-v1';

function formatScore(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return '--';
  const formatted = value.toFixed(2);
  if (formatted.endsWith('.00')) return formatted.slice(0, -3);
  return formatted.replace(/(\.\d)0$/, '$1');
}

function formatDelta(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return '--';
  return `${value >= 0 ? '+' : ''}${formatScore(value)}`;
}

function scoreNeedsReview(value: number | undefined): boolean {
  return value !== undefined && Number.isFinite(value) && value > ADMISSION_RAW_SCORE_SCALE;
}

function splitAdmissionGroupCodes(value: string): string[] {
  return value
    .split(';')
    .map((item) => item.trim())
    .filter(Boolean);
}

function ScoreReviewBadge() {
  return (
    <Tooltip
      className="admission-score-tooltip"
      content="Điểm này lớn hơn 30 vì nguồn có thể đã gồm điểm ưu tiên hoặc quy đổi. Hãy mở nguồn để kiểm tra cách tính trước khi dùng để đặt nguyện vọng."
    >
      <span className="admission-score-review-badge" aria-label="Điểm cần kiểm tra cách tính" tabIndex={0}>
        <CircleHelp size={13} strokeWidth={2.6} />
      </span>
    </Tooltip>
  );
}

function getRiskNote(level: AdmissionChanceLevel): { title: string; text: string } | null {
  switch (level) {
    case 'risky':
      return {
        title: 'Rủi ro nhẹ hơn',
        text: 'Điểm đang thấp hơn điểm chuẩn gần nhất. Bạn vẫn có thể cân nhắc nếu rất thích ngành này, nhưng nên thêm nguyện vọng dự phòng an toàn hơn.',
      };
    case 'very_risky':
      return {
        title: 'Rất rủi ro',
        text: 'Điểm thấp hơn điểm chuẩn gần nhất khá nhiều. Không nên chỉ phụ thuộc vào nguyện vọng này; hãy ưu tiên thêm ngành, tổ hợp hoặc phương thức xét tuyển khác.',
      };
    case 'consider':
      return {
        title: 'Sát ngưỡng',
        text: 'Điểm đang nằm gần vùng điểm chuẩn gần nhất. Hãy xem thêm biến động các năm và chuẩn bị phương án dự phòng.',
      };
    default:
      return null;
  }
}

function getRegimeLabel(regime: 'pre_2025' | 'post_2025'): string {
  return regime === 'post_2025' ? 'Sau mốc 2025' : 'Trước mốc 2025';
}

function getSourceLinkLabel(year: number, sourceKind: 'html' | 'api'): string {
  return sourceKind === 'html' ? `${year}` : `Dữ liệu ${year}`;
}

export function AdmissionPage() {
  const [showGuide, setShowGuide] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(ADMISSION_GUIDE_ACK_KEY) !== 'true';
  });
  const programs = useMemo(() => getAdmissionPrograms(), []);
  const [programName, setProgramName] = useState('');
  const [programQuery, setProgramQuery] = useState('');
  const [admissionMethod, setAdmissionMethod] = useState<AdmissionMethod>('THPT');
  const [subjectGroup, setSubjectGroup] = useState('');
  const [score, setScore] = useState('');
  const [scoreInputMode, setScoreInputMode] = useState<'total' | 'subjects'>('total');
  const [subjectScores, setSubjectScores] = useState<Record<string, string>>({});
  const [priorityScore, setPriorityScore] = useState('');

  const hasSelectedProgram = programName.trim().length > 0;
  const hasSelectedSubjectGroup = subjectGroup.trim().length > 0;

  const suggestions = useMemo(
    () => (programQuery.trim() ? searchAdmissionPrograms(programQuery, 10) : []),
    [programQuery],
  );

  const programRecords = useMemo(
    () => (hasSelectedProgram ? getCutoffsForProgram(programName) : []),
    [hasSelectedProgram, programName],
  );
  const historyScoreScale = useMemo(
    () =>
      Math.max(
        ADMISSION_RAW_SCORE_SCALE,
        Math.ceil(Math.max(0, ...programRecords.map((item) => item.cutoffScore))),
      ),
    [programRecords],
  );

  const selectedPlan = useMemo(
    () => (hasSelectedProgram ? getAdmissionPlanForProgram(programName) : undefined),
    [hasSelectedProgram, programName],
  );

  const methods = useMemo(
    () => (hasSelectedProgram ? getMethodsForProgram(programName) : []),
    [hasSelectedProgram, programName],
  );

  const subjectGroups = useMemo(
    () => (hasSelectedProgram ? getSubjectGroupsForProgram(programName, admissionMethod) : []),
    [hasSelectedProgram, programName, admissionMethod],
  );
  const planSubjectGroupSet = useMemo(() => {
    const codes = selectedPlan?.examSubjectGroups.flatMap((group) => splitAdmissionGroupCodes(group.code)) ?? [];
    return new Set(codes);
  }, [selectedPlan]);
  const subjectGroupOptions = useMemo(() => {
    const planGroups = subjectGroups.filter((group) => planSubjectGroupSet.has(group));
    const historicalGroups = subjectGroups.filter((group) => !planSubjectGroupSet.has(group));
    return { planGroups, historicalGroups };
  }, [planSubjectGroupSet, subjectGroups]);
  const selectedSubjectGroupInPlan = hasSelectedSubjectGroup && planSubjectGroupSet.has(subjectGroup);
  const subjectGroupDefinition = useMemo(() => getSubjectGroupDefinition(subjectGroup), [subjectGroup]);
  const calculatedScore = useMemo(
    () => calculateAdmissionTotal(subjectGroup, subjectScores, priorityScore),
    [subjectGroup, subjectScores, priorityScore],
  );
  const manualScoreNumber = Number(score);
  const effectiveScore = scoreInputMode === 'subjects' && calculatedScore !== null ? calculatedScore : manualScoreNumber;
  const hasScore = Number.isFinite(effectiveScore) && effectiveScore > 0;

  useEffect(() => {
    if (methods.length > 0 && !methods.includes(admissionMethod)) {
      setAdmissionMethod(methods[0]);
    }
  }, [methods, admissionMethod]);

  useEffect(() => {
    if (subjectGroup && !subjectGroups.includes(subjectGroup)) {
      setSubjectGroup('');
    }
  }, [subjectGroups, subjectGroup]);

  const estimate = useMemo(
    () =>
      hasSelectedProgram && hasSelectedSubjectGroup
        ? estimateAdmissionChance({
            programName,
            admissionMethod,
            subjectGroup,
            score: effectiveScore,
          })
        : estimateAdmissionChance({
            programName: '',
            admissionMethod,
            subjectGroup,
            score: 0,
          }),
    [hasSelectedProgram, hasSelectedSubjectGroup, programName, admissionMethod, subjectGroup, effectiveScore],
  );

  const nearPrograms = useMemo(() => getNearScorePrograms(effectiveScore, 6), [effectiveScore]);
  const selectedFaculty = programRecords[0]?.faculty ?? 'Chưa có dữ liệu';
  const latestYear = programRecords.length > 0 ? Math.max(...programRecords.map((item) => item.year)) : undefined;
  const riskNote = getRiskNote(estimate.level);
  const latestCutoffIs2025 = estimate.latestCutoff?.year === 2025;
  const latestCutoffIsPost2025 = estimate.latestCutoff?.admissionRegime === 'post_2025';
  const latestCutoffNeedsReview = scoreNeedsReview(estimate.latestCutoff?.cutoffScore);
  const sourceLinksByYear = useMemo(
    () => {
      const sources = programRecords.reduce((current, item) => {
          if (!current.has(item.year)) {
            current.set(item.year, { sourceUrl: item.sourceUrl, sourceKind: item.sourceKind });
          }
          return current;
        }, new Map<number, { sourceUrl: string; sourceKind: 'html' | 'api' }>());
      if (selectedPlan && !sources.has(selectedPlan.year)) {
        sources.set(selectedPlan.year, { sourceUrl: selectedPlan.sourceUrl, sourceKind: 'html' });
      }
      return Array.from(sources).sort(([yearA], [yearB]) => yearB - yearA);
    },
    [programRecords, selectedPlan],
  );

  const selectProgram = (name: string) => {
    setProgramName(name);
    setProgramQuery(name);
  };

  const confirmGuide = () => {
    window.localStorage.setItem(ADMISSION_GUIDE_ACK_KEY, 'true');
    setShowGuide(false);
  };

  return (
    <div className="page-container tool-page admission-page">
      {showGuide && (
        <div className="admission-guide-overlay" role="dialog" aria-modal="true" aria-labelledby="admission-guide-title">
          <div className="admission-guide-modal">
            <div className="admission-guide-icon">
              <Sparkles size={24} />
            </div>
            <p className="admission-guide-eyebrow">Công cụ tham khảo nguyện vọng</p>
            <h2 id="admission-guide-title">Tuyển sinh dùng để làm gì?</h2>
            <p className="admission-guide-lead">
              Công cụ này giúp bạn tra nhanh điểm chuẩn HCMUE, xem tổ hợp xét tuyển và ước lượng mức độ an toàn
              khi đặt nguyện vọng theo điểm thi THPT.
            </p>

            <div className="admission-guide-grid">
              <div>
                <CheckCircle2 size={18} />
                <span>Chọn ngành, phương thức và tổ hợp môn.</span>
              </div>
              <div>
                <CheckCircle2 size={18} />
                <span>Nhập tổng điểm hoặc điểm từng môn để hệ thống tự tính.</span>
              </div>
              <div>
                <CheckCircle2 size={18} />
                <span>So với điểm chuẩn 2021-2025, trong đó mốc 2025 được ưu tiên hơn.</span>
              </div>
              <div>
                <CheckCircle2 size={18} />
                <span>Xem kế hoạch tuyển sinh 2026: chỉ tiêu, tổ hợp và nguồn kiểm chứng.</span>
              </div>
            </div>

            <div className="admission-guide-note">
              <AlertTriangle size={18} />
              <p>
                Kết quả chỉ để tham khảo, không phải cam kết trúng tuyển. Dữ liệu ưu tiên cơ sở chính TP.HCM; hãy mở
                nguồn trước khi chốt nguyện vọng.
              </p>
            </div>

            <button type="button" className="tool-btn primary admission-guide-action" onClick={confirmGuide}>
              Đã hiểu, bắt đầu tra cứu
            </button>
          </div>
        </div>
      )}

      <div className="page-header">
        <h1>Tuyển sinh</h1>
        <p>
          Tra cứu điểm chuẩn HCMUE và ước lượng mức độ an toàn tham khảo theo ngành,
          phương thức xét tuyển và tổ hợp môn.
        </p>
      </div>

      <section className="tool-callout warning admission-warning">
        <AlertTriangle size={20} />
        <div>
          <h2>Lưu ý trước khi dùng</h2>
          <p>
            Kết quả chỉ là công cụ tham khảo để đặt nguyện vọng, không phải dự đoán chắc chắn.
            Từ năm 2025, chương trình GDPT 2018 làm thay đổi cấu trúc thi và tổ hợp xét tuyển,
            nên dữ liệu 2025 trở đi được ưu tiên hơn dữ liệu xu hướng trước đó.
          </p>
        </div>
      </section>

      <div className="tool-layout split admission-layout">
        <section className="tool-panel">
          <div className="tool-panel-header">
            <div>
              <h2>Nhập thông tin xét tuyển</h2>
              <p>Chọn đúng ngành, phương thức và tổ hợp để kết quả có ý nghĩa hơn.</p>
            </div>
            <GraduationCap size={24} className="text-accent" />
          </div>

          <label className="tool-field">
            <span>Tìm ngành</span>
            <div className="autocomplete-box">
              <Search size={18} className="search-icon" />
              <input
                className="tool-input"
                value={programQuery}
                onChange={(event) => setProgramQuery(event.target.value)}
                placeholder="Nhập tên ngành, ví dụ: Công nghệ thông tin"
              />
            </div>
          </label>

          {programQuery && programQuery !== programName && (
            <div className="autocomplete-list">
              {suggestions.length > 0 ? (
                suggestions.map((name) => (
                  <button key={name} type="button" onClick={() => selectProgram(name)}>
                    <strong>{name}</strong>
                    <span>{getCutoffsForProgram(name)[0]?.faculty ?? 'HCMUE'}</span>
                  </button>
                ))
              ) : (
                <p>Chưa tìm thấy ngành trong bộ dữ liệu tuyển sinh hiện tại.</p>
              )}
            </div>
          )}

          <div className="tool-form-grid admission-form-grid">
            <label className="tool-field">
              <span>Ngành đang chọn</span>
              <select
                className="tool-select"
                value={programName}
                onChange={(event) => selectProgram(event.target.value)}
              >
                <option value="" disabled>
                  Chưa chọn ngành
                </option>

                {programs.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label className="tool-field">
              <span>Phương thức</span>
              <select
                className="tool-select"
                value={hasSelectedProgram ? admissionMethod : ''}
                onChange={(event) => setAdmissionMethod(event.target.value as AdmissionMethod)}
                disabled={!hasSelectedProgram || methods.length <= 1}
              >
                {!hasSelectedProgram && (
                  <option value="">Chọn ngành trước</option>
                )}

                {methods.map((method) => (
                  <option key={method} value={method}>
                    {ADMISSION_METHOD_LABELS[method]}
                  </option>
                ))}
              </select>
            </label>

            <label className="tool-field">
              <span>Tổ hợp môn</span>
              <select
                className="tool-select"
                value={hasSelectedProgram ? subjectGroup : ''}
                onChange={(event) => setSubjectGroup(event.target.value)}
                disabled={!hasSelectedProgram}
              >
                <option value="" disabled>
                  {hasSelectedProgram ? 'Chọn tổ hợp môn' : 'Chọn ngành trước'}
                </option>

                {subjectGroupOptions.planGroups.length > 0 && (
                  <optgroup label="Theo đề án tuyển sinh 2026">
                    {subjectGroupOptions.planGroups.map((group) => (
                      <option key={group} value={group}>
                        {group}
                      </option>
                    ))}
                  </optgroup>
                )}

                {subjectGroupOptions.historicalGroups.length > 0 && (
                  <optgroup label="Tổ hợp từng dùng các năm trước">
                    {subjectGroupOptions.historicalGroups.map((group) => (
                      <option key={group} value={group}>
                        {group}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>
          </div>

          {hasSelectedProgram && (
            <div className="admission-subject-box">
              <div>
                <span>{hasSelectedSubjectGroup ? `Tổ hợp ${subjectGroup}` : 'Chưa chọn tổ hợp môn'}</span>
                {!hasSelectedSubjectGroup ? (
                  <strong>Chọn một tổ hợp trong đề án 2026 hoặc lịch sử điểm chuẩn để hệ thống so sánh chính xác.</strong>
                ) : subjectGroupDefinition.subjects.length > 0 ? (
                  <strong>{subjectGroupDefinition.subjects.map((subject) => subject.label).join(' + ')}</strong>
                ) : (
                  <strong>Chưa có mô tả môn trong dữ liệu hiện tại</strong>
                )}
              </div>
              {selectedPlan && hasSelectedSubjectGroup && (
                <span className={`admission-subject-status ${selectedSubjectGroupInPlan ? 'in-plan' : 'historical-only'}`}>
                  {selectedSubjectGroupInPlan ? 'Có trong đề án 2026' : 'Từng dùng các năm trước'}
                </span>
              )}
              {hasSelectedSubjectGroup && subjectGroupDefinition.note && <p>{subjectGroupDefinition.note}</p>}
              {selectedPlan && hasSelectedSubjectGroup && !selectedSubjectGroupInPlan && (
                <p className="admission-subject-plan-note">
                  Tổ hợp này từng có dữ liệu điểm chuẩn ở các năm trước, nhưng chưa thấy trong kế hoạch tuyển sinh 2026 của ngành đang chọn.
                  Hãy ưu tiên các tổ hợp thuộc đề án 2026 khi đặt nguyện vọng năm nay.
                </p>
              )}
            </div>
          )}

          {selectedPlan && (
            <div className="admission-plan-card">
              <div>
                <span>Kế hoạch tuyển sinh 2026</span>
                <strong>{selectedPlan.programLabel}</strong>
              </div>
              <div className="admission-plan-grid">
                <div>
                  <span>Mã xét tuyển</span>
                  <strong>{selectedPlan.admissionCode}</strong>
                </div>
                <div>
                  <span>Mã ngành</span>
                  <strong>{selectedPlan.majorCode}</strong>
                </div>
                <div>
                  <span>Chỉ tiêu</span>
                  <strong>{selectedPlan.quota}</strong>
                </div>
                <div>
                  <span>Cơ sở</span>
                  <strong>{selectedPlan.campus}</strong>
                </div>
              </div>
              <div className="admission-plan-subjects">
                <div>
                  <span>Tổ hợp xét tuyển 2026</span>
                  <strong>{selectedPlan.examMethodLabel}</strong>
                </div>
                {selectedPlan.examSubjectGroups.length > 0 ? (
                  <div className="admission-plan-subject-list">
                    {selectedPlan.examSubjectGroups.map((group) => (
                      <span className="admission-plan-subject-chip" key={group.code}>
                        <b>{group.code}</b>
                        {group.subjects}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p>Đề án nguồn không liệt kê tổ hợp THPT cho ngành này.</p>
                )}
              </div>
              <a className="admission-inline-source compact" href={selectedPlan.sourceUrl} target="_blank" rel="noreferrer">
                Mở kế hoạch tuyển sinh 2026, trang {selectedPlan.sourcePage} <ExternalLink size={14} />
              </a>
            </div>
          )}

          <div className="admission-score-mode" role="tablist" aria-label="Cách nhập điểm xét tuyển">
            <button
              type="button"
              className={scoreInputMode === 'total' ? 'active' : ''}
              onClick={() => setScoreInputMode('total')}
            >
              Nhập tổng điểm
            </button>
            <button
              type="button"
              className={scoreInputMode === 'subjects' ? 'active' : ''}
              onClick={() => setScoreInputMode('subjects')}
              disabled={!hasSelectedProgram || !subjectGroupDefinition.calculable}
            >
              Tính từ điểm môn
            </button>
          </div>

          {scoreInputMode === 'total' || !subjectGroupDefinition.calculable ? (
            <label className="tool-field">
              <span>Tổng điểm xét tuyển của bạn</span>
              <input
                className="tool-input"
                type="number"
                min="0"
                max={ADMISSION_SCORE_INPUT_MAX}
                step="0.01"
                value={score}
                onChange={(event) => setScore(event.target.value)}
                placeholder="Ví dụ: 24.75"
              />
              <p className="tool-note admission-score-help">
                Nhập tổng điểm xét tuyển theo nguồn tuyển sinh. Nếu đã cộng điểm ưu tiên/khuyến khích, điểm có thể lớn hơn 30.
              </p>
            </label>
          ) : (
            <div className="admission-subject-score-panel">
              <div className="tool-form-grid admission-form-grid">
                {subjectGroupDefinition.subjects.map((subject) => (
                  <label className="tool-field" key={subject.key}>
                    <span>{subject.label}</span>
                    <input
                      className="tool-input"
                      type="number"
                      min="0"
                      max="10"
                      step="0.01"
                      value={subjectScores[subject.key] ?? ''}
                      onChange={(event) =>
                        setSubjectScores((current) => ({ ...current, [subject.key]: event.target.value }))
                      }
                      placeholder="0 - 10"
                    />
                  </label>
                ))}
                <label className="tool-field">
                  <span>Điểm ưu tiên / khuyến khích</span>
                  <input
                    className="tool-input"
                    type="number"
                    min="0"
                    max="3"
                    step="0.01"
                    value={priorityScore}
                    onChange={(event) => setPriorityScore(event.target.value)}
                    placeholder="Nếu có"
                  />
                </label>
              </div>
              <div className="admission-calculated-score">
                <span>Tổng điểm tạm tính</span>
                <strong>{calculatedScore === null ? '--' : formatScore(calculatedScore)}</strong>
              </div>
            </div>
          )}

          <div className="admission-meta-grid">
            <div>
              <span>Khoa phụ trách</span>
              <strong>{selectedFaculty}</strong>
            </div>
            <div>
              <span>Năm dữ liệu mới nhất</span>
              <strong>{latestYear ?? '--'}</strong>
            </div>
            <div>
              <span>Số dòng điểm chuẩn</span>
              <strong>{programRecords.length}</strong>
            </div>
          </div>
        </section>

        <aside className={`tool-result-card admission-result ${estimate.level}`}>
          <ShieldCheck size={28} className="result-icon" />
          <p className="result-label">Mức độ an toàn tham khảo</p>
          {!hasSelectedProgram ? (
            <p className="tool-note">
              Chọn ngành trước để xem mức độ an toàn xét tuyển.
            </p>
          ) : !hasSelectedSubjectGroup ? (
            <p className="tool-note">
              Chọn tổ hợp môn trước để hệ thống so sánh đúng điểm chuẩn theo ngành, phương thức và tổ hợp.
            </p>
          ) : hasScore ? (
            <>
              <div className="admission-result-status">
                <span className={`admission-level-pill ${estimate.level}`}>{estimate.levelLabel}</span>
                {latestCutoffIs2025 && <span className="admission-2025-pill">Điểm chuẩn 2025</span>}
                {latestCutoffNeedsReview && <span className="admission-review-pill">Cần kiểm tra cách tính điểm</span>}
              </div>
              <h3 className="result-title">{estimate.levelLabel}</h3>
              <p className="result-subtitle">{estimate.levelDescription}</p>
              <div className="result-list">
                <div className={latestCutoffIs2025 ? 'admission-key-metric is-2025' : 'admission-key-metric'}>
                  <span>Điểm chuẩn gần nhất</span>
                  <strong>
                    {formatScore(estimate.latestCutoff?.cutoffScore)}
                    {latestCutoffNeedsReview && <ScoreReviewBadge />}
                    {estimate.latestCutoff && <small> năm {estimate.latestCutoff.year}</small>}
                  </strong>
                </div>
                <div>
                  <span>Chênh lệch điểm</span>
                  <strong>{formatDelta(estimate.scoreDelta)}</strong>
                </div>
                <div>
                  <span>Độ tin cậy</span>
                  <strong>{estimate.confidenceLabel}</strong>
                </div>
                <div>
                  <span>So khớp dữ liệu</span>
                  <strong>
                    {estimate.matchScope === 'exact'
                      ? 'Đúng tổ hợp'
                      : estimate.matchScope === 'method'
                        ? 'Cùng phương thức'
                      : 'Cùng ngành'}
                  </strong>
                </div>
                {estimate.latestCutoff && (
                  <div className={latestCutoffIsPost2025 ? 'admission-key-metric post-2025' : 'admission-key-metric'}>
                    <span>Giai đoạn dữ liệu</span>
                    <strong>{getRegimeLabel(estimate.latestCutoff.admissionRegime)}</strong>
                  </div>
                )}
              </div>
              {riskNote && (
                <div className={`admission-risk-note ${estimate.level}`}>
                  <strong>{riskNote.title}</strong>
                  <p>{riskNote.text}</p>
                </div>
              )}
              {estimate.warnings.length > 0 && (
                <ul className="admission-warning-list">
                  {estimate.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="tool-note">
              Nhập tổng điểm xét tuyển để xem mức độ an toàn. Nếu có điểm ưu tiên/khuyến khích, hãy cộng vào trước khi nhập. Hệ thống sẽ ưu tiên so với ngành,
              phương thức và tổ hợp đang chọn.
            </p>
          )}
        </aside>
      </div>

      <section className="tool-panel admission-history">
        <div className="tool-panel-header">
          <div>
            <h2>Lịch sử điểm chuẩn của ngành</h2>
            <p>{ADMISSION_DATA_NOTE}</p>
          </div>
          <div className="admission-history-actions">
            <LineChart size={24} className="text-accent" />
          </div>
        </div>

        <div className="admission-bars">
          {programRecords.slice(0, 8).map((item) => (
            <div className={`admission-bar-row ${item.year === 2025 ? 'is-latest-year' : ''}`} key={item.id}>
              <div className="admission-bar-meta">
                <strong>
                  {item.year}
                  {item.year === 2025 && <span className="admission-inline-badge">Mốc 2025</span>}
                </strong>
                <span>{item.admissionMethodLabel} · {item.subjectGroup}</span>
              </div>
              <div className="admission-bar-track">
                <div className="admission-bar-fill" style={{ width: `${Math.min(100, (item.cutoffScore / historyScoreScale) * 100)}%` }} />
              </div>
              <strong className="admission-bar-score">
                {formatScore(item.cutoffScore)}
                {scoreNeedsReview(item.cutoffScore) && <ScoreReviewBadge />}
              </strong>
            </div>
          ))}
        </div>

        <div className="admission-table-shell">
          <div className="admission-table-scroll-hint" aria-hidden="true">
            <ChevronsLeftRight size={16} />
            <span>Vuốt ngang để xem thêm cột</span>
          </div>
          <div className="admission-table-wrap">
            <table className="data-table admission-table">
              <thead>
                <tr>
                  <th>Năm</th>
                  <th>Ngành</th>
                  <th>Phương thức</th>
                  <th>Tổ hợp</th>
                  <th>Điểm chuẩn</th>
                  <th>Giai đoạn</th>
                  <th>Ghi chú</th>
                  <th>Nguồn</th>
                </tr>
              </thead>
              <tbody>
                {programRecords.map((item) => (
                  <tr key={item.id} className={item.year === 2025 ? 'is-latest-year' : ''}>
                    <td className="admission-col-year">{item.year}</td>
                    <td className="admission-col-program">{item.programName}</td>
                    <td className="admission-col-method">{item.admissionMethodLabel}</td>
                    <td className="admission-col-group">{item.subjectGroup}</td>
                    <td className={`admission-col-score font-medium ${item.year === 2025 ? 'admission-score-2025' : ''} ${scoreNeedsReview(item.cutoffScore) ? 'admission-score-needs-review' : ''}`}>
                      <span className="admission-score-cell">
                        {formatScore(item.cutoffScore)}
                        {scoreNeedsReview(item.cutoffScore) && <ScoreReviewBadge />}
                      </span>
                    </td>
                    <td className="admission-col-regime">
                      <span className={`admission-regime-badge ${item.admissionRegime}`}>
                        {getRegimeLabel(item.admissionRegime)}
                      </span>
                    </td>
                    <td className="admission-col-note">{item.note ?? item.campus}</td>
                    <td className="admission-col-source">
                      <a className="admission-row-source" href={item.sourceUrl} target="_blank" rel="noreferrer">
                        {item.sourceKind === 'html' ? item.year : `Dữ liệu ${item.year}`} <ExternalLink size={13} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {hasSelectedProgram && hasSelectedSubjectGroup && hasScore && nearPrograms.length > 0 && (
        <section className="tool-panel admission-suggestions">
          <h2>Ngành gần mức điểm của bạn</h2>
          <p className="tool-note">
            Danh sách này giúp bạn tham khảo thêm nguyện vọng dự phòng theo điểm chuẩn gần nhất.
          </p>
          <div className="admission-suggestion-grid">
            {nearPrograms.map((item) => (
              <button key={item.id} type="button" onClick={() => selectProgram(item.programName)}>
                <strong>{item.programName}</strong>
                <span>
                  {item.subjectGroup} · {formatScore(item.cutoffScore)} điểm
                  {scoreNeedsReview(item.cutoffScore) && <ScoreReviewBadge />}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="tool-callout info admission-source">
        <h2>Nguồn dữ liệu</h2>
        <p>
          Dữ liệu seed lấy từ bảng điểm chuẩn HCMUE 2021-2025 theo phương thức điểm thi THPT.
          Chức năng này chỉ giữ các dòng của cơ sở chính tại TP.HCM; các dòng ghi chú đào tạo tại Gia Lai hoặc Long An
          trong nguồn gốc không được đưa vào phần tính xác suất.
        </p>
        <div className="admission-source-links">
          {sourceLinksByYear.map(([year, source]) => (
            <a key={year} href={source.sourceUrl} target="_blank" rel="noreferrer">
              {getSourceLinkLabel(year, source.sourceKind)} <ExternalLink size={15} />
            </a>
          ))}
        </div>
        <p className="tool-note">
          Tổng điểm nhập vào nên là điểm xét tuyển theo đúng quy định của phương thức/tổ hợp tương ứng,
          bao gồm điểm ưu tiên nếu nguồn tuyển sinh yêu cầu tính như vậy.
        </p>
      </section>
    </div>
  );
}
