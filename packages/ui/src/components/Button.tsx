import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

/** Native button; every size keeps a touch target of at least 44 px (section 6.3). */
export function Button({
  variant = "primary",
  size = "md",
  type = "button",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      data-variant={variant}
      data-size={size}
      className={["trv-button", className].filter(Boolean).join(" ")}
      {...props}
    />
  );
}

type IconButtonProps = Omit<ButtonProps, "children" | "aria-label"> & {
  /** Accessible name, required: an icon alone says nothing to a screen reader. */
  label: string;
  icon: ReactNode;
};

export function IconButton({
  label,
  icon,
  variant = "ghost",
  className,
  ...props
}: IconButtonProps) {
  return (
    <Button
      aria-label={label}
      title={label}
      variant={variant}
      className={["trv-icon-button", className].filter(Boolean).join(" ")}
      {...props}
    >
      {icon}
    </Button>
  );
}
