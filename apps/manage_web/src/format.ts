const ZONE = 'Asia/Ho_Chi_Minh';

/** Backend gửi UTC (ISO, đuôi Z); hiển thị theo giờ Việt Nam. */
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('vi-VN', { timeZone: ZONE, dateStyle: 'short', timeStyle: 'short' }).format(date);
}

/** VND số nguyên do backend tính; chỉ định dạng để hiển thị. */
export function money(vnd: number): string {
  return `${new Intl.NumberFormat('vi-VN').format(Math.round(vnd))} ₫`;
}

export function duration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor((seconds % 3600) / 60))}:${pad(seconds % 60)}`;
}

/** Ngày hôm nay theo giờ Việt Nam, dạng YYYY-MM-DD. */
export function todayVN(now = Date.now()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(now));
}

/** Giờ Việt Nam cố định UTC+7 (không có giờ mùa hè): ghép ngày + số phút trong ngày thành ISO UTC. */
export function slotIso(date: string, minuteOfDay: number): string {
  const hh = String(Math.floor(minuteOfDay / 60)).padStart(2, '0');
  const mm = String(minuteOfDay % 60).padStart(2, '0');
  return new Date(`${date}T${hh}:${mm}:00+07:00`).toISOString();
}

export function clockLabel(minuteOfDay: number): string {
  return `${String(Math.floor(minuteOfDay / 60)).padStart(2, '0')}:${String(minuteOfDay % 60).padStart(2, '0')}`;
}

export function addDays(date: string, days: number): string {
  const base = new Date(`${date}T00:00:00+07:00`);
  base.setUTCDate(base.getUTCDate() + days);
  return todayVN(base.getTime());
}
