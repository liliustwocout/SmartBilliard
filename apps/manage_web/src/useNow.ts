import { useEffect, useState } from 'react';

/** Trả về Date.now() cập nhật mỗi `ms`; chỉ để hiển thị đồng hồ chạy, số tiền luôn lấy từ máy chủ. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}
