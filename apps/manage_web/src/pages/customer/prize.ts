import type { PrizeKind } from '../../api';
import { money } from '../../format';

export const REASON: Record<string, string> = { checkin: 'Check-in', streak_bonus: 'Thưởng chuỗi ngày', wheel: 'Vòng quay may mắn' };

export function prizeText(kind: PrizeKind, value: number, name: string): string {
  if (kind === 'points') return `+${value} điểm`;
  if (kind === 'discount_vnd') return `Giảm ${money(value)}`;
  if (kind === 'free_minutes') return `Miễn phí ${value} phút chơi`;
  return name;
}
