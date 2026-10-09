import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';

import styles from './Field.module.css';

/** Attributes a control needs to be tied to its label, hint and error. */
export interface ControlProps {
  id: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
}

export interface FieldProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  /** Use a given id (e.g. to keep an existing one stable); generated otherwise. */
  id?: string;
  className?: string;
  children: (control: ControlProps) => ReactNode;
}

/** Label + control + hint/error, wired with htmlFor and aria-describedby. */
export function Field({ label, hint, error, id, className, children }: FieldProps) {
  const generated = useId();
  const controlId = id || generated;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div className={[styles.field, className].filter(Boolean).join(' ')}>
      <label htmlFor={controlId} className={styles.label}>{label}</label>
      {children({ id: controlId, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {hint && <div id={hintId} className={styles.hint}>{hint}</div>}
      {error && <div id={errorId} className={styles.error} role="alert">{error}</div>}
    </div>
  );
}

type Size = 'md' | 'lg';

function controlClass(size: Size | undefined, extra: string | undefined, base = ''): string {
  return [styles.control, base, size === 'lg' ? styles.large : '', extra || ''].filter(Boolean).join(' ');
}

export const Input = forwardRef<HTMLInputElement, Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> & { size?: Size }>(
  function Input({ className, size, ...rest }, ref) {
    return <input ref={ref} className={controlClass(size, className)} {...rest} />;
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={controlClass(undefined, className, styles.textarea)} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...rest }, ref) {
    return <select ref={ref} className={controlClass(undefined, className)} {...rest} />;
  },
);
