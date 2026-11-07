"use client";

import React, { useState } from "react";
import { api, ApiClientError } from "@/lib/api";
import {
  DockerStatusResponse,
  Repository,
  VerificationReportResponse,
  VerificationRunResponse,
} from "@/types/api";

interface VerificationPanelProps {
  repositories: Repository[];
  verificationRuns: VerificationRunResponse[];
  dockerStatus: DockerStatusResponse | null;
  onRunCompleted: (report: VerificationReportResponse) => void;
}

export function VerificationPanel({
  repositories,
  verificationRuns,
  dockerStatus,
  onRunCompleted,
}: VerificationPanelProps) {
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [commandPreset, setCommandPreset] = useState<string>("pytest");
  const [runRuff, setRunRuff] = useState<boolean>(true);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeReport, setActiveReport] = useState<VerificationReportResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"stdout" | "stderr" | "ruff">("stdout");
  const [isLoadingReport, setIsLoadingReport] = useState<boolean>(false);

  const handleStartVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!selectedRepoId) {
      setError("Please select a target repository to verify.");
      return;
    }

    setIsExecuting(true);
    try {
      const report = await api.startVerification({
        repository_id: selectedRepoId,
        command: commandPreset,
        run_ruff: runRuff,
      });

      setActiveReport(report);
      onRunCompleted(report);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.detail || err.message);
      } else {
        setError("Failed to execute verification run. Verify backend is running.");
      }
    } finally {
      setIsExecuting(false);
    }
  };

  const handleViewHistoricalReport = async (runId: string) => {
    setIsLoadingReport(true);
    try {
      const report = await api.getVerificationReport(runId);
      setActiveReport(report);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.detail || err.message);
      }
    } finally {
      setIsLoadingReport(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "passed":
        return (
          <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-emerald-950 text-emerald-400 border border-emerald-800/60 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            TESTS PASSED
          </span>
        );
      case "failed":
        return (
          <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-rose-950 text-rose-400 border border-rose-800/60 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
            FAILURE ISOLATED (REPRODUCED)
          </span>
        );
      case "timed_out":
        return (
          <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-amber-950 text-amber-400 border border-amber-800/60 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            TIMED OUT
          </span>
        );
      case "error":
      default:
        return (
          <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-red-950 text-red-400 border border-red-800/60 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
            INFRASTRUCTURE ERROR
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Sandbox Trigger & Configuration Panel */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <span>Secure Docker Execution Engine</span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/40">
                Phase 2
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Execute test suites in disposable, unprivileged containers with dropped capabilities and zero network.
            </p>
          </div>

          {/* Docker Daemon Indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono">
            <span
              className={`w-2 h-2 rounded-full ${
                dockerStatus?.docker_available
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"
                  : "bg-amber-400"
              }`}
            />
            <span className="text-slate-400">Docker Engine:</span>
            <span
              className={
                dockerStatus?.docker_available
                  ? "text-emerald-400 font-medium"
                  : "text-amber-400 font-medium"
              }
            >
              {dockerStatus?.docker_available ? "Active" : "Daemon Offline"}
            </span>
          </div>
        </div>

        {!dockerStatus?.docker_available && (
          <div className="mb-4 text-xs font-mono text-amber-300 bg-amber-950/40 border border-amber-800/60 rounded p-3">
            <div className="font-semibold flex items-center gap-1.5 mb-1">
              <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>Docker Daemon Standby Notice</span>
            </div>
            <div className="text-[11px] text-amber-300/80">
              {dockerStatus?.detail || "Docker is not running locally. Start Docker Desktop to enable live container test runs."}
            </div>
          </div>
        )}

        <form onSubmit={handleStartVerification} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Target Repository */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">
                Target Repository *
              </label>
              <select
                value={selectedRepoId}
                onChange={(e) => setSelectedRepoId(e.target.value)}
                disabled={isExecuting || repositories.length === 0}
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500 transition-colors disabled:opacity-50"
              >
                <option value="">
                  {repositories.length === 0
                    ? "No repositories available"
                    : "-- Select registered repository --"}
                </option>
                {repositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name} ({repo.source_type.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>

            {/* Allowlisted Command Preset */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">
                Allowlisted Command Preset *
              </label>
              <select
                value={commandPreset}
                onChange={(e) => setCommandPreset(e.target.value)}
                disabled={isExecuting}
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500 transition-colors"
              >
                <option value="pytest">pytest -v --tb=short (Standard)</option>
                <option value="pytest_verbose">pytest -vv --tb=short (Verbose)</option>
                <option value="pytest_quiet">pytest -q (Compact)</option>
              </select>
            </div>

            {/* Ruff Toggle */}
            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2 cursor-pointer bg-slate-950 border border-slate-800 rounded px-3 py-2 hover:border-slate-700 transition-colors">
                <input
                  type="checkbox"
                  checked={runRuff}
                  onChange={(e) => setRunRuff(e.target.checked)}
                  disabled={isExecuting}
                  className="rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                />
                <span className="text-xs font-mono text-slate-300">
                  Run Ruff Static Analysis
                </span>
              </label>
            </div>
          </div>

          {error && (
            <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-800/60 rounded px-3 py-2 font-mono flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex justify-between items-center pt-1">
            <div className="text-[11px] text-slate-400 font-mono flex items-center gap-2">
              <span>Security constraints:</span>
              <span className="text-slate-300">net=none</span> •
              <span className="text-slate-300">user=1000</span> •
              <span className="text-slate-300">mem=512m</span> •
              <span className="text-slate-300">timeout=30s</span>
            </div>
            <button
              type="submit"
              disabled={isExecuting || !selectedRepoId}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors flex items-center gap-2"
            >
              {isExecuting ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Executing in Sandbox Container...</span>
                </>
              ) : (
                <span>Trigger Isolated Verification Run</span>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Active Evidence Report Card */}
      {activeReport && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div>
              <div className="text-[11px] font-mono text-slate-400">
                Evidence Report • Run ID: <span className="text-sky-400">{activeReport.run_id}</span>
              </div>
              <h3 className="text-base font-semibold text-slate-100 mt-0.5">
                {activeReport.repository_name}
              </h3>
            </div>
            <div className="flex items-center gap-2">
              {getStatusBadge(activeReport.status)}
              <span className="px-2.5 py-1 text-xs font-mono rounded bg-slate-950 border border-slate-800 text-slate-300">
                {activeReport.duration_seconds}s
              </span>
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div className="p-3 rounded bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-[11px] font-mono text-slate-400">Passed Tests</div>
              <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                {activeReport.tests_passed}
              </div>
            </div>
            <div className="p-3 rounded bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-[11px] font-mono text-slate-400">Failed Tests</div>
              <div className={`text-xl font-bold font-mono mt-1 ${
                activeReport.tests_failed > 0 ? "text-rose-400" : "text-slate-300"
              }`}>
                {activeReport.tests_failed}
              </div>
            </div>
            <div className="p-3 rounded bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-[11px] font-mono text-slate-400">Skipped</div>
              <div className="text-xl font-bold font-mono text-slate-300 mt-1">
                {activeReport.tests_skipped}
              </div>
            </div>
            <div className="p-3 rounded bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-[11px] font-mono text-slate-400">Ruff Linter</div>
              <div className={`text-sm font-bold font-mono mt-2 ${
                activeReport.ruff_passed ? "text-emerald-400" : "text-amber-400"
              }`}>
                {activeReport.ruff_passed ? "PASSED" : `${activeReport.ruff_issues.length} Issues`}
              </div>
            </div>
            <div className="p-3 rounded bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-[11px] font-mono text-slate-400">Exit Code</div>
              <div className={`text-xl font-bold font-mono mt-1 ${
                activeReport.exit_code === 0 ? "text-emerald-400" : "text-amber-400"
              }`}>
                {activeReport.exit_code !== null ? activeReport.exit_code : "N/A"}
              </div>
            </div>
          </div>

          {/* Narrative Verdict */}
          <div className="p-3 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
            <span className="text-slate-400 font-semibold">Verdict: </span>
            {activeReport.verification_summary}
          </div>

          {/* Execution Environment & Command */}
          <div className="flex flex-wrap gap-4 text-xs font-mono text-slate-400">
            <div>
              <span className="text-slate-400">Environment: </span>
              <span className="text-slate-200">{activeReport.execution_environment}</span>
            </div>
            <div>
              <span className="text-slate-400">Command: </span>
              <code className="text-sky-400">{activeReport.command}</code>
            </div>
          </div>

          {/* Output Console Streams */}
          <div>
            <div className="flex border-b border-slate-800 mb-2">
              <button
                type="button"
                onClick={() => setActiveTab("stdout")}
                className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                  activeTab === "stdout"
                    ? "border-b-2 border-sky-400 text-sky-400 font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                stdout logs
              </button>
              {activeReport.stderr && (
                <button
                  type="button"
                  onClick={() => setActiveTab("stderr")}
                  className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                    activeTab === "stderr"
                      ? "border-b-2 border-rose-400 text-rose-400 font-semibold"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  stderr logs
                </button>
              )}
              {activeReport.ruff_issues.length > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveTab("ruff")}
                  className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                    activeTab === "ruff"
                      ? "border-b-2 border-amber-400 text-amber-400 font-semibold"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Ruff Findings ({activeReport.ruff_issues.length})
                </button>
              )}
            </div>

            <div className="bg-slate-950 rounded border border-slate-800/80 p-3 font-mono text-xs max-h-64 overflow-y-auto text-slate-300 whitespace-pre-wrap select-text">
              {activeTab === "stdout" && (
                activeReport.stdout ? activeReport.stdout : <span className="text-slate-400">No stdout output produced.</span>
              )}
              {activeTab === "stderr" && (
                activeReport.stderr ? activeReport.stderr : <span className="text-slate-400">No stderr output produced.</span>
              )}
              {activeTab === "ruff" && (
                activeReport.ruff_issues.length > 0 ? (
                  activeReport.ruff_issues.join("\n")
                ) : (
                  <span className="text-emerald-400">No static analysis issues detected.</span>
                )
              )}
            </div>
          </div>
        </div>
      )}

      {/* Historical Verification Runs Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <span>Verification Run History</span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                {verificationRuns.length} Total
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              History of isolated test suite and static check executions.
            </p>
          </div>
        </div>

        {verificationRuns.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-slate-800 rounded-md bg-slate-950/40">
            <svg className="w-8 h-8 text-slate-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <div className="text-xs text-slate-400 font-mono">No verification runs recorded yet.</div>
            <div className="text-[11px] text-slate-400 mt-1">
              Select a repository above and trigger an isolated test run.
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-2 px-3">Run ID</th>
                  <th className="py-2 px-3">Repository</th>
                  <th className="py-2 px-3">Command</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Tests (P/F)</th>
                  <th className="py-2 px-3">Duration</th>
                  <th className="py-2 px-3">Timestamp</th>
                  <th className="py-2 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {verificationRuns.map((run) => (
                  <tr key={run.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3 text-sky-400 font-semibold">
                      {run.id.slice(0, 8)}
                    </td>
                    <td className="py-2.5 px-3 text-slate-200">
                      {run.repository_name || run.repository_id.slice(0, 8)}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 max-w-xs truncate">
                      <code>{run.command}</code>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 text-[10px] rounded uppercase font-semibold ${
                        run.status === "passed"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800/50"
                          : run.status === "failed"
                          ? "bg-rose-950 text-rose-400 border border-rose-800/50"
                          : run.status === "timed_out"
                          ? "bg-amber-950 text-amber-400 border border-amber-800/50"
                          : "bg-red-950 text-red-400 border border-red-800/50"
                      }`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="text-emerald-400">{run.tests_passed}P</span> /{" "}
                      <span className={run.tests_failed > 0 ? "text-rose-400" : "text-slate-400"}>
                        {run.tests_failed}F
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-300">
                      {run.duration_seconds}s
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                      {new Date(run.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={() => handleViewHistoricalReport(run.id)}
                        disabled={isLoadingReport}
                        className="px-2.5 py-1 text-[11px] rounded bg-slate-800 hover:bg-slate-700 text-sky-400 transition-colors border border-slate-700/60"
                      >
                        Inspect Evidence
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

