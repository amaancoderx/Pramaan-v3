"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe, getToken, login as apiLogin, register as apiRegister, setToken, Merchant } from "@/lib/api";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  merchant: Merchant | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; name: string; registered_upi_id: string; registered_receiver_name: string }) => Promise<void>;
  logout: () => void;
  setMerchant: (m: Merchant) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [merchant, setMerchant] = useState<Merchant | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setStatus("anonymous");
      return;
    }
    let cancelled = false;
    getMe()
      .then((m) => {
        if (cancelled) return;
        setMerchant(m);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        setToken(null);
        setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tok = await apiLogin(email, password);
    setToken(tok.access_token);
    setMerchant(tok.merchant);
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (data: { email: string; password: string; name: string; registered_upi_id: string; registered_receiver_name: string }) => {
    const tok = await apiRegister(data);
    setToken(tok.access_token);
    setMerchant(tok.merchant);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setMerchant(null);
    setStatus("anonymous");
  }, []);

  return (
    <AuthContext.Provider value={{ status, merchant, login, register, logout, setMerchant }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
