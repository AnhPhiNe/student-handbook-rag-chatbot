import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, CircleHelp, ExternalLink, GraduationCap, LineChart, Search, ShieldCheck, Sparkles } from 'lucide-react';
import {
  ADMISSION_DATA_NOTE,
  ADMISSION_METHOD_LABELS,
  ADMISSION_RAW_SCORE_SCALE,
  ADMISSION_SCORE_INPUT_MAX,
  type AdmissionMethod,
  type AdmissionCutoff,
} from '../../data/admissions';
import {
  calculateAdmissionTotal,
  getSubjectGroupDefinition,
} from '../../data/admissionSubjectGroups';
import {
  estimateAdmissionChance,
  getAdmissionPlanForProgram,
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

function getSourceLinkLabel(year: number, sourceKind: 'html' | 'api'): string {
  return sourceKind === 'html' ? `Nguồn ${year}` : `Dữ liệu ${year}`;
}

export function AdmissionPage() {
  const inputPanelRef = useRef<HTMLElement | null>(null);
  const [showGuide, setShowGuide] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(ADMISSION_GUIDE_ACK_KEY) !== 'true';
  });
  const [programName, setProgramName] = useState('');
  const [programQuery, setProgramQuery] = useState('');
  const [isProgramSearchOpen, setIsProgramSearchOpen] = useState(true);
  const [admissionMethod, setAdmissionMethod] = useState<AdmissionMethod>('THPT');
  const [subjectGroup, setSubjectGroup] = useState('');
  const [score, setScore] = useState('');
  const [scoreInputMode, setScoreInputMode] = useState<'total' | 'subjects'>('total');
  const [subjectScores, setSubjectScores] = useState<Record<string, string>>({});
  const [priorityScore, setPriorityScore] = useState('');
  const [highlightInputPanel, setHighlightInputPanel] = useState(false);

  const hasSelectedProgram = programName.trim().length > 0;
  const hasSelectedSubjectGroup = subjectGroup.trim().length > 0;
  const canEnterScore = hasSelectedProgram && hasSelectedSubjectGroup;
  const showProgramSearch = !hasSelectedProgram || isProgramSearchOpen;

  const suggestions = useMemo(
    () => (showProgramSearch && programQuery.trim() ? searchAdmissionPrograms(programQuery, 10) : []),
    [programQuery, showProgramSearch],
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
  const formatSubjectGroupOption = (group: string) => {
    const definition = getSubjectGroupDefinition(group);
    const subjects = definition.subjects.map((subject) => subject.label).join(', ');
    return subjects ? `${group} - ${subjects}` : group;
  };
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
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAdmissionMethod(methods[0]);
    }
  }, [methods, admissionMethod]);

  useEffect(() => {
    if (subjectGroup && !subjectGroups.includes(subjectGroup)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
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

  const nearPrograms = useMemo(
    () =>
      getNearScorePrograms(effectiveScore, 6, {
        admissionMethod,
        subjectGroup,
        excludeProgramName: programName,
      }),
    [admissionMethod, effectiveScore, programName, subjectGroup],
  );
  const selectedFaculty = programRecords[0]?.faculty ?? 'Chưa có dữ liệu';
  const riskNote = getRiskNote(estimate.level);
  const latestCutoffIs2025 = estimate.latestCutoff?.year === 2025;
  const latestCutoffNeedsReview = scoreNeedsReview(estimate.latestCutoff?.cutoffScore);
  const visibleWarnings = useMemo(() => {
    if (latestCutoffNeedsReview) {
      return estimate.warnings.slice(0, 1);
    }
    if (estimate.level === 'safe' || estimate.level === 'very_safe') {
      return [];
    }
    return estimate.warnings.slice(0, 1);
  }, [estimate.level, estimate.warnings, latestCutoffNeedsReview]);
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

  const selectProgram = (
    name: string,
    options: { admissionMethod?: AdmissionMethod; subjectGroup?: string; scrollToForm?: boolean } = {},
  ) => {
    const nextMethods = getMethodsForProgram(name);
    const nextMethod =
      options.admissionMethod && nextMethods.includes(options.admissionMethod)
        ? options.admissionMethod
        : nextMethods.includes(admissionMethod)
          ? admissionMethod
          : nextMethods[0] ?? 'THPT';
    const nextSubjectGroups = getSubjectGroupsForProgram(name, nextMethod);
    const nextSubjectGroup =
      options.subjectGroup && nextSubjectGroups.includes(options.subjectGroup)
        ? options.subjectGroup
        : '';

    setProgramName(name);
    setProgramQuery(name);
    setIsProgramSearchOpen(false);
    setAdmissionMethod(nextMethod);
    setSubjectGroup(nextSubjectGroup);

    if (options.scrollToForm) {
      setHighlightInputPanel(true);
      window.setTimeout(() => {
        inputPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 0);
      window.setTimeout(() => setHighlightInputPanel(false), 1400);
    }
  };

  const selectNearProgram = (item: AdmissionCutoff) => {
    const nextSubjectGroups = getSubjectGroupsForProgram(item.programName, item.admissionMethod);
    const preferredSubjectGroup =
      splitAdmissionGroupCodes(item.subjectGroup).find((group) => nextSubjectGroups.includes(group)) ??
      nextSubjectGroups[0] ??
      '';

    selectProgram(item.programName, {
      admissionMethod: item.admissionMethod,
      subjectGroup: preferredSubjectGroup,
      scrollToForm: true,
    });
  };

  const openProgramSearch = () => {
    setIsProgramSearchOpen(true);
    setProgramQuery('');
  };

  const cancelProgramSearch = () => {
    setIsProgramSearchOpen(false);
    setProgramQuery(programName);
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
              khi đặt nguyện vọng theo điểm thi THPTQG.
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
          <div className="admission-scope-badges" aria-label="Phạm vi áp dụng của công cụ tuyển sinh">
            <span>Chỉ dùng điểm thi THPTQG</span>
            <span>Cơ sở chính: 280 An Dương Vương, phường Chợ Quán, TP.HCM</span>
          </div>
          <p>
            Kết quả chỉ là công cụ tham khảo để đặt nguyện vọng, không phải dự đoán chắc chắn.
            Từ năm 2025, chương trình GDPT 2018 làm thay đổi cấu trúc thi và tổ hợp xét tuyển,
            nên dữ liệu 2025 trở đi được ưu tiên hơn dữ liệu xu hướng trước đó.
          </p>
        </div>
      </section>

      <div className="tool-layout split admission-layout">
        <section className={`tool-panel admission-input-panel ${highlightInputPanel ? 'is-highlighted' : ''}`} ref={inputPanelRef}>
          <div className="tool-panel-header">
            <div>
              <h2>Nhập thông tin xét tuyển</h2>
              <p>Dành cho điểm thi THPTQG tại cơ sở chính TP.HCM.</p>
            </div>
            <GraduationCap size={24} className="text-accent admission-panel-icon" />
          </div>

          <div className="admission-stepper" aria-label="Thứ tự nhập thông tin xét tuyển">
            <div className={`admission-step ${hasSelectedProgram ? 'is-done' : 'is-current'}`}>
              <span>{hasSelectedProgram ? <CheckCircle2 size={15} /> : '1'}</span>
              <strong>Chọn ngành</strong>
            </div>
            <div className={`admission-step ${hasSelectedSubjectGroup ? 'is-done' : hasSelectedProgram ? 'is-current' : ''}`}>
              <span>{hasSelectedSubjectGroup ? <CheckCircle2 size={15} /> : '2'}</span>
              <strong>Chọn tổ hợp</strong>
            </div>
            <div className={`admission-step ${canEnterScore && hasScore ? 'is-done' : canEnterScore ? 'is-current' : ''}`}>
              <span>{canEnterScore && hasScore ? <CheckCircle2 size={15} /> : '3'}</span>
              <strong>Nhập điểm</strong>
            </div>
          </div>

          {showProgramSearch && (
            <div className="admission-program-search-panel">
              <label className="tool-field">
                <span>{hasSelectedProgram ? 'Đổi ngành' : 'Tìm ngành'}</span>
                <div className="autocomplete-box">
                  <Search size={18} className="search-icon" />
                  <input
                    className="tool-input"
                    value={programQuery}
                    onChange={(event) => setProgramQuery(event.target.value)}
                    placeholder="Nhập tên ngành, ví dụ: Công nghệ thông tin"
                    autoFocus={hasSelectedProgram}
                  />
                </div>
              </label>
              {hasSelectedProgram && (
                <button type="button" className="admission-cancel-search" onClick={cancelProgramSearch}>
                  Hủy
                </button>
              )}
            </div>
          )}

          {showProgramSearch && programQuery && programQuery !== programName && (
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

          {showProgramSearch && hasSelectedProgram && (
            <div className="admission-selected-program compact">
              <div>
                <span>Ngành hiện tại</span>
                <strong>{programName}</strong>
                <div className="admission-selected-meta">
                  <span className="admission-meta-pill">{selectedFaculty}</span>
                  <span className="admission-meta-pill method">{ADMISSION_METHOD_LABELS[admissionMethod]}</span>
                </div>
              </div>
            </div>
          )}

          {hasSelectedProgram && !isProgramSearchOpen && (
            <>
              <div className="admission-selected-program">
                <div>
                  <span>Ngành đã chọn</span>
                  <strong>{programName}</strong>
                  <div className="admission-selected-meta">
                    <span className="admission-meta-pill">{selectedFaculty}</span>
                    <span className="admission-meta-pill method">{ADMISSION_METHOD_LABELS[admissionMethod]}</span>
                  </div>
                </div>
                <button type="button" onClick={openProgramSearch}>Đổi ngành</button>
              </div>

              {methods.length > 1 && (
                <div className="tool-form-grid admission-form-grid">
                  <label className="tool-field">
                    <span>Phương thức</span>
                    <select
                      className="tool-select"
                      value={admissionMethod}
                      onChange={(event) => setAdmissionMethod(event.target.value as AdmissionMethod)}
                    >
                      {methods.map((method) => (
                        <option key={method} value={method}>
                          {ADMISSION_METHOD_LABELS[method]}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}

              <div className="tool-form-grid admission-form-grid admission-subject-select-row">
                <label className="tool-field">
                  <span>Tổ hợp môn</span>
                  <select
                    className="tool-select"
                    value={subjectGroup}
                    onChange={(event) => setSubjectGroup(event.target.value)}
                  >
                    <option value="" disabled>
                      Chọn tổ hợp môn
                    </option>

                    {subjectGroupOptions.planGroups.length > 0 && (
                      <optgroup label="Theo đề án tuyển sinh 2026">
                        {subjectGroupOptions.planGroups.map((group) => (
                          <option key={group} value={group}>
                            {formatSubjectGroupOption(group)}
                          </option>
                        ))}
                      </optgroup>
                    )}

                    {subjectGroupOptions.historicalGroups.length > 0 && (
                      <optgroup label="Tổ hợp từng dùng các năm trước">
                        {subjectGroupOptions.historicalGroups.map((group) => (
                          <option key={group} value={group}>
                            {formatSubjectGroupOption(group)}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  {!hasSelectedSubjectGroup && (
                    <p className="tool-note admission-inline-help">
                      Ưu tiên tổ hợp trong đề án 2026.
                    </p>
                  )}
                </label>
              </div>
            </>
          )}

          {hasSelectedProgram && hasSelectedSubjectGroup && (!selectedSubjectGroupInPlan || subjectGroupDefinition.note) && (
            <div className="admission-subject-box">
              <div>
                <span>{subjectGroup}</span>
                {subjectGroupDefinition.subjects.length > 0 ? (
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
            </div>
          )}

          {canEnterScore && (
            <>
              <div className="admission-score-heading">
                <span>{scoreInputMode === 'subjects' ? 'Nhập điểm từng môn' : 'Nhập tổng điểm'}</span>
                {subjectGroupDefinition.calculable && (
                  <button
                    type="button"
                    onClick={() => setScoreInputMode(scoreInputMode === 'total' ? 'subjects' : 'total')}
                  >
                    {scoreInputMode === 'total' ? 'Tính từ điểm môn' : 'Nhập tổng điểm'}
                  </button>
                )}
              </div>

              {scoreInputMode === 'total' || !subjectGroupDefinition.calculable ? (
                <label className="tool-field">
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
            </>
          )}

          {selectedPlan && (
            <div className="admission-plan-card">
              <div className="admission-plan-heading">
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
              </div>
              {riskNote && (
                <div className={`admission-risk-note ${estimate.level}`}>
                  <strong>{riskNote.title}</strong>
                  <p>{riskNote.text}</p>
                </div>
              )}
              {visibleWarnings.length > 0 && (
                <ul className="admission-warning-list">
                  {visibleWarnings.map((warning) => (
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
          {programRecords.slice(0, 8).map((item) => {
            const sourceLabel = getSourceLinkLabel(item.year, item.sourceKind);

            return (
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
              <a
                className="admission-row-source"
                href={item.sourceUrl}
                target="_blank"
                rel="noreferrer"
                aria-label={`Mở ${sourceLabel} để kiểm tra điểm chuẩn`}
                title={`Mở ${sourceLabel} để kiểm tra điểm chuẩn`}
              >
                {sourceLabel} <ExternalLink size={13} />
              </a>
            </div>
            );
          })}
        </div>
      </section>

      {hasSelectedProgram && hasSelectedSubjectGroup && hasScore && nearPrograms.length > 0 && (
        <section className="tool-panel admission-suggestions">
          <h2>Ngành cùng tổ hợp gần mức điểm của bạn</h2>
          <p className="tool-note">
            Chỉ hiển thị các ngành cùng phương thức và còn có tổ hợp {subjectGroup} trong đề án tuyển sinh 2026.
          </p>
          <p className="admission-suggestion-note">
            Lưu ý: điểm bên dưới là điểm chuẩn gần nhất trong dữ liệu 2021-2025, không phải điểm chuẩn 2026.
          </p>
          <div className="admission-suggestion-grid">
            {nearPrograms.map((item) => (
              <button key={item.id} type="button" onClick={() => selectNearProgram(item)}>
                <strong>{item.programName}</strong>
                <span className="admission-suggestion-meta">
                  <span>{item.subjectGroup} · {formatScore(item.cutoffScore)} điểm</span>
                  <b>{item.year}</b>
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
          Dữ liệu seed lấy từ bảng điểm chuẩn HCMUE 2021-2025 theo phương thức điểm thi THPTQG.
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
