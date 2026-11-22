import { useState } from 'react';
import { Button, Modal } from './components';

/** Hiện mật khẩu tạm đúng một lần. Đóng hộp thoại là không xem lại được. */
export function CredentialsDialog({ open, title, login, password, onClose, recipient = 'chủ quán' }:
  { open: boolean; title: string; login: string; password: string; onClose: () => void; recipient?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try { await navigator.clipboard.writeText(`Tên đăng nhập: ${login}\nMật khẩu tạm: ${password}`); setCopied(true); } catch { setCopied(false); }
  }

  return (
    <Modal open={open} title={title} onClose={() => { setCopied(false); onClose(); }}
      actions={<><Button onClick={() => void copy()}>{copied ? 'Đã sao chép' : 'Sao chép'}</Button>
        <Button variant="primary" onClick={() => { setCopied(false); onClose(); }}>Đã lưu, đóng lại</Button></>}>
      <p className="muted">Gửi thông tin này cho {recipient}. Mật khẩu tạm chỉ hiện một lần; họ phải đổi mật khẩu khi đăng nhập lần đầu.</p>
      <dl className="credentials">
        <dt>Tên đăng nhập</dt><dd className="num">{login}</dd>
        <dt>Mật khẩu tạm</dt><dd className="num" data-testid="temp-password">{password}</dd>
      </dl>
    </Modal>
  );
}
