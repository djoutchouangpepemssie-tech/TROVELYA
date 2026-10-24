import { Dialog as Primitive } from "radix-ui";
import type { ReactNode } from "react";

import { CloseIcon } from "../icons";
import { IconButton } from "./Button";

type DialogProps = {
  trigger: ReactNode;
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
  return (
    <Primitive.Root {...state}>
      <Primitive.Trigger asChild>{trigger}</Primitive.Trigger>
      <Primitive.Portal>
        <Primitive.Overlay className="trv-dialog-overlay" />
        <Primitive.Content
          className="trv-dialog"
          data-presentation={presentation}
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
