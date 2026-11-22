import type { BookingStatus, DepositStatus } from './api';

export const BOOKING_LABEL: Record<BookingStatus, { text: string; tone: 'ok' | 'warn' | 'info' | 'danger' | 'neutral' }> = {
  PENDING: { text: 'Chờ trả cọc', tone: 'warn' },
  CONFIRMED: { text: 'Đã xác nhận', tone: 'ok' },
  CHECKED_IN: { text: 'Đang chơi', tone: 'info' },
  CANCELLED: { text: 'Đã huỷ', tone: 'neutral' },
  EXPIRED: { text: 'Hết hạn giữ chỗ', tone: 'neutral' },
  NO_SHOW: { text: 'Không đến', tone: 'danger' },
};

export const DEPOSIT_LABEL: Record<DepositStatus, string> = {
  PENDING: 'Chưa trả', PAID: 'Đã cọc', APPLIED: 'Đã trừ vào hoá đơn', REFUNDED: 'Đã hoàn', FORFEITED: 'Mất cọc', CANCELLED: 'Đã huỷ',
};
