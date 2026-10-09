// Unsaved text the user typed (a note on a lead), kept per key in memory so
// moving to another lead and back does not lose it, and text typed for one
// lead never shows up on another. Cleared with the rest of the session.
import { useEffect, useState } from 'react';

const drafts = new Map<string, string>();

export function clearDrafts(): void {
  drafts.clear();
}

/** Like useState(''), but remembered under `key` until saved or the session ends. */
export function useDraft(key: string): [string, (value: string) => void] {
  const [value, setValue] = useState(() => drafts.get(key) || '');
  useEffect(() => {
    if (value) drafts.set(key, value);
    else drafts.delete(key);
  }, [key, value]);
  return [value, setValue];
}
