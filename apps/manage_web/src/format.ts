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
