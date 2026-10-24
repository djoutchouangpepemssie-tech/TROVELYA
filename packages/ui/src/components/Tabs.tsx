import { Tabs as Primitive } from "radix-ui";
import type { ReactNode } from "react";

type Tab = { value: string; label: string; content: ReactNode };

/** Tabs with arrow-key navigation (Radix). */
export function Tabs({
  tabs,
  label,
  defaultValue,
}: {
  tabs: Tab[];
  label: string;
  defaultValue?: string;
}) {
  return (
    <Primitive.Root className="trv-tabs" defaultValue={defaultValue ?? tabs[0]?.value ?? ""}>
      <Primitive.List className="trv-tabs-list" aria-label={label}>
        {tabs.map((tab) => (
          <Primitive.Trigger key={tab.value} value={tab.value} className="trv-tabs-trigger">
            {tab.label}
          </Primitive.Trigger>
        ))}
      </Primitive.List>
      {tabs.map((tab) => (
        <Primitive.Content key={tab.value} value={tab.value} className="trv-tabs-content">
          {tab.content}
        </Primitive.Content>
      ))}
    </Primitive.Root>
  );
}
