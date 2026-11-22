import { useEffect, useRef, useState } from 'react';
import type { WheelPrizePublic } from '../api';

const COLORS = ['#f2c230', '#3b82c4', '#d6453d', '#2f9e6e', '#e8812c', '#5b3a8c', '#0e6b6b', '#8a2d2d'];
const SIZE = 300;
const R = 140;

function polar(angle: number, radius: number): [number, number] {
  const rad = ((angle - 90) * Math.PI) / 180;
  return [SIZE / 2 + radius * Math.cos(rad), SIZE / 2 + radius * Math.sin(rad)];
}

/** Chữ chạy dọc theo bán kính và luôn đọc được (không bị lộn ngược ở nửa dưới vòng). */
function labelAngle(mid: number): number {
  return mid < 180 ? mid - 90 : mid + 90;
}

function short(name: string): string {
  return name.length > 14 ? `${name.slice(0, 13)}…` : name;
}

/** Vòng quay: các ô chia đều để dễ nhìn (tỷ lệ thật hiển thị ở bảng bên cạnh). Đích dừng do máy chủ quyết định
 *  (`targetIndex`); component chỉ chạy hoạt ảnh tới đúng ô đó. */
export function Wheel({ prizes, targetIndex, spinning, onDone }:
  { prizes: WheelPrizePublic[]; targetIndex: number | null; spinning: boolean; onDone: () => void }) {
  const [rotation, setRotation] = useState(0);
  const lastTarget = useRef<number | null>(null);
  const slice = 360 / Math.max(1, prizes.length);

  useEffect(() => {
    if (targetIndex === null || targetIndex === lastTarget.current) return;
    lastTarget.current = targetIndex;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const landing = 360 - (targetIndex + 0.5) * slice; // kim chỉ ở đỉnh vòng
    setRotation(previous => Math.ceil(previous / 360) * 360 + (reduced ? 0 : 5 * 360) + landing);
    const timer = setTimeout(onDone, reduced ? 50 : 4200);
    return () => clearTimeout(timer);
  }, [targetIndex, slice, onDone]);

  return (
    <div className="wheel" aria-busy={spinning || undefined}>
      <div className="wheel-pointer" aria-hidden="true" />
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`Vòng quay may mắn gồm ${prizes.length} ô`}
        style={{ transform: `rotate(${rotation}deg)` }} className="wheel-disc">
        {prizes.map((prize, i) => {
          const [x1, y1] = polar(i * slice, R);
          const [x2, y2] = polar((i + 1) * slice, R);
          const [tx, ty] = polar((i + 0.5) * slice, R * 0.62);
          return (
            <g key={prize.id}>
              <path d={`M ${SIZE / 2} ${SIZE / 2} L ${x1} ${y1} A ${R} ${R} 0 0 1 ${x2} ${y2} Z`} fill={COLORS[i % COLORS.length]} stroke="#10282a" strokeWidth="2" />
              <text x={tx} y={ty} textAnchor="middle" dominantBaseline="middle" fontSize="11" fontWeight="700" fill={i % COLORS.length === 0 ? '#10282a' : '#fff'}
                transform={`rotate(${labelAngle((i + 0.5) * slice)} ${tx} ${ty})`}>{short(prize.name)}</text>
            </g>
          );
        })}
        <circle cx={SIZE / 2} cy={SIZE / 2} r="16" fill="#10282a" stroke="#f2c230" strokeWidth="3" />
      </svg>
    </div>
  );
}
