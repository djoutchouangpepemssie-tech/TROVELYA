import { Toast as Primitive } from "radix-ui";
import type { ReactNode } from "react";

/** Wrap the app once; toasts are announced to screen readers (aria-live). */
export function ToastProvider({ children, label }: { children: ReactNode; label: string }) {
  return (
    <Primitive.Provider label={label} duration={5000}>
      {children}
      <Primitive.Viewport className="trv-toast-viewport" />
    </Primitive.Provider>
  );
}

type ToastProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  tone?: "neutral" | "success" | "danger";
};

export function Toast({ open, onOpenChange, title, description, tone = "neutral" }: ToastProps) {
  return (
    <Primitive.Root className="trv-toast" data-tone={tone} open={open} onOpenChange={onOpenChange}>
      <Primitive.Title className="trv-toast-title">{title}</Primitive.Title>
      {description ? <Primitive.Description>{description}</Primitive.Description> : null}
    </Primitive.Root>
  );
}
