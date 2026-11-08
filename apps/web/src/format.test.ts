import { describe, expect, it } from 'vitest';
import { dateTime, duration, money, sourceLabel } from './format';

describe('display server values without calculating fees', () => {
  it('formats elapsed time across an hour without wrapping', () => {
    expect(duration(3661)).toBe('01:01:01');
    expect(duration(-5)).toBe('00:00:00');
    expect(duration(100 * 3600)).toBe('100:00:00');
  });
  it('formats integer VND and preserves simulation provenance', () => {
    expect(money(61000)).toContain('61.000');
    expect(sourceLabel.SIMULATED).toBe('Mô phỏng');
    expect(sourceLabel.STAFF_CONFIRMATION).toBe('Nhân viên xác nhận');
  });
  it('displays UTC timestamps in the configured timezone', () => {
    expect(dateTime('2026-11-08T00:00:00Z', 'Asia/Ho_Chi_Minh')).toContain('07:00:00');
    expect(dateTime(null, 'Asia/Ho_Chi_Minh')).toBe('—');
  });
});
