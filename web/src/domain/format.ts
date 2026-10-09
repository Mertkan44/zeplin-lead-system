// Display formatting shared by every screen (Turkish locale).

/** Compact number: 1.2M, 34K, 950; '—' when unknown. */
export function fmt(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  if (number === 0) return '0';
  if (number >= 1000000) return (number / 1000000).toFixed(1) + 'M';
  if (number >= 1000) return Math.round(number / 1000) + 'K';
  return String(number);
}

/** "3 Eki 2026"; the input itself when it is not a date. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** "03 Eki 10:00" */
export function fmtShortDateTime(value: string | Date): string {
  return new Date(value).toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export function initialsFor(value: string | null | undefined): string {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'ZM';
  return parts.slice(0, 2).map(part => part.charAt(0).toUpperCase()).join('');
}

export function isToday(value: string | Date | null | undefined): boolean {
  if (!value) return false;
  const date = new Date(value);
  const now = new Date();
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate();
}

/** Value for <input type="datetime-local">: local time, minutes precision. */
export function toDateTimeInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 10:00 local time, `days` days from now. */
export function daysFromNowAtTen(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(10, 0, 0, 0);
  return toDateTimeInput(date);
}
