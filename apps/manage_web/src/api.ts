export interface Health { status: string; app: string; time: string }

export async function fetchHealth(timeoutMs = 5000): Promise<Health> {
  const response = await fetch('/api/health', { signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok) throw new Error(`Máy chủ trả lỗi (${response.status})`);
  const body = (await response.json()) as Health;
  if (body.app !== 'manage') throw new Error('Đang kết nối nhầm máy chủ (không phải phòng quản lý)');
  return body;
}
