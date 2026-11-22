import { useEffect, useId, useMemo, useRef, useState } from 'react';

export interface ComboOption { value: string; label: string; hint?: string }

/** Bỏ dấu tiếng Việt và hoa/thường để gõ "nguyen" vẫn tìm ra "Nguyễn". */
export function foldText(value: string): string {
  return value.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
}

/** Ô chọn có gõ để tìm (thay cho <select> khi danh sách dài). `value` rỗng = lựa chọn "không chọn" (ví dụ "Tất cả"). */
export function Combobox({ label, value, onChange, options, emptyLabel, placeholder = 'Gõ để tìm…', hint, disabled }:
  { label: string; value: string; onChange: (value: string) => void; options: ComboOption[]; emptyLabel: string; placeholder?: string; hint?: string; disabled?: boolean }) {
  const id = useId();
  const listId = `${id}-list`;
  const wrapper = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const all = useMemo<ComboOption[]>(() => [{ value: '', label: emptyLabel }, ...options], [options, emptyLabel]);
  const selected = all.find(o => o.value === value) ?? all[0];
  const needle = foldText(query.trim());
  const shown = useMemo(() => (needle ? all.filter(o => o.value !== '' && foldText(`${o.label} ${o.hint ?? ''}`).includes(needle)) : all), [all, needle]);

  useEffect(() => { setActive(0); }, [needle, open]);
  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => { if (!wrapper.current?.contains(event.target as Node)) { setOpen(false); setQuery(''); } };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  function pick(option: ComboOption) {
    onChange(option.value);
    setOpen(false); setQuery('');
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setActive(i => Math.min(shown.length - 1, i + 1)); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(0, i - 1)); }
    else if (event.key === 'Enter' && open && shown[active]) { event.preventDefault(); pick(shown[active]); }
    else if (event.key === 'Escape' && open) { event.stopPropagation(); event.preventDefault(); setOpen(false); setQuery(''); }
  }

  return (
    <div className="field combo" ref={wrapper}>
      <label htmlFor={id}>{label}</label>
      <input id={id} className="input" role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list" autoComplete="off" disabled={disabled}
        aria-activedescendant={open && shown[active] ? `${id}-opt-${active}` : undefined}
        placeholder={open ? placeholder : undefined} value={open ? query : selected.label}
        onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onChange={e => { setQuery(e.target.value); setOpen(true); }} onKeyDown={onKeyDown} />
      <span className="combo-caret" aria-hidden="true">▾</span>
      {open && (
        <ul id={listId} role="listbox" aria-label={label} className="combo-list">
          {shown.length === 0 ? <li className="combo-empty" role="presentation">Không có kết quả khớp.</li> : shown.map((option, i) => (
            <li key={option.value || 'empty'} id={`${id}-opt-${i}`} role="option" aria-selected={option.value === value} data-active={i === active || undefined}
              onMouseDown={event => { event.preventDefault(); pick(option); }} onMouseEnter={() => setActive(i)}>
              <span>{option.label}</span>{option.hint && <span className="muted">{option.hint}</span>}
            </li>
          ))}
        </ul>
      )}
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}
