export const money = (amount: number) => new Intl.NumberFormat('vi-VN', {
  style: 'currency', currency: 'VND', maximumFractionDigits: 0,
}).format(amount);

export function duration(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return [Math.floor(value / 3600), Math.floor(value % 3600 / 60), value % 60]
    .map(part => String(part).padStart(2, '0')).join(':');
}

export function dateTime(value: string | null, timezone: string): string {
  return value ? new Intl.DateTimeFormat('vi-VN', {
    timeZone: timezone, dateStyle: 'short', timeStyle: 'medium',
  }).format(new Date(value)) : '—';
}

export const statusLabel: Record<string, string> = {
  EMPTY: 'Sẵn sàng', CANDIDATE: 'Đang quan sát', ACTIVE: 'Đang chơi',
  NEEDS_CONFIRMATION: 'Chờ xác nhận', CLOSED: 'Đã chốt phiên',
};
export const sourceLabel: Record<string, string> = {
  STAFF: 'Nhân viên', STAFF_CONFIRMATION: 'Nhân viên xác nhận', SIMULATED: 'Mô phỏng',
};
export const reasonLabel: Record<string, string> = {
  COOLDOWN: 'Đang chờ sau thanh toán', OUT_OF_ORDER: 'Tín hiệu cũ bị bỏ qua',
  SESSION_ACTIVE: 'Giữ nguyên phiên đang chơi', AMBIGUOUS: 'Vị trí không rõ bàn',
  NO_RELIABLE_PRESENCE: 'Không đủ bằng chứng hiện diện', PRESENCE_PENDING: 'Đang tích lũy thời gian hiện diện',
  CUE_NOT_READY: 'Chưa có detector gậy được kiểm chứng', STAFF_REQUIRED: 'Cần nhân viên xác nhận',
  CONTROLLED_DEMO: 'Mở tự động trong demo mô phỏng',
};
