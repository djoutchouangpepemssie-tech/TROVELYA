"use client";

import {
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Dialog,
  Distance,
  EmptyState,
  HeartIcon,
  IconButton,
  Input,
  LiquidGlass,
  MessageIcon,
  Price,
  SearchIcon,
  Select,
  Sheet,
  Skeleton,
  Squircle,
  Switch,
  Tabs,
  Toast,
  ToastProvider,
} from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-4">
      <h2 className="text-xl font-semibold">{title}</h2>
      <div className="flex flex-wrap items-center gap-4">{children}</div>
    </section>
  );
}

export function DesignSystemShowcase() {
  const t = useTranslations("DesignSystem");
  const locale = useLocale();
  const [toastOpen, setToastOpen] = useState(false);
  const distanceLabels = { underOneKm: t("underOneKm"), km: (km: number) => t("km", { km }) };

  return (
    <ToastProvider label={t("notificationsRegion")}>
      <main className="mx-auto grid max-w-4xl gap-10 px-4 py-10">
        <header className="grid gap-2">
          <h1 className="text-3xl font-semibold">{t("title")}</h1>
          <p className="text-ink-2">{t("intro")}</p>
        </header>

        <Section title={t("buttons")}>
          <Button>{t("primary")}</Button>
          <Button variant="secondary">{t("secondary")}</Button>
          <Button variant="ghost">{t("ghost")}</Button>
          <Button variant="danger">{t("danger")}</Button>
          <IconButton label={t("search")} icon={<SearchIcon />} />
          <IconButton label={t("favorite")} icon={<HeartIcon />} />
        </Section>

        <Section title={t("fields")}>
          <div className="grid w-full gap-4 sm:grid-cols-2">
            <Input label={t("emailLabel")} type="email" hint={t("emailHint")} />
            <Input
              label={t("emailLabel")}
              type="email"
              error={t("emailError")}
              defaultValue="arcel@"
            />
            <Select
              label={t("conditionLabel")}
              placeholder={t("conditionPlaceholder")}
              options={[
                { value: "new_with_tags", label: t("conditionNew") },
                { value: "very_good", label: t("conditionVeryGood") },
                { value: "good", label: t("conditionGood") },
              ]}
            />
            <div className="grid gap-2">
              <Checkbox label={t("handover")} />
              <Switch label={t("notifications")} />
            </div>
          </div>
        </Section>

        <Section title={t("display")}>
          <Badge tone="brand">{t("badgeVerified")}</Badge>
          <Badge tone="live">{t("badgeLive")}</Badge>
          <Avatar name={t("avatarName")} initials="LV" />
          <Card>
            <p className="font-semibold">{t("price")}</p>
            <Price amountMinor={1850000} currency="EUR" locale={locale} />
          </Card>
          <Card>
            <p className="font-semibold">{t("distance")}</p>
            <Distance meters={392000} labels={distanceLabels} />
          </Card>
          <Skeleton width={160} height={20} />
          <Squircle
            family="blue"
            icon={<MessageIcon />}
            count={3}
            countLabel={t("unread", { count: 3 })}
          />
        </Section>

        <Tabs
          label={t("tabsLabel")}
          tabs={[
            {
              value: "description",
              label: t("tabDescription"),
              content: <p>{t("tabDescriptionContent")}</p>,
            },
            {
              value: "passport",
              label: t("tabPassport"),
              content: <p>{t("tabPassportContent")}</p>,
            },
            { value: "history", label: t("tabHistory"), content: <p>{t("tabHistoryContent")}</p> },
          ]}
        />

        <Section title={t("dialogTitle")}>
          <Dialog
            trigger={<Button variant="secondary">{t("dialogOpen")}</Button>}
            title={t("dialogTitle")}
            description={t("dialogDescription")}
            closeLabel={t("close")}
          >
            <Button>{t("dialogConfirm")}</Button>
          </Dialog>
          <Sheet
            trigger={<Button variant="secondary">{t("sheetOpen")}</Button>}
            title={t("sheetTitle")}
            closeLabel={t("close")}
          >
            <Switch label={t("handover")} />
          </Sheet>
          <Button
            variant="secondary"
            onClick={() => {
              setToastOpen(true);
            }}
          >
            {t("toastOpen")}
          </Button>
          <Toast
            open={toastOpen}
            onOpenChange={setToastOpen}
            title={t("toastTitle")}
            tone="success"
          />
        </Section>

        <EmptyState
          title={t("emptyTitle")}
          description={t("emptyDescription")}
          action={<Button>{t("emptyAction")}</Button>}
        />

        <LiquidGlass className="flex items-center justify-between rounded-[var(--trv-radius-pill)] px-4 py-2">
          <span className="font-semibold">{t("menu")}</span>
          <IconButton label={t("messages")} icon={<MessageIcon />} />
        </LiquidGlass>
      </main>
    </ToastProvider>
  );
}
