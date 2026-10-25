"use client";

import { Dialog as Primitive } from "radix-ui";
import { type ReactNode, useRef } from "react";

import { CloseIcon } from "../icons";
import { IconButton } from "./Button";

type DialogProps = {
  /** Omitted for a dialog opened by code (`open`): focus then returns where it was. */
  trigger?: ReactNode;
  title: string;
  description?: string;
  closeLabel: string;
  children: ReactNode;
  /** "sheet" slides from the bottom on mobile (bottom sheet). */
  presentation?: "dialog" | "sheet";
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

/** Modal dialog (Radix): focus trapped inside, closes on Escape, focus restored on close. */
export function Dialog({
  trigger,
  title,
  description,
  closeLabel,
  children,
  presentation = "dialog",
  ...state
}: DialogProps) {
  // Without a trigger, Radix would give focus back to <body>: remember where it was instead.
  const returnTo = useRef<HTMLElement | null>(null);
  return (
    <Primitive.Root {...state}>
      {trigger ? <Primitive.Trigger asChild>{trigger}</Primitive.Trigger> : null}
      <Primitive.Portal>
        <Primitive.Overlay className="trv-dialog-overlay" />
        <Primitive.Content
          className="trv-dialog"
          data-presentation={presentation}
          onOpenAutoFocus={() => {
            if (!trigger && document.activeElement instanceof HTMLElement) {
              returnTo.current = document.activeElement;
            }
          }}
          onCloseAutoFocus={(event) => {
            if (trigger || !returnTo.current) return;
            event.preventDefault();
            returnTo.current.focus();
            returnTo.current = null;
          }}
          {...(description ? {} : { "aria-describedby": undefined })}
        >
          <div className="trv-dialog-header">
            <Primitive.Title className="trv-dialog-title">{title}</Primitive.Title>
            <Primitive.Close asChild>
              <IconButton label={closeLabel} icon={<CloseIcon />} />
            </Primitive.Close>
          </div>
          {description ? (
            <Primitive.Description className="trv-dialog-description">
              {description}
            </Primitive.Description>
          ) : null}
          {children}
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}

/** Bottom sheet: the dialog presented from the bottom edge. */
export function Sheet(props: Omit<DialogProps, "presentation">) {
  return <Dialog {...props} presentation="sheet" />;
}
