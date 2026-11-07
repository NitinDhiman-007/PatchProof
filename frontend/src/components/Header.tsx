"use client";

import React from "react";
import { SystemStatusResponse } from "@/types/api";

interface HeaderProps {
  systemStatus: SystemStatusResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export function Header({ systemStatus, isLoading, onRefresh }: HeaderProps) {
  const isHealthy = systemStatus?.status === "operational";

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/40 backdrop-blur px-8 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-4">
        <div>
          <h1 className="text-sm font-semibold tracking-tight text-slate-100 flex items-center gap-2">
            <span>PatchProof Verification Suite</span>
            <span className="text-xs px-2 py-0.5 rounded bg-sky-950/80 border border-sky-700/60 text-sky-300 font-mono">
              Phase 3 • Agentic Debugging
            </span>
          </h1>
          <p className="text-xs text-sky-400 font-medium tracking-tight">
            &ldquo;Don&apos;t trust generated code. Prove it works.&rdquo;
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* API Status Badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-950/80 border border-slate-800 text-xs font-mono">
          <span
            className={`w-2 h-2 rounded-full ${
              isLoading
                ? "bg-sky-400 animate-pulse"
                : isHealthy
                ? "bg-emerald-400"
                : "bg-rose-500"
            }`}
          />
          <span className="text-slate-400">FastAPI:</span>
          <span
            className={
              isHealthy
                ? "text-emerald-400 font-medium"
                : "text-rose-400 font-medium"
            }
          >
            {isLoading ? "checking..." : systemStatus?.status || "offline"}
          </span>
        </div>

        {/* Database Badge */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-950/80 border border-slate-800 text-xs font-mono">
          <span className="text-slate-400">DB:</span>
          <span
            className={
              systemStatus?.database === "connected"
                ? "text-slate-200"
                : "text-rose-400"
            }
          >
            {systemStatus?.database || "unknown"}
          </span>
        </div>

        {/* Refresh Action */}
        <button
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="Refresh status"
          className="p-1.5 rounded-md bg-slate-800/80 hover:bg-slate-700 border border-slate-700/80 text-slate-300 transition-colors disabled:opacity-50"
          title="Refresh Backend Status"
        >
          <svg
            className={`w-4 h-4 ${isLoading ? "animate-spin text-sky-400" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>
    </header>
  );
}

