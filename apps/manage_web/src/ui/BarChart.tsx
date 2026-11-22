import { useState } from 'react';

export interface Bar { label: string; value: number; detail?: string }

/** Rút gọn số tiền trên trục: 1.500.000 -> "1,5 tr", 45.000 -> "45k". */
export function shortMoney(vnd: number): string {
  if (vnd >= 1_000_000) return `${(vnd / 1_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} tr`;
  if (vnd >= 1_000) return `${Math.round(vnd / 1_000)}k`;
  return String(vnd);
}

/** Làm tròn trần "đẹp" cho trục: 1, 2, 2,5, 5 × 10^n. */
export function niceMax(value: number): number {
  if (value <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(value));
  const norm = value / exp;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return step * exp;
}

const W = 640;
const H = 240;
const PAD = { left: 44, right: 8, top: 12, bottom: 28 };

/** Biểu đồ cột một chuỗi (một màu thương hiệu, không cần chú giải): cột mảnh, đầu cột bo 4px, lưới mờ,
 *  tooltip khi rê chuột/focus bàn phím. `format` định dạng giá trị đầy đủ cho tooltip và nhãn trợ năng. */
export function BarChart({ bars, format, ariaLabel, axisFormat = shortMoney }:
  { bars: Bar[]; format: (value: number) => string; ariaLabel: string; axisFormat?: (value: number) => string }) {
  const [active, setActive] = useState<number | null>(null);
  const max = niceMax(Math.max(0, ...bars.map(b => b.value)));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const slot = innerW / Math.max(1, bars.length);
  const barW = Math.max(2, Math.min(28, slot - 2));
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const labelEvery = Math.max(1, Math.ceil(bars.length / 8));
  const y = (value: number) => PAD.top + innerH - (value / max) * innerH;
  const current = active !== null ? bars[active] : null;

  return (
    <div className="chart" style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel} className="chart-svg">
        {ticks.map(t => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(max * t)} y2={y(max * t)} stroke="var(--line)" strokeWidth="1" />
            <text x={PAD.left - 6} y={y(max * t)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill="var(--ink-faint)">{axisFormat(max * t)}</text>
          </g>
        ))}
        {bars.map((bar, i) => {
          const h = (bar.value / max) * innerH;
          const x = PAD.left + i * slot + (slot - barW) / 2;
          const top = PAD.top + innerH - h;
          const r = Math.min(4, barW / 2, h);
          return (
            <g key={bar.label}>
              {/* vùng bấm rộng hơn cột để dễ rê chuột/chạm */}
              <rect x={PAD.left + i * slot} y={PAD.top} width={slot} height={innerH} fill="transparent"
                onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} />
              {bar.value > 0 && (
                <path tabIndex={0} role="img" aria-label={`${bar.label}: ${format(bar.value)}${bar.detail ? `, ${bar.detail}` : ''}`}
                  d={`M ${x} ${PAD.top + innerH} V ${top + r} Q ${x} ${top} ${x + r} ${top} H ${x + barW - r} Q ${x + barW} ${top} ${x + barW} ${top + r} V ${PAD.top + innerH} Z`}
                  fill="var(--brand)" opacity={active === null || active === i ? 1 : 0.45}
                  onFocus={() => setActive(i)} onBlur={() => setActive(null)} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} />
              )}
              {i % labelEvery === 0 && (
                <text x={x + barW / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--ink-faint)">{bar.label}</text>
              )}
            </g>
          );
        })}
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + innerH} y2={PAD.top + innerH} stroke="var(--line-strong)" strokeWidth="1" />
      </svg>
      {current && (
        <div className="chart-tip" role="status" style={{ left: `${((PAD.left + (active! + 0.5) * slot) / W) * 100}%` }}>
          <strong>{current.label}</strong>
          <span className="num">{format(current.value)}</span>
          {current.detail && <span className="muted">{current.detail}</span>}
        </div>
      )}
    </div>
  );
}
