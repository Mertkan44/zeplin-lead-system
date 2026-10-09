import { forwardRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type ReactNode } from 'react';

import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'danger' | 'link';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
}

export function buttonClass({ variant = 'secondary', size = 'md', block = false }: CommonProps, extra?: string): string {
  return [styles.button, styles[variant], styles[size], block ? styles.block : '', extra || ''].filter(Boolean).join(' ');
}

export interface ButtonProps extends CommonProps, ButtonHTMLAttributes<HTMLButtonElement> {
  /** Shows a spinner, disables the button and announces it as busy. */
  busy?: boolean;
  /** Label while busy, e.g. "Kaydediliyor…". */
  busyLabel?: ReactNode;
}

/** Buttons default to type="button": only an explicit submit submits a form. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, block, busy = false, busyLabel, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass({ variant, size, block }, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <span className={styles.spinner} aria-hidden="true" />}
      {busy && busyLabel ? busyLabel : children}
    </button>
  );
});

export interface ButtonLinkProps extends CommonProps, AnchorHTMLAttributes<HTMLAnchorElement> {}

/** A link that looks like a button (tel:, mailto:, external pages). */
export function ButtonLink({ variant, size, block, className, ...rest }: ButtonLinkProps) {
  return <a className={buttonClass({ variant, size, block }, className)} {...rest} />;
}
