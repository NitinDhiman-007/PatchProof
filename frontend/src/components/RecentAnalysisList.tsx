"use client";

import React from "react";
import { BugAnalysisResponse, Repository } from "@/types/api";

interface RecentAnalysisListProps {
  analyses: BugAnalysisResponse[];
  repositories: Repository[];
  onSelectAnalysis?: (analysisId: string) => void;
  selectedAnalysisId?: string | null;
}

export function RecentAnalysisList({
  analyses,
  repositories,
  onSelectAnalysis,
  selectedAnalysisId,
}: RecentAnalysisListProps) {
  const getRepoName = (repoId: string) => {
    const found = repositories.find((r) => r.id === repoId);
    return found ? found.name : repoId.slice(0, 8);
  };

  const getVerdictBadge = (verdict?: string) => {
    switch (verdict) {
      case "VERIFIED":
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
            VERIFIED
          </span>
        );
      case "FAILED":
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-rose-950 text-rose-400 border border-rose-800">
            FAILED
          </span>
        );
      case "INCONCLUSIVE":
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-950 text-amber-400 border border-amber-800">
            INCONCLUSIVE
          </span>
        );
      case "ERROR":
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-rose-950/80 text-rose-400 border border-rose-900">
            ERROR
          </span>
        );
      default:
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-800 text-slate-400 border border-slate-700">
            PENDING
          </span>
        );
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50">
            COMPLETED
          </span>
        );
      case "analyzing":
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-sky-950 text-sky-400 border border-sky-800/50 animate-pulse">
            ANALYZING
          </span>
        );
      case "failed":
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-rose-950 text-rose-400 border border-rose-800/50">
            FAILED
          </span>
        );
      case "pending":
      default:
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-amber-950 text-amber-400 border border-amber-800/50">
            QUEUED
          </span>
        );
    }
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <span>Recent Analysis Runs</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
              {analyses.length} Total
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Audit trail of bug reproduction requests and verification pipelines.
          </p>
        </div>
      </div>

      {analyses.length === 0 ? (
        <div className="text-center py-8 border border-dashed border-slate-800 rounded-md bg-slate-950/40">
          <svg className="w-8 h-8 text-slate-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <div className="text-xs text-slate-400 font-mono">No bug analyses initiated yet.</div>
          <div className="text-[11px] text-slate-400 mt-1">
            Connect a repository and submit a bug report above to start verification.
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2 px-3">Run ID</th>
                <th className="py-2 px-3">Repository</th>
                <th className="py-2 px-3">Verdict</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {analyses.map((run) => {
                const isSelected = selectedAnalysisId === run.id;
                return (
                  <tr
                    key={run.id}
                    onClick={() => onSelectAnalysis && onSelectAnalysis(run.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-sky-950/40 border-l-2 border-sky-500"
                        : "hover:bg-slate-800/30"
                    }`}
                  >
                    <td className="py-2.5 px-3 text-sky-400 font-semibold">
                      {run.id.slice(0, 8)}
                    </td>
                    <td className="py-2.5 px-3 text-slate-200">
                      {getRepoName(run.repository_id)}
                    </td>
                    <td className="py-2.5 px-3">
                      {getVerdictBadge(run.verification_verdict)}
                    </td>
                    <td className="py-2.5 px-3">
                      {getStatusBadge(run.status)}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                      {new Date(run.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

