"use client";

import { WifiOff } from "lucide-react";
import { Button, Card, EmptyState } from "@/components/ui";
import { useLanguage } from "@/context/LanguageContext";

export default function OfflinePage() {
  const { t } = useLanguage();
  return (
    <Card className="mx-auto max-w-md">
      <EmptyState
        icon={<WifiOff className="h-5 w-5" />}
        title={t.offline.title}
        body={t.offline.body}
        action={<Button onClick={() => window.location.reload()}>{t.offline.retry}</Button>}
      />
    </Card>
  );
}
