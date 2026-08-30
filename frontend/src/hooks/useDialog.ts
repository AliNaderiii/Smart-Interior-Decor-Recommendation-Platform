import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

export interface UseDialogOptions {
  isOpen?: boolean;
  onClose: () => void;
  containerRef: RefObject<HTMLElement | null>;
  initialFocusRef?: RefObject<HTMLElement | null>;
  restoreFocus?: boolean;
  trapFocus?: boolean;
  closeOnEscape?: boolean;
  lockScroll?: boolean;
}

/**
 * Shared accessible modal dialog hook (WCAG 2.1.2 / 2.4.3).
 *
 * Provides:
 * 1. Document-level Escape key handling (closing regardless of where focus sits).
 * 2. Focus trapping within the dialog container.
 * 3. Restoring focus to the triggering element upon dialog unmount/close.
 * 4. Document body scroll lock while modal is open.
 */
export function useDialog({
  isOpen = true,
  onClose,
  containerRef,
  initialFocusRef,
  restoreFocus = true,
  trapFocus = true,
  closeOnEscape = true,
  lockScroll = true,
}: UseDialogOptions): void {
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // 1. Remember previously focused element for restoration
    if (typeof document !== "undefined") {
      previousActiveElementRef.current = document.activeElement as HTMLElement | null;
    }

    // 2. Lock body scroll if requested
    const originalOverflow = typeof document !== "undefined" ? document.body.style.overflow : "";
    if (lockScroll && typeof document !== "undefined") {
      document.body.style.overflow = "hidden";
    }

    // 3. Set initial focus
    const timer = setTimeout(() => {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus();
      } else if (containerRef.current) {
        const firstFocusable = containerRef.current.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
        if (firstFocusable) {
          firstFocusable.focus();
        } else {
          containerRef.current.focus();
        }
      }
    }, 10);

    // 4. Global keydown handler for Escape and Focus Trap (Tab/Shift+Tab)
    function handleKeyDown(e: KeyboardEvent) {
      if (closeOnEscape && e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }

      if (trapFocus && e.key === "Tab" && containerRef.current) {
        const focusableElements = Array.from(
          containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        ).filter((el) => el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);

        if (focusableElements.length === 0) {
          e.preventDefault();
          return;
        }

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement || !containerRef.current.contains(document.activeElement)) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement || !containerRef.current.contains(document.activeElement)) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    }

    if (typeof document !== "undefined") {
      document.addEventListener("keydown", handleKeyDown, true);
    }

    return () => {
      clearTimeout(timer);
      if (lockScroll && typeof document !== "undefined") {
        document.body.style.overflow = originalOverflow;
      }
      if (typeof document !== "undefined") {
        document.removeEventListener("keydown", handleKeyDown, true);
      }
      if (restoreFocus && previousActiveElementRef.current) {
        previousActiveElementRef.current.focus?.();
      }
    };
  }, [isOpen, onClose, containerRef, initialFocusRef, restoreFocus, trapFocus, closeOnEscape, lockScroll]);
}
