"use client";

import React from "react";
import { Repository } from "@/types/api";

interface RepositoriesListProps {
  repositories: Repository[];
}

export function RepositoriesList({ repositories }: RepositoriesListProps) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <span>Registered Repositories</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
              {repositories.length} Active
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Repositories registered for AST analysis, bug reproduction, and isolated patch testing.
          </p>
        </div>
      </div>

      {repositories.length === 0 ? (
        <div className="text-center py-8 border border-dashed border-slate-800 rounded-md bg-slate-950/40">
          <svg className="w-8 h-8 text-slate-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          <div className="text-xs text-slate-400 font-mono">No repositories registered yet.</div>
          <div className="text-[11px] text-slate-400 mt-1">
            Connect a GitHub URL or upload a ZIP archive above to begin.
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2 px-3">Name</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3">Language</th>
                <th className="py-2 px-3">Branch / Files</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Added</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {repositories.map((repo) => (
                <tr key={repo.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">
                    {repo.git_url ? (
                      <a
                        href={repo.git_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sky-400 hover:underline flex items-center gap-1.5"
                      >
                        <span>{repo.name}</span>
                        <svg className="w-3 h-3 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                    ) : (
                      <span>{repo.name}</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3">
                    <span className={`px-2 py-0.5 text-[10px] rounded uppercase font-semibold ${
                      repo.source_type === "git"
                        ? "bg-purple-950/80 text-purple-400 border border-purple-800/40"
                        : "bg-blue-950/80 text-blue-400 border border-blue-800/40"
                    }`}>
                      {repo.source_type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 capitalize text-slate-300">
                    {repo.detected_language}
                  </td>
                  <td className="py-2.5 px-3 text-slate-400">
                    {repo.source_type === "git"
                      ? repo.default_branch || "main"
                      : `${repo.file_count} files`}
                  </td>
                  <td className="py-2.5 px-3">
                    <span className="px-2 py-0.5 text-[10px] rounded bg-emerald-950 text-emerald-400 border border-emerald-800/40">
                      {repo.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                    {new Date(repo.created_at).toLocaleDateString([], {
                      month: "short",
                      day: "numeric",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

