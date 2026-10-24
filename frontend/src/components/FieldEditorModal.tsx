"use client";

import React, { useEffect, useState } from "react";
import { ApiError, Corrections, submitCorrections, Verification } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Alert, Button, Input, Label, Modal } from "./ui";

const KEYS = ["amount", "utr", "receiver_upi_id", "receiver", "timestamp", "status"] as const;
type Key = (typeof KEYS)[number];

function initialValues(check: Verification): Record<Key, string> {
  const init = {} as Record<Key, string>;
  KEYS.forEach((k) => (init[k] = check.extracted_data[k].value ?? ""));
  return init;
}

export function FieldEditorModal({
  open,
  onClose,
  check,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  check: Verification;
  onSaved: (v: Verification) => void;
}) {
  const { t } = useLanguage();
  const [values, setValues] = useState<Record<Key, string>>(() => initialValues(check));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setValues(initialValues(check));
    setError(null);
  }, [open, check]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const changes: Corrections = {};
    KEYS.forEach((k) => {
      const original = check.extracted_data[k].value ?? "";
      const next = values[k].trim();
      if (next !== original) changes[k] = next || null;
    });
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await submitCorrections(check.id, changes);
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.editor.title}
      description={t.editor.body}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t.editor.cancel}
          </Button>
          <Button type="submit" form="field-editor" loading={busy}>
            {t.editor.save}
          </Button>
        </>
      }
    >
      <form id="field-editor" onSubmit={submit} className="space-y-4">
        {KEYS.map((k) => (
          <div key={k}>
            <Label htmlFor={`f-${k}`}>{t.fields[k]}</Label>
            <Input
              id={`f-${k}`}
              value={values[k]}
              onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
              inputMode={k === "amount" ? "decimal" : k === "utr" ? "numeric" : undefined}
              className={k === "utr" || k === "receiver_upi_id" ? "font-mono" : undefined}
              autoCapitalize="none"
              autoCorrect="off"
            />
          </div>
        ))}
        {error && <Alert tone="danger">{error}</Alert>}
      </form>
    </Modal>
  );
}
