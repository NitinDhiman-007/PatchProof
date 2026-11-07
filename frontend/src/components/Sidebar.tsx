"use client";

import React from "react";

export type NavTab =
  | "overview"
  | "repositories"
  | "analysis"
  | "reports"
  | "settings";

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  systemStatus?: "operational" | "degraded" | "offline" | "loading";
  version?: string;
}

export function Sidebar({
  activeTab,
  onTabChange,
  systemStatus = "loading",
  version = "0.1.0",
}: SidebarProps) {
  const navItems: { id: NavTab; label: string; icon: React.ReactNode }[] = [
    {
      id: "overview",
      label: "Overview",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
    },
    {
      id: "repositories",
      label: "Repositories",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      ),
    },
    {
      id: "analysis",
      label: "Bug Analysis",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
    {
      id: "reports",
      label: "Verification Reports",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
    },
    {
      id: "settings",
      label: "Settings",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col shrink-0 select-none">
      {/* Brand Header */}
      <div className="h-16 flex items-center px-6 border-b border-slate-800/80 gap-3">
        <div className="w-8 h-8 rounded bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        </div>
        <div>
          <div className="text-sm font-semibold tracking-wide text-slate-100 flex items-center gap-1.5">
            PatchProof
            <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-sky-950 text-sky-300 border border-sky-800/40">
              v{version}
            </span>
          </div>
          <div className="text-[10px] text-slate-400 tracking-tight">BharatCode Build League</div>
        </div>
      </div>

      {/* Nav Menu */}
      <nav className="p-3 space-y-1 flex-1">
        <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-wider text-slate-500">
          Platform
        </div>
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                isActive
                  ? "bg-slate-800/90 text-sky-400 border border-slate-700/60 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
              }`}
            >
              <span className={isActive ? "text-sky-400" : "text-slate-400"}>
                {item.icon}
              </span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Backend Engine Status Footer */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/80">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400 font-mono text-[11px]">Backend API</span>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                systemStatus === "operational"
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                  : systemStatus === "degraded"
                  ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]"
                  : systemStatus === "loading"
                  ? "bg-sky-400 animate-pulse"
                  : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]"
              }`}
            />
            <span
              className={`text-[11px] font-mono capitalize ${
                systemStatus === "operational"
                  ? "text-emerald-400"
                  : systemStatus === "degraded"
                  ? "text-amber-400"
                  : systemStatus === "loading"
                  ? "text-sky-400"
                  : "text-rose-400"
              }`}
            >
              {systemStatus}
            </span>
          </div>
        </div>
        <div className="mt-2 text-[10px] text-slate-400 font-mono">
          Isolated Sandbox: <span className="text-slate-400">Armed</span>
        </div>
      </div>
    </aside>
  );
}

