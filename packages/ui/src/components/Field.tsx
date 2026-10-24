import {
  Checkbox as CheckboxPrimitive,
  Select as SelectPrimitive,
  Switch as SwitchPrimitive,
} from "radix-ui";
import { type InputHTMLAttributes, type ReactNode, useId } from "react";

import { CheckIcon, ChevronDownIcon } from "../icons";

type FieldShellProps = {
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  id: string;
  children: ReactNode;
};

/** Label, hint and error wired to the control (aria-describedby, aria-invalid). */
function FieldShell({ label, hint, error, id, children }: FieldShellProps) {
  return (
    <div className="trv-field">
      <label className="trv-field-label" htmlFor={id}>
        {label}
      </label>
      {children}
      {hint ? (
        <p className="trv-field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="trv-field-error" id={`${id}-error`} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, hint?: string, error?: string): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
};

export function Input({ label, hint, error, id, className, ...props }: InputProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <FieldShell label={label} hint={hint} error={error} id={inputId}>
      <input
        id={inputId}
        className={["trv-input", className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, hint, error)}
        {...props}
      />
    </FieldShell>
  );
}

type Option = { value: string; label: string };
type SelectProps = {
  label: string;
  placeholder: string;
  options: Option[];
  value?: string;
  onValueChange?: (value: string) => void;
  hint?: string;
  error?: string;
};

export function Select({
  label,
  placeholder,
  options,
  value,
  onValueChange,
  hint,
  error,
}: SelectProps) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <SelectPrimitive.Root
        {...(value === undefined ? {} : { value })}
        {...(onValueChange ? { onValueChange } : {})}
      >
        <SelectPrimitive.Trigger
          id={id}
          className="trv-input trv-select-trigger"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, hint, error)}
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <ChevronDownIcon size={18} />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content className="trv-menu" position="popper" sideOffset={4}>
            <SelectPrimitive.Viewport>
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  className="trv-menu-item"
                >
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator>
                    <CheckIcon size={16} />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </FieldShell>
  );
}

type ToggleProps = {
  label: string;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
};

export function Checkbox({ label, checked, onCheckedChange, disabled }: ToggleProps) {
  const id = useId();
  return (
    <div className="trv-toggle-row">
      <CheckboxPrimitive.Root
        id={id}
        className="trv-checkbox"
        {...(checked === undefined ? {} : { checked })}
        {...(onCheckedChange
          ? {
              onCheckedChange: (state: boolean | "indeterminate") => {
                onCheckedChange(state === true);
              },
            }
          : {})}
        {...(disabled ? { disabled } : {})}
      >
        <CheckboxPrimitive.Indicator>
          <CheckIcon size={16} />
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

export function Switch({ label, checked, onCheckedChange, disabled }: ToggleProps) {
  const id = useId();
  return (
    <div className="trv-toggle-row">
      <SwitchPrimitive.Root
        id={id}
        className="trv-switch"
        {...(checked === undefined ? {} : { checked })}
        {...(onCheckedChange ? { onCheckedChange } : {})}
        {...(disabled ? { disabled } : {})}
      >
        <SwitchPrimitive.Thumb className="trv-switch-thumb" />
      </SwitchPrimitive.Root>
      <label htmlFor={id}>{label}</label>
    </div>
  );
}
