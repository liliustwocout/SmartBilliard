import { dateTime, money, sourceLabel } from '../format';
import type { Session, Snapshot } from '../types';

export type HistoryViewProps = {
  data: Snapshot;
  history: Session[];
  historyPage: number;
  historyLoading: boolean;
  onChangePage: (page: number) => void;
};

export function HistoryView({
  data,
  history,
  historyPage,
  historyLoading,
  onChangePage,
}: HistoryViewProps) {
  return (
    <section className="history-panel">
      <div className="section-heading history-heading">
        <div>
          <h2>Phiên đã ghi nhận</h2>
          <p>Doanh thu demo đã chốt được đồng bộ trực tiếp từ máy chủ.</p>
        </div>
        <div className="history-header-meta">
          <div className="history-revenue">
            <span>Doanh thu demo đã chốt</span>
            <strong>{money(data.revenue_vnd)}</strong>
          </div>
          <span className="outline-badge">25 phiên / trang</span>
        </div>
      </div>

      {historyLoading ? (
        <p role="status">Đang tải lịch sử…</p>
      ) : (
        <div className="history-scroll">
          <table>
            <thead>
              <tr>
                <th>Bàn</th>
                <th>Bắt đầu / kết thúc</th>
                <th>Nguồn mở</th>
                <th>Số phút tính phí</th>
                <th>Tiền đã chốt</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {history.map(item => (
                <tr key={item.id}>
                  <td>
                    <strong>Bàn {item.table_id.toString().padStart(2, '0')}</strong>
                    <small>{item.id.slice(0, 8)}</small>
                  </td>
                  <td>
                    {dateTime(item.started_at, data.timezone)}
                    <small>{dateTime(item.ended_at, data.timezone)}</small>
                  </td>
                  <td>
                    {sourceLabel[item.trigger_source] ?? item.trigger_source}
                    {item.evidence_source && <small>Bằng chứng: {sourceLabel[item.evidence_source] ?? 'mô phỏng'}</small>}
                  </td>
                  <td>{item.ended_at ? item.billable_minutes : 'Đang chơi'}</td>
                  <td>{item.total_amount === null ? 'Chưa chốt' : money(item.total_amount)}</td>
                  <td>
                    <span className={`status ${item.status === 'ACTIVE' ? 'active' : 'closed'}`}>
                      {item.status === 'ACTIVE' ? 'Đang chơi' : 'Đã thanh toán demo'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {history.length === 0 && (
            <p className="empty-inline">Chưa có phiên nào. Mở bàn trong trang Tổng quan để bắt đầu.</p>
          )}
        </div>
      )}

      <div className="pagination">
        <button
          type="button"
          className="button subtle"
          disabled={!historyPage || historyLoading}
          onClick={() => onChangePage(historyPage - 1)}
        >
          Trang trước
        </button>
        <span>Trang {historyPage + 1}</span>
        <button
          type="button"
          className="button subtle"
          disabled={history.length < 25 || historyLoading}
          onClick={() => onChangePage(historyPage + 1)}
        >
          Trang sau
        </button>
      </div>
    </section>
  );
}
