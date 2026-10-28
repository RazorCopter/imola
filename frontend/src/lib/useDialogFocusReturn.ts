import { useRef } from "react";
/** Focus restoration for controlled dialogs which have no Radix Trigger. */
export function useDialogFocusReturn(fallbackSelector?: string) {
  const opener = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus: (event: Event) => {
      const active = document.activeElement;
      if (
        active instanceof HTMLElement &&
        active !== document.body &&
        !(event.target instanceof HTMLElement && event.target.contains(active))
      )
        opener.current = active;
    },
    onCloseAutoFocus: (event: Event) => {
      const target =
        (fallbackSelector ? document.querySelector<HTMLElement>(fallbackSelector) : null) ??
        opener.current;
      if (target?.isConnected && target !== document.body) {
        event.preventDefault();
        target.focus();
      }
    },
  };
}
