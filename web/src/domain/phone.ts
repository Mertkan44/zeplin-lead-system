// Phone numbers for tel: and WhatsApp links (review §12.7). Turkish local
// numbers get the country code; a number we cannot read with certainty gets
// no WhatsApp link rather than a guessed one.

/** Digits of an international number (e.g. 905321234567), or null if unsure. */
export function toInternational(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const text = raw.trim();
  const digits = text.replace(/\D/g, '');
  if (!digits) return null;
  if (text.startsWith('+')) return digits.length >= 8 ? digits : null;
  if (digits.startsWith('00')) return digits.length >= 10 ? digits.slice(2) : null;
  if (digits.startsWith('90') && digits.length === 12) return digits;
  if (digits.startsWith('0') && digits.length === 11) return `90${digits.slice(1)}`;
  if (digits.length === 10 && /^[2-5]/.test(digits)) return `90${digits}`;
  return null;
}

/** tel: link; the raw number without spaces dials fine locally. */
export function telLink(raw: string): string {
  return `tel:${raw.replace(/[^\d+]/g, '')}`;
}

export function whatsappLink(raw: string | null | undefined): string | null {
  const number = toInternational(raw);
  return number ? `https://wa.me/${number}` : null;
}
