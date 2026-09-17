import { useState, type KeyboardEvent } from 'react';
import { Search, X } from 'lucide-react';
import { searchTuitionPrograms, type TuitionProgram } from '../../data/tuitionRates';

interface ProgramSearchProps {
  id: string;
  label: string;
  hint?: string;
  query: string;
  selectedProgram: TuitionProgram | null;
  onQueryChange: (query: string) => void;
  onSelect: (program: TuitionProgram) => void;
  onClear: () => void;
}

export function ProgramSearch({
  id,
  label,
  hint,
  query,
  selectedProgram,
  onQueryChange,
  onSelect,
  onClear,
}: ProgramSearchProps) {
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const suggestions = searchTuitionPrograms(query);
  const isOpen = Boolean(query) && !selectedProgram;
  const listId = `${id}-options`;
  const hintId = hint ? `${id}-hint` : undefined;

  const select = (program: TuitionProgram) => {
    onSelect(program);
    setFocusedIndex(-1);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || suggestions.length === 0) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setFocusedIndex((prev) => Math.min(suggestions.length - 1, prev + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setFocusedIndex((prev) => Math.max(0, prev - 1));
    } else if (event.key === 'Enter' && focusedIndex >= 0 && focusedIndex < suggestions.length) {
      event.preventDefault();
      select(suggestions[focusedIndex]);
    }
  };

  return (
    <div className="tool-control">
      <label htmlFor={id}>{label}</label>
      <div className="scholarship-search-box">
        <Search size={16} className="scholarship-search-icon" aria-hidden="true" />
        <input
          id={id}
          type="text"
          role="combobox"
          autoComplete="off"
          className="scholarship-search-input"
          value={query}
          placeholder="VD: Công nghệ thông tin hoặc 7480201"
          aria-expanded={isOpen}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={isOpen && focusedIndex >= 0 ? `${listId}-${focusedIndex}` : undefined}
          aria-describedby={hintId}
          onChange={(e) => {
            onQueryChange(e.target.value);
            setFocusedIndex(-1);
          }}
          onKeyDown={handleKeyDown}
        />
        {query && (
          <button
            type="button"
            className="scholarship-clear-btn"
            onClick={() => {
              onClear();
              setFocusedIndex(-1);
            }}
            aria-label="Xóa ngành đã nhập"
          >
            <X size={14} aria-hidden="true" />
          </button>
        )}
        {isOpen && (
          <div id={listId} role="listbox" className="scholarship-autocomplete-dropdown">
            {suggestions.length > 0 ? (
              suggestions.map((program, index) => (
                <button
                  key={`${program.code}-${program.name}`}
                  id={`${listId}-${index}`}
                  type="button"
                  role="option"
                  aria-selected={index === focusedIndex}
                  className={`scholarship-suggestion-item ${index === focusedIndex ? 'focused' : ''}`}
                  onClick={() => select(program)}
                >
                  <span className="prog-name">{program.name}</span>
                  <span className="prog-code">{program.code}</span>
                </button>
              ))
            ) : (
              <div className="scholarship-suggestion-empty">
                Không tìm thấy ngành phù hợp. Thử gõ tên ngắn hơn hoặc mã ngành.
              </div>
            )}
          </div>
        )}
      </div>
      {hint && <p id={hintId} className="tool-hint">{hint}</p>}
    </div>
  );
}
