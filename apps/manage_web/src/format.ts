const ZONE = 'Asia/Ho_Chi_Minh';

/** Backend gửi UTC (ISO, đuôi Z); hiển thị theo giờ Việt Nam. */
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('vi-VN', { timeZone: ZONE, dateStyle: 'short', timeStyle: 'short' }).format(date);
}
