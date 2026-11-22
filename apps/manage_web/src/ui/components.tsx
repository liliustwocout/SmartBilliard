import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';
import { FeltTable } from './FeltTable';
import type { FeltState } from './FeltTable';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

export function Button({ variant = 'secondary', size = 'md', block, loading, children, className = '', disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; block?: boolean; loading?: boolean }) {
  const cls = ['btn', `btn-${variant}`, size !== 'md' && `btn-${size}`, block && 'btn-block', className].filter(Boolean).join(' ');
  return (
    <button type="button" {...rest} className={cls} disabled={disabled || loading} aria-busy={loading || undefined}>
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

interface FieldProps { label: string; hint?: string; error?: string }

export function Field({ label, hint, error, id, ...rest }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const auto = useId();
  const fieldId = id ?? auto;
  const describedBy = error ? `${fieldId}-err` : hint ? `${fieldId}-hint` : undefined;
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <input {...rest} id={fieldId} className="input" aria-invalid={error ? true : undefined} aria-describedby={describedBy} />
      {error ? <p className="field-error" id={`${fieldId}-err`} role="alert">{error}</p>
        : hint ? <p className="field-hint" id={`${fieldId}-hint`}>{hint}</p> : null}
    </div>
  );
}

export function SelectField({ label, error, id, children, ...rest }: { label: string; error?: string } & SelectHTMLAttributes<HTMLSelectElement>) {
  const auto = useId();
  const fieldId = id ?? auto;
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <select {...rest} id={fieldId} className="input" aria-invalid={error ? true : undefined}>{children}</select>
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'ok' | 'warn' | 'info' | 'danger'; children: ReactNode }) {
  return <span className={`badge${tone === 'neutral' ? '' : ` badge-${tone}`}`}>{children}</span>;
}

export function Card({ children, flat, className = '' }: { children: ReactNode; flat?: boolean; className?: string }) {
  return <section className={`card${flat ? ' card-flat' : ''} ${className}`.trim()}>{children}</section>;
}

export function Skeleton({ width = '100%', height = 16 }: { width?: number | string; height?: number | string }) {
  return <div className="skeleton" style={{ width, height }} aria-hidden="true" />;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-art"><FeltTable title="" /></div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="empty" role="alert">
      <h2>Có lỗi xảy ra</h2>
      <p>{message}</p>
      {onRetry && <Button onClick={onRetry}>Thử lại</Button>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, label }:
  { tabs: Array<{ id: T; label: string }>; value: T; onChange: (id: T) => void; label: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map(tab => (
        <button key={tab.id} type="button" role="tab" className="tab" aria-selected={tab.id === value}
          tabIndex={tab.id === value ? 0 : -1} onClick={() => onChange(tab.id)}>{tab.label}</button>
      ))}
    </div>
  );
}

export interface Column<Row> { key: string; header: string; render: (row: Row) => ReactNode; align?: 'left' | 'right' }

export function DataTable<Row>({ columns, rows, rowKey, empty }:
  { columns: Array<Column<Row>>; rows: Row[]; rowKey: (row: Row) => string; empty: ReactNode }) {
  if (rows.length === 0) return <div className="table-wrap">{empty}</div>;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead><tr>{columns.map(c => <th key={c.key} scope="col" className={c.align === 'right' ? 'right' : undefined}>{c.header}</th>)}</tr></thead>
        <tbody>{rows.map(row => (
          <tr key={rowKey(row)}>{columns.map(c => <td key={c.key} className={c.align === 'right' ? 'right' : undefined}>{c.render(row)}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function Modal({ open, title, onClose, children, actions }:
  { open: boolean; title: string; onClose: () => void; children: ReactNode; actions?: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close?.();
  }, [open]);
  return (
    <dialog ref={ref} className="modal" aria-label={title} onClose={onClose} onCancel={onClose}>
      <div className="modal-body"><h2>{title}</h2>{children}</div>
      {actions && <div className="modal-actions">{actions}</div>}
    </dialog>
  );
}

/** Hành động không hoàn tác phải qua hộp thoại này; nút xác nhận nêu rõ hành động. */
export function ConfirmDialog({ open, title, description, confirmLabel, danger, onConfirm, onCancel }:
  { open: boolean; title: string; description: string; confirmLabel: string; danger?: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    <Modal open={open} title={title} onClose={onCancel}
      actions={<><Button variant="ghost" onClick={onCancel}>Huỷ</Button>
        <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>{confirmLabel}</Button></>}>
      <p className="muted">{description}</p>
    </Modal>
  );
}

type ToastTone = 'success' | 'error' | 'info';
interface ToastItem { id: number; tone: ToastTone; message: string }
const ToastContext = createContext<(tone: ToastTone, message: string) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const push = useCallback((tone: ToastTone, message: string) => {
    const id = next.current++;
    setItems(list => [...list.slice(-3), { id, tone, message }]);
    setTimeout(() => setItems(list => list.filter(item => item.id !== id)), tone === 'error' ? 8000 : 4500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map(item => (
          <div key={item.id} className={`toast toast-${item.tone}`}>
            <span>{item.message}</span>
            <Button variant="ghost" size="sm" aria-label="Đóng thông báo" onClick={() => setItems(list => list.filter(i => i.id !== item.id))}>✕</Button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const STATE_LABEL: Record<FeltState, { text: string; tone: 'ok' | 'warn' | 'info' }> = {
  free: { text: 'Trống', tone: 'ok' },
  playing: { text: 'Đang chơi', tone: 'warn' },
  reserved: { text: 'Đã đặt', tone: 'info' },
};

/** Thẻ bàn: giá trị đồng hồ/tiền do backend cung cấp, thẻ chỉ hiển thị. */
export function TableCard({ name, state, clock, amount, rate, actions }:
  { name: string; state: FeltState; clock?: string; amount?: string; rate: string; actions?: ReactNode }) {
  const label = STATE_LABEL[state];
  return (
    <article className="table-card" data-state={state} aria-label={`${name}: ${label.text}`}>
      <header><h3>{name}</h3><Badge tone={label.tone}>{label.text}</Badge></header>
      <FeltTable state={state} title={`Mặt ${name.toLowerCase()}`} />
      {state === 'playing' && clock ? (
        <div className="meta">
          <span className="num clock" aria-label="Thời gian đã chơi">{clock}</span>
          <span className="num" style={{ fontSize: 'var(--text-xl)', color: 'var(--ink)' }}>{amount}</span>
        </div>
      ) : (
        <div className="meta" aria-hidden="true">
          <span className="num clock" style={{ color: 'var(--ink-faint)' }}>--:--:--</span>
        </div>
      )}
      <div className="meta"><span>Giá giờ</span><span className="num">{rate}</span></div>
      {actions && <div className="row">{actions}</div>}
    </article>
  );
}
