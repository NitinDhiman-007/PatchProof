"use client";

import React from "react";
import { SystemStatusResponse } from "@/types/api";

interface VerificationCardsProps {
  systemStatus: SystemStatusResponse | null;
  repositoriesCount: number;
  analysesCount: number;
  verificationRunsCount?: number;
  dockerAvailable?: boolean;
}

export function VerificationCards({
  systemStatus,
  repositoriesCount,
  analysesCount,
  verificationRunsCount = 0,
  dockerAvailable = false,
}: VerificationCardsProps) {
  const isBharatCodeConfigured = !!systemStatus?.bharatcode_configured;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Connected Repositories */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">Repositories</span>
          <div className="w-6 h-6 rounded bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
        </div>
        <div className="mt-2 text-2xl font-bold font-mono text-slate-100">
          {repositoriesCount}
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          Validated Git URLs & ZIP archives
        </div>
      </div>

      {/* Analysis Runs & Verification */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">Verifications Run</span>
          <div className="w-6 h-6 rounded bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
        </div>
        <div className="mt-2 text-2xl font-bold font-mono text-slate-100">
          {verificationRunsCount}
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {analysesCount} bug analyses queued
        </div>
      </div>

      {/* Execution Sandbox Isolation */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">Docker Sandbox</span>
          <div className={`w-6 h-6 rounded border flex items-center justify-center ${
            dockerAvailable
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
              : "bg-amber-500/10 border-amber-500/20 text-amber-400"
          }`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
        </div>
        <div className={`mt-2 text-xl font-bold font-mono flex items-center gap-1.5 ${
          dockerAvailable ? "text-emerald-400" : "text-amber-400"
        }`}>
          <span>{dockerAvailable ? "Operational" : "Standby"}</span>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {dockerAvailable ? "Disposable containers enabled" : "Start Docker Desktop"}
        </div>
      </div>

      {/* BharatCode Model API */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">BharatCode AI</span>
          <div className={`w-6 h-6 rounded border flex items-center justify-center ${
            isBharatCodeConfigured
              ? "bg-sky-500/10 border-sky-500/20 text-sky-400"
              : "bg-amber-500/10 border-amber-500/20 text-amber-400"
          }`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
        </div>
        <div className={`mt-2 text-xl font-bold font-mono ${
          isBharatCodeConfigured ? "text-sky-400" : "text-amber-400"
        }`}>
          {isBharatCodeConfigured ? "Connected" : "Key Needed"}
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {isBharatCodeConfigured
            ? "API credentials loaded from env"
            : "Set BHARATCODE_API_KEY in .env"}
        </div>
      </div>
    </div>
  );
}

