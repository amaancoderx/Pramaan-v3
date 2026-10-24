"use client";

import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { useLanguage } from "@/context/LanguageContext";

export function useOnline() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

export function OfflineBanner() {
  const online = useOnline();
  const { t } = useLanguage();
  if (online) return null;
  return (
    <div role="status" className="flex items-center justify-center gap-2 bg-suspicious px-4 py-2 text-center text-sm font-medium text-white">
      <WifiOff className="h-4 w-4 shrink-0" aria-hidden />
      <span>{t.offline.banner}</span>
    </div>
  );
}
