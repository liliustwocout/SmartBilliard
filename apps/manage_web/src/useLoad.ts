import { useCallback, useEffect, useState } from 'react';

export interface Loaded<T> { data: T | null; error: string; loading: boolean; reload: () => void }

/** Tải dữ liệu khi `deps` đổi; bỏ kết quả cũ nếu đã có yêu cầu mới (tránh ghi đè sai thứ tự). */
export function useLoad<T>(load: () => Promise<T>, deps: ReadonlyArray<unknown>): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    load()
      .then(result => { if (!cancelled) setData(result); })
      .catch(reason => { if (!cancelled) setError((reason as Error).message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick(value => value + 1), []);
  return { data, error, loading, reload };
}
