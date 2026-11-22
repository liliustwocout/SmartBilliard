import type { CSSProperties, ReactElement } from 'react';

const BALL_COLORS = ['#f2c230', '#3b82c4', '#d6453d', '#5b3a8c', '#e8812c', '#2f9e6e', '#8a2d2d', '#1b1b1b'];

export type FeltState = 'free' | 'playing' | 'reserved';

interface BallProps { cx: number; cy: number; color: string; index: number; stripe?: boolean }

function Ball({ cx, cy, color, index, stripe }: BallProps) {
  const style = { '--i': index, '--dx': `${(15 - index) * 6}px` } as CSSProperties;
  return (
    <g className="felt-ball" style={style}>
      <circle cx={cx} cy={cy} r="11" fill={stripe ? '#f6f3ea' : color} />
      {stripe && <path d={`M ${cx - 10.2} ${cy - 4} A 11 11 0 0 1 ${cx + 10.2} ${cy - 4} L ${cx + 10.2} ${cy + 4} A 11 11 0 0 1 ${cx - 10.2} ${cy + 4} Z`} fill={color} />}
      <circle cx={cx} cy={cy} r="4.2" fill="#f6f3ea" opacity=".9" />
      <circle cx={cx - 4} cy={cy - 4} r="2.2" fill="#fff" opacity=".45" />
    </g>
  );
}

/** Mặt bàn bi-a nhìn từ trên xuống. `rack` = bày 15 bi + bi cái (dùng ở trang đăng nhập); nếu không, chỉ vẽ mặt bàn. */
export function FeltTable({ rack = false, state, title }: { rack?: boolean; state?: FeltState; title?: string }) {
  const felt = state === 'playing' ? '#12807f' : state === 'reserved' ? '#1c5f8f' : '#0e6b6b';
  const balls: ReactElement[] = [];
  if (rack) {
    let n = 0;
    for (let col = 0; col < 5; col += 1) {
      for (let row = 0; row <= col; row += 1) {
        const cx = 372 + col * 19.5;
        const cy = 170 + (row - col / 2) * 22.5;
        balls.push(<Ball key={n} cx={cx} cy={cy} index={n} color={BALL_COLORS[n % 8]} stripe={n >= 8 && n % 8 !== 7} />);
        n += 1;
      }
    }
    balls.push(<Ball key="cue" cx={170} cy={170} index={15} color="#f6f3ea" />);
  }
  const pockets = [[46, 46], [300, 40], [554, 46], [46, 294], [300, 300], [554, 294]];
  return (
    <svg className={`felt ${rack ? 'rack-in' : ''}`} viewBox="0 0 600 340" role="img" aria-label={title ?? 'Mặt bàn bi-a'}>
      <rect x="4" y="4" width="592" height="332" rx="30" fill="#6b3f23" />
      <rect x="4" y="4" width="592" height="332" rx="30" fill="none" stroke="#8d5a35" strokeWidth="3" />
      <rect x="30" y="30" width="540" height="280" rx="14" fill={felt} />
      <rect x="30" y="30" width="540" height="280" rx="14" fill="none" stroke="#0a4f52" strokeWidth="4" />
      {[[120, 24], [210, 24], [390, 24], [480, 24], [120, 316], [210, 316], [390, 316], [480, 316]].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="3" fill="#e9d9b6" opacity=".85" />
      ))}
      {rack && <line x1="200" y1="36" x2="200" y2="304" stroke="#fff" strokeOpacity=".18" strokeWidth="1.5" />}
      {pockets.map(([x, y]) => <circle key={`p${x}-${y}`} cx={x} cy={y} r="17" fill="#0b1c1d" />)}
      {balls}
    </svg>
  );
}

/** Logo: bi số 8 nhỏ. */
export function BrandBall() {
  return (
    <svg className="brand-ball" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="15" fill="#10282a" stroke="#f2c230" strokeWidth="2" />
      <circle cx="16" cy="16" r="7" fill="#f6f3ea" />
      <text x="16" y="20.2" textAnchor="middle" fontSize="11" fontWeight="700" fill="#10282a" fontFamily="Barlow Condensed, sans-serif">8</text>
    </svg>
  );
}
