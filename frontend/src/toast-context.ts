import { createContext } from "react";

export type ToastMessage = {
  id: number;
  message: string;
  tone: "success" | "error";
};

export type ToastContextValue = {
  showToast: (message: string, tone?: ToastMessage["tone"]) => void;
};

export const ToastContext = createContext<ToastContextValue | null>(null);
