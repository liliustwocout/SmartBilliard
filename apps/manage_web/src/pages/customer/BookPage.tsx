import { useMemo, useState } from 'react';
import { api } from '../../api';
import type { Availability, BookingView } from '../../api';
import { useAuth } from '../../auth';
import { addDays, clockLabel, money, slotIso, todayVN } from '../../format';
import { useLoad } from '../../useLoad';
import { Button, Card, ErrorState, Modal, SelectField, Skeleton, useToast } from '../../ui/components';
import { FeltTable } from '../../ui/FeltTable';
import { DepositDialog } from '../../ui/DepositDialog';

const SLOT_STEP = 30;

export function BookPage() {
  const { state } = useAuth();
  const toast = useToast();
  const venueId = state.status === 'ready' ? state.user.venue?.id ?? 0 : 0;
  const [date, setDate] = useState(todayVN());
  const [tableId, setTableId] = useState<number | null>(null);
  const [duration, setDuration] = useState(60);
  const [slot, setSlot] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pendingPay, setPendingPay] = useState<BookingView | null>(null);
  const availability = useLoad(() => api<Availability>(`/venues/${venueId}/availability?date=${date}`), [venueId, date]);

  const data = availability.data;
  const table = data?.tables.find(t => t.id === (tableId ?? data.tables[0]?.id));
  const serverNow = data ? new Date(data.server_time).getTime() : Date.now();

  const slots = useMemo(() => {
    if (!table) return [];
    const busy = table.busy.map(b => [new Date(b.start_at).getTime(), new Date(b.end_at).getTime()]);
    return Array.from({ length: (24 * 60) / SLOT_STEP }, (_, i) => i * SLOT_STEP).map(minute => {
      const start = new Date(slotIso(date, minute)).getTime();
      const end = start + duration * 60_000;
      return { minute, past: start < serverNow, free: !busy.some(([bs, be]) => bs < end && be > start) };
    }).filter(s => !s.past); // giờ đã qua không hiện
  }, [table, date, duration, serverNow]);

  async function createBooking() {
    if (!table || slot === null) return;
    setBusy(true); setError('');
    try {
      const created = await api<BookingView>(`/venues/${venueId}/my/bookings`, {
        body: { table_id: table.id, start_at: slotIso(date, slot), duration_minutes: duration },
      });
      setConfirming(false); setSlot(null); availability.reload();
      if (created.status === 'PENDING') setPendingPay(created);
      else toast('success', 'Đã đặt bàn.');
    } catch (failure) { setError((failure as Error).message); availability.reload(); } finally { setBusy(false); }
  }

  if (availability.error && !data) return <Card><ErrorState message={availability.error} onRetry={availability.reload} /></Card>;
  if (!data) return <Skeleton height={260} />;

  const today = todayVN();
  const days = Array.from({ length: 15 }, (_, i) => addDays(today, i));
  const endMinute = slot === null ? null : (slot + duration) % (24 * 60);
  const groups = [
    { label: 'Sáng', items: slots.filter(s => s.minute < 12 * 60) },
    { label: 'Chiều', items: slots.filter(s => s.minute >= 12 * 60 && s.minute < 18 * 60) },
    { label: 'Tối', items: slots.filter(s => s.minute >= 18 * 60) },
  ].filter(g => g.items.length > 0);
  return (
    <>
      <div className="page-title"><h1>Đặt bàn</h1></div>
      {data.settings.payment_is_mock && <p className="notice" role="note">Tiền cọc đang ở chế độ mô phỏng: không thu tiền thật.</p>}
      {data.tables.length === 0 ? <Card><p className="muted">Quán chưa mở bàn nào để đặt.</p></Card> : (
        <>
          <section className="book-step" aria-labelledby="step-date">
            <h2 id="step-date"><span className="step-ball">1</span>Chọn ngày</h2>
            <div className="day-strip" role="radiogroup" aria-label="Chọn ngày">
              {days.map(day => {
                const d = new Date(`${day}T12:00:00+07:00`);
                const weekday = day === today ? 'Hôm nay' : d.toLocaleDateString('vi-VN', { weekday: 'short', timeZone: 'Asia/Ho_Chi_Minh' });
                return (
                  <button key={day} type="button" role="radio" aria-checked={day === date} className="day-chip" aria-label={d.toLocaleDateString('vi-VN', { weekday: 'long', day: 'numeric', month: 'numeric', timeZone: 'Asia/Ho_Chi_Minh' })}
                    onClick={() => { setDate(day); setSlot(null); }}>
                    <span>{weekday}</span><strong className="num">{day.slice(8, 10)}</strong><span>Th{Number(day.slice(5, 7))}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="book-step" aria-labelledby="step-table">
            <h2 id="step-table"><span className="step-ball">2</span>Chọn bàn</h2>
            <div className="table-picks" role="radiogroup" aria-label="Chọn bàn">
              {data.tables.map(t => (
                <button key={t.id} type="button" role="radio" aria-checked={t.id === table?.id} className="table-pick"
                  onClick={() => { setTableId(t.id); setSlot(null); }}>
                  <FeltTable state={t.playing_now && date === today ? 'playing' : 'free'} title={`Mặt ${t.name.toLowerCase()}`} />
                  <strong>{t.name}</strong>
                  <span className="num">{money(t.hourly_rate)}/giờ</span>
                  {t.playing_now && date === today && <span className="pick-note">Đang có khách chơi</span>}
                </button>
              ))}
            </div>
          </section>

          <section className="book-step" aria-labelledby="step-time">
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
              <h2 id="step-time"><span className="step-ball">3</span>Chọn giờ</h2>
              <div style={{ minWidth: 130 }}>
                <SelectField label="Thời lượng" value={duration} onChange={e => { setDuration(Number(e.target.value)); setSlot(null); }}>
                  {data.durations.map(m => <option key={m} value={m}>{m % 60 === 0 ? `${m / 60} giờ` : `${m} phút`}</option>)}
                </SelectField>
              </div>
            </div>
            <div className="slots" role="radiogroup" aria-label="Giờ bắt đầu">
              {slots.length === 0 && <p className="muted">{date === today ? 'Hôm nay không còn giờ để đặt. Hãy chọn ngày khác.' : 'Ngày này không còn giờ để đặt.'}</p>}
              {groups.map(group => (
                <div key={group.label} className="slot-group" role="presentation">
                  <span className="slot-group-label" aria-hidden="true">{group.label}</span>
                  <div className="slot-grid" role="presentation">
                    {group.items.map(s => (
                      <button key={s.minute} type="button" role="radio" aria-checked={slot === s.minute} className="slot" disabled={!s.free}
                        onClick={() => setSlot(s.minute)}>{clockLabel(s.minute)}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="slot-legend"><span className="legend-free" aria-hidden="true" />Còn trống<span className="legend-busy" aria-hidden="true" />Đã có người đặt hoặc chồng giờ</p>
          </section>

          <div className="booking-bar">
            <div className="booking-bar-text">
              {table && slot !== null && endMinute !== null ? (
                <><strong>{table.name} · {clockLabel(slot)}–{clockLabel(endMinute)}</strong><span className="muted">{date.slice(8, 10)}/{date.slice(5, 7)} · {money(Math.round(table.hourly_rate * duration / 60))} tiền giờ{data.settings.deposit_amount > 0 ? ` · cọc ${money(data.settings.deposit_amount)}` : ''}</span></>
              ) : <span>Chọn bàn và giờ bắt đầu</span>}
            </div>
            <Button variant="primary" disabled={slot === null} onClick={() => { setError(''); setConfirming(true); }}>Tiếp tục</Button>
          </div>
        </>
      )}

      <Modal open={confirming} title="Xác nhận đặt bàn" onClose={() => setConfirming(false)}
        actions={<><Button variant="ghost" onClick={() => setConfirming(false)}>Quay lại</Button>
          <Button variant="primary" loading={busy} onClick={() => void createBooking()}>{data.settings.deposit_amount > 0 ? 'Đặt bàn và trả cọc' : 'Đặt bàn'}</Button></>}>
        <dl className="credentials">
          <dt>Bàn</dt><dd>{table?.name}</dd>
          <dt>Ngày</dt><dd>{date.slice(8, 10)}/{date.slice(5, 7)}/{date.slice(0, 4)}</dd>
          <dt>Giờ</dt><dd>{slot !== null ? `${clockLabel(slot)} – ${clockLabel((slot + duration) % (24 * 60))}` : ''}</dd>
          <dt>Tiền cọc</dt><dd className="num">{money(data.settings.deposit_amount)}</dd>
        </dl>
        <p className="muted">Huỷ trước giờ hẹn ít nhất {data.settings.refund_before_minutes} phút để được hoàn cọc. Không đến sau {data.settings.noshow_grace_minutes} phút sẽ mất cọc. Cọc được trừ vào hoá đơn khi bạn chơi.</p>
        {error && <p className="field-error" role="alert">{error}</p>}
      </Modal>
      <DepositDialog venueId={venueId} booking={pendingPay} onClose={() => { setPendingPay(null); toast('info', 'Lịch đặt đang chờ cọc. Vào "Lịch đặt" để trả cọc trước khi hết hạn giữ chỗ.'); }}
        onPaid={() => { setPendingPay(null); availability.reload(); toast('success', 'Đã xác nhận lịch đặt.'); }} />
    </>
  );
}
