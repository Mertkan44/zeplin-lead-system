// Modal dialog: focus moves in on open, Tab stays inside, Escape and a click
// outside close it (unless busy), focus returns to the opener on close, and
// the page behind is inert for pointer, keyboard and screen readers.
import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';

import { Button } from './Button';
import styles from './Dialog.module.css';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'summary',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

// Open dialogs, innermost last: only the top one handles Escape and Tab.
const stack: string[] = [];

function focusables(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(element => element.offsetParent !== null || element === document.activeElement);
}

export interface DialogProps {
  /** Visible heading; also the dialog's accessible name. */
  title: ReactNode;
  eyebrow?: ReactNode;
  onClose: () => void;
  /** false while an action runs: Escape, outside click and the close button do nothing. */
  dismissible?: boolean;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  /** center: a card; left/right: a full-height drawer (full screen on phones). */
  placement?: 'center' | 'left' | 'right';
  role?: 'dialog' | 'alertdialog';
  /** Show the close button in the header (default true). */
  closeButton?: boolean;
  /** Element to focus on open; otherwise the first focusable element. */
  initialFocus?: RefObject<HTMLElement>;
  /** Extra element in the header, left of the close button. */
  headerExtra?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export function Dialog({
  title,
  eyebrow,
  onClose,
  dismissible = true,
  size = 'md',
  placement = 'center',
  role = 'dialog',
  closeButton = true,
  initialFocus,
  headerExtra,
  className,
  children,
}: DialogProps) {
  const id = useId();
  const titleId = `${id}-title`;
  const panelRef = useRef<HTMLDivElement>(null);
  // Captured during render, before anything inside the dialog takes focus.
  const [returnTo] = useState(() => document.activeElement as HTMLElement | null);
  const closeRef = useRef(onClose);
  const dismissibleRef = useRef(dismissible);
  closeRef.current = onClose;
  dismissibleRef.current = dismissible;

  useEffect(() => {
    const panel = panelRef.current!;
    const root = document.getElementById('root');
    stack.push(id);
    if (root) root.inert = true;
    document.body.classList.add('dialog-open');
    if (!panel.contains(document.activeElement)) {
      (initialFocus?.current || focusables(panel)[0] || panel).focus();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (stack[stack.length - 1] !== id) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        if (dismissibleRef.current) closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusables(panel);
      if (!items.length) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      stack.splice(stack.indexOf(id), 1);
      if (!stack.length) {
        if (root) root.inert = false;
        document.body.classList.remove('dialog-open');
      }
      if (returnTo && document.contains(returnTo)) returnTo.focus();
    };
    // Runs once per open dialog; latest callbacks are read through refs.
  }, []);

  return createPortal(
    <div
      role="presentation"
      className={[styles.overlay, size === 'xl' ? styles.tall : '', placement !== 'center' ? styles[`drawer-${placement}`] : ''].filter(Boolean).join(' ')}
      onMouseDown={event => {
        if (event.target === event.currentTarget && dismissible) onClose();
      }}
    >
      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={[styles.panel, styles[size], className].filter(Boolean).join(' ')}
      >
        <div className={styles.head}>
          <div>
            {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
            <h2 id={titleId} className={styles.title}>{title}</h2>
          </div>
          {(headerExtra || closeButton) && (
            <div className={styles.footer}>
              {headerExtra}
              {closeButton && <Button onClick={onClose} disabled={!dismissible}>Kapat</Button>}
            </div>
          )}
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

export interface ConfirmDialogProps {
  title: string;
  text: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** The action discards or deletes something: shown in the danger style. */
  destructive?: boolean;
  busyLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Asks before an action with consequences (not for routine saves). */
export function ConfirmDialog({ title, text, confirmLabel, cancelLabel = 'Vazgeç', destructive = false, busyLabel, busy = false, onConfirm, onCancel }: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog title={title} onClose={onCancel} dismissible={!busy} size="sm" role="alertdialog" closeButton={false} initialFocus={cancelRef}>
      <p className={styles.description}>{text}</p>
      <div className={styles.footer}>
        <Button ref={cancelRef} disabled={busy} onClick={onCancel}>{cancelLabel}</Button>
        <Button variant={destructive ? 'danger' : 'primary'} busy={busy} busyLabel={busyLabel} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Dialog>
  );
}

export const dialogStyles = styles;
