"use client";

import React, { useEffect, useState } from "react";
import { api, ApiClientError } from "@/lib/api";
import {
  BugAnalysisResponse,
  ModelStatusResponse,
  ProposedPatchResponse,
  ReproductionTestResponse,
  Repository,
  RootCauseResponse,
  WorkflowEventResponse,
} from "@/types/api";

interface BugAnalysisPanelProps {
  repositories: Repository[];
  onAnalysisStarted?: (run: BugAnalysisResponse) => void;
  selectedAnalysisId?: string | null;
}

type DetailTab = "events" | "root_cause" | "test" | "patch" | "evidence";

export function BugAnalysisPanel({
  repositories,
  onAnalysisStarted,
  selectedAnalysisId: propSelectedId,
}: BugAnalysisPanelProps) {
  // Form State
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [bugDescription, setBugDescription] = useState<string>("");
  const [issueUrl, setIssueUrl] = useState<string>("");
  const [stackTrace, setStackTrace] = useState<string>("");
  const [showStackTraceInput, setShowStackTraceInput] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Model Status Telemetry
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);

  // Active Analysis State
  const [activeAnalysisId, setActiveAnalysisId] = useState<string | null>(propSelectedId || null);
  const effectiveAnalysisId = propSelectedId || activeAnalysisId;
  const [activeAnalysis, setActiveAnalysis] = useState<BugAnalysisResponse | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("events");
  const [events, setEvents] = useState<WorkflowEventResponse[]>([]);
  const [rootCause, setRootCause] = useState<RootCauseResponse | null>(null);
  const [reproTest, setReproTest] = useState<ReproductionTestResponse | null>(null);
  const [proposedPatch, setProposedPatch] = useState<ProposedPatchResponse | null>(null);
  const [evidenceReport, setEvidenceReport] = useState<Record<string, unknown> | null>(null);

  // Human Review State
  const [approvalComment, setApprovalComment] = useState<string>("");
  const [isReviewing, setIsReviewing] = useState<boolean>(false);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);

  // Initial Model Connectivity Check
  useEffect(() => {
    let mounted = true;
    api.getModelStatus()
      .then((res) => {
        if (mounted) setModelStatus(res);
      })
      .catch(() => {
        if (mounted) {
          setModelStatus({
            configured: false,
            reachable: false,
            model: "qwen-3.8-27b",
            base_url: "https://bharatcode.ai/api/model/v1",
            message: "Unable to contact BharatCode model status endpoint.",
          });
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Poll active analysis if it's running
  useEffect(() => {
    if (!effectiveAnalysisId) return;

    let isMounted = true;
    const fetchRunDetails = async () => {
      try {
        const [analysisData, eventList] = await Promise.all([
          api.getAnalysisStatus(effectiveAnalysisId),
          api.getAnalysisEvents(effectiveAnalysisId),
        ]);

        if (!isMounted) return;
        setActiveAnalysis(analysisData);
        setEvents(eventList);

        // Fetch sub-resources if available
        if (analysisData.root_cause_json) {
          api.getRootCause(effectiveAnalysisId).then((r) => isMounted && setRootCause(r)).catch(() => {});
        }
        if (analysisData.reproduction_test_code) {
          api.getReproductionTest(effectiveAnalysisId).then((t) => isMounted && setReproTest(t)).catch(() => {});
        }
        if (analysisData.patch_diff) {
          api.getProposedPatch(effectiveAnalysisId).then((p) => isMounted && setProposedPatch(p)).catch(() => {});
        }
        if (analysisData.evidence_report_json) {
          api.getEvidenceReport(effectiveAnalysisId).then((e) => isMounted && setEvidenceReport(e)).catch(() => {});
        }
      } catch (err) {
        console.warn("Polling error for analysis run:", err);
      }
    };

    fetchRunDetails();

    // Set polling interval if status is 'analyzing' or 'pending'
    const interval = setInterval(() => {
      if (activeAnalysis?.status === "completed" || activeAnalysis?.status === "failed") {
        clearInterval(interval);
      } else {
        fetchRunDetails();
      }
    }, 2500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [effectiveAnalysisId, activeAnalysis?.status]);

  // Form Submit Handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!selectedRepoId) {
      setFormError("Please select a target repository.");
      return;
    }

    if (bugDescription.trim().length < 10) {
      setFormError("Please describe the bug in at least 10 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      const run = await api.startBugAnalysis({
        repository_id: selectedRepoId,
        bug_description: bugDescription.trim(),
        issue_url: issueUrl.trim() || undefined,
        stack_trace: stackTrace.trim() || undefined,
      });

      setActiveAnalysisId(run.id);
      setActiveAnalysis(run);
      setActiveTab("events");
      setBugDescription("");
      setIssueUrl("");
      setStackTrace("");
      setShowStackTraceInput(false);

      if (onAnalysisStarted) {
        onAnalysisStarted(run);
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setFormError(err.detail || err.message);
      } else {
        setFormError("Failed to initialize bug analysis. Check backend connectivity.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Human Approval Action Handler
  const handleReviewAction = async (decision: "approved" | "rejected") => {
    if (!effectiveAnalysisId) return;
    setIsReviewing(true);
    setReviewMessage(null);
    try {
      await api.approvePatch(effectiveAnalysisId, decision, approvalComment.trim() || undefined);
      setReviewMessage(`Patch successfully marked as ${decision.toUpperCase()}.`);
      // Update local state
      if (activeAnalysis) {
        setActiveAnalysis({
          ...activeAnalysis,
          patch_status: decision,
        });
      }
      if (proposedPatch) {
        setProposedPatch({
          ...proposedPatch,
          patch_status: decision,
        });
      }
      // Refresh event stream
      const newEvents = await api.getAnalysisEvents(effectiveAnalysisId);
      setEvents(newEvents);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setReviewMessage(`Review error: ${err.detail}`);
      } else {
        setReviewMessage("Failed to update patch review status.");
      }
    } finally {
      setIsReviewing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Analysis Submission Panel */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <span>Automated Bug Analysis & LangGraph Agent Loop</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/40">
                Phase 3 Active
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Analyzes repository code, designs failing pytest reproduction tests, generates minimal unified patches, and proves them in isolated Docker containers.
            </p>
          </div>

          {/* Model Connectivity Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-[11px] font-mono shrink-0">
            <span
              className={`w-2 h-2 rounded-full ${
                modelStatus?.reachable
                  ? "bg-emerald-400"
                  : modelStatus?.configured
                  ? "bg-amber-400"
                  : "bg-slate-600"
              }`}
            />
            <span className="text-slate-400">BharatCode:</span>
            <span className="text-slate-200">
              {modelStatus?.model || "qwen-3.8-27b"}
            </span>
            <span
              className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                modelStatus?.reachable
                  ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/40"
                  : "bg-slate-800 text-slate-400"
              }`}
            >
              {modelStatus?.reachable ? "Online" : modelStatus?.configured ? "Standby" : "Unconfigured"}
            </span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Target Repository Selector */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">
                Target Repository *
              </label>
              <select
                value={selectedRepoId}
                onChange={(e) => setSelectedRepoId(e.target.value)}
                disabled={isSubmitting || repositories.length === 0}
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500 transition-colors disabled:opacity-50"
              >
                <option value="">
                  {repositories.length === 0
                    ? "No repositories registered yet"
                    : "-- Select registered repository --"}
                </option>
                {repositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name} ({repo.source_type.toUpperCase()} • {repo.detected_language})
                  </option>
                ))}
              </select>
            </div>

            {/* Optional Issue URL */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">
                Issue Reference URL (Optional)
              </label>
              <input
                type="text"
                value={issueUrl}
                onChange={(e) => setIssueUrl(e.target.value)}
                placeholder="https://github.com/owner/repo/issues/42"
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 transition-colors"
                disabled={isSubmitting}
              />
            </div>
          </div>

          {/* Bug Description */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="block text-xs font-mono text-slate-400">
                Bug Report / Observed Defect *
              </label>
              <span className="text-[11px] font-mono text-slate-500">
                {bugDescription.length} / 10000
              </span>
            </div>
            <textarea
              value={bugDescription}
              onChange={(e) => setBugDescription(e.target.value)}
              rows={4}
              placeholder={`Example:
The calculate_discount(price, discount) function returns an incorrect result when discount is given as a percentage.
Expected: calculate_discount(1000, 20) == 800
Actual: calculate_discount(1000, 20) == -19000`}
              className="w-full bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 transition-colors resize-y"
              disabled={isSubmitting}
            />
          </div>

          {/* Optional Stack Trace Toggle */}
          <div>
            <button
              type="button"
              onClick={() => setShowStackTraceInput(!showStackTraceInput)}
              className="text-xs font-mono text-sky-400 hover:text-sky-300 flex items-center gap-1.5 transition-colors"
            >
              <span>{showStackTraceInput ? "▼ Hide Stack Trace" : "▶ Add Stack Trace / Execution Traceback (Optional)"}</span>
            </button>
            {showStackTraceInput && (
              <div className="mt-2">
                <textarea
                  value={stackTrace}
                  onChange={(e) => setStackTrace(e.target.value)}
                  rows={4}
                  placeholder={`Traceback (most recent call last):
  File "calculator/discount.py", line 8, in calculate_discount
    return price - (price * discount)
AssertionError: Expected 800 but got -19000`}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 transition-colors resize-y"
                  disabled={isSubmitting}
                />
              </div>
            )}
          </div>

          {formError && (
            <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-800/60 rounded px-3 py-2 font-mono flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              <span>{formError}</span>
            </div>
          )}

          <div className="flex justify-between items-center pt-1">
            <div className="text-[11px] text-slate-500 font-mono">
              Enforces reproduction before patch generation. Requires human approval before export.
            </div>
            <button
              type="submit"
              disabled={isSubmitting || !selectedRepoId || bugDescription.trim().length < 10}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Dispatching LangGraph Workflow...</span>
                </>
              ) : (
                <span>Analyze Bug & Prove Patch</span>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* 2. Active Analysis Workflow Stepper & Telemetry */}
      {activeAnalysis && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5 space-y-5">
          {/* Active Run Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-sm font-semibold text-slate-100 font-mono">
                  Run {activeAnalysis.id.slice(0, 8)}
                </h3>
                {/* Verdict Badge */}
                <span
                  className={`text-xs px-2.5 py-0.5 rounded font-mono font-bold tracking-wide border ${
                    activeAnalysis.verification_verdict === "VERIFIED"
                      ? "bg-emerald-950 text-emerald-400 border-emerald-600"
                      : activeAnalysis.verification_verdict === "FAILED"
                      ? "bg-rose-950 text-rose-400 border-rose-600"
                      : activeAnalysis.verification_verdict === "INCONCLUSIVE"
                      ? "bg-amber-950 text-amber-400 border-amber-600"
                      : activeAnalysis.verification_verdict === "ERROR"
                      ? "bg-rose-950/80 text-rose-300 border-rose-800"
                      : "bg-slate-800 text-sky-400 border-slate-700 animate-pulse"
                  }`}
                >
                  VERDICT: {activeAnalysis.verification_verdict || "PENDING"}
                </span>

                {/* Status Pill */}
                <span className="text-[11px] font-mono text-slate-400">
                  [{activeAnalysis.status.toUpperCase()}]
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 line-clamp-1">
                {activeAnalysis.summary || "Agentic debugging workflow active."}
              </p>
            </div>

            {/* Patch Human Approval Badge */}
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-slate-400">Patch Approval:</span>
              <span
                className={`px-2 py-0.5 rounded font-medium ${
                  activeAnalysis.patch_status === "approved"
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-800/40"
                    : activeAnalysis.patch_status === "rejected"
                    ? "bg-rose-950 text-rose-400 border border-rose-800/40"
                    : activeAnalysis.patch_status === "pending_approval"
                    ? "bg-amber-950 text-amber-400 border border-amber-800/40 animate-pulse"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {activeAnalysis.patch_status ? activeAnalysis.patch_status.replace("_", " ").toUpperCase() : "NONE"}
              </span>
            </div>
          </div>

          {/* Stepper Progress Visualizer */}
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 text-center text-xs font-mono">
            {[
              { key: "load_context", label: "1. Index Repo" },
              { key: "root_cause", label: "2. Root Cause" },
              { key: "generate_test", label: "3. Gen Test" },
              { key: "verify_baseline", label: "4. Base Test" },
              { key: "generate_patch", label: "5. Gen Patch" },
              { key: "verify_docker", label: "6. Docker Run" },
              { key: "compare_regression", label: "7. Verdict" },
            ].map((step) => {
              const matchingEvent = events.find((e) => e.step_name === step.key);
              const isCompleted = matchingEvent?.status === "completed";
              const isRunning = matchingEvent?.status === "running";
              const isFailed = matchingEvent?.status === "failed";
              const isWarning = matchingEvent?.status === "warning";

              return (
                <div
                  key={step.key}
                  className={`p-2 rounded border text-center transition-all ${
                    isCompleted
                      ? "bg-emerald-950/30 border-emerald-800/50 text-emerald-400"
                      : isRunning
                      ? "bg-sky-950/50 border-sky-500 text-sky-300 animate-pulse"
                      : isFailed
                      ? "bg-rose-950/40 border-rose-800 text-rose-400"
                      : isWarning
                      ? "bg-amber-950/40 border-amber-800 text-amber-300"
                      : "bg-slate-950/60 border-slate-800/60 text-slate-600"
                  }`}
                >
                  <div className="font-semibold">{step.label}</div>
                  <div className="text-[10px] uppercase mt-0.5">
                    {matchingEvent ? matchingEvent.status : "pending"}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Detailed Resource Tabs */}
          <div>
            <div className="flex border-b border-slate-800 space-x-1">
              {[
                { id: "events", label: `Workflow Events (${events.length})` },
                { id: "root_cause", label: "Root Cause" },
                { id: "test", label: "Reproduction Test" },
                { id: "patch", label: "Proposed Patch & Review" },
                { id: "evidence", label: "Evidence Report" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as DetailTab)}
                  className={`px-3 py-2 text-xs font-mono font-medium rounded-t transition-colors ${
                    activeTab === tab.id
                      ? "bg-slate-800 text-sky-400 border-t-2 border-sky-500"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab Contents */}
            <div className="pt-4">
              {/* TAB 1: Real-time Event Stream */}
              {activeTab === "events" && (
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {events.length === 0 ? (
                    <div className="text-xs font-mono text-slate-500 p-4 text-center">
                      No events recorded yet. Initializing workflow...
                    </div>
                  ) : (
                    events.map((ev) => (
                      <div
                        key={ev.id}
                        className="p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono flex items-start gap-3"
                      >
                        <span
                          className={`mt-1 w-2 h-2 rounded-full shrink-0 ${
                            ev.status === "completed"
                              ? "bg-emerald-400"
                              : ev.status === "running"
                              ? "bg-sky-400 animate-ping"
                              : ev.status === "failed"
                              ? "bg-rose-500"
                              : ev.status === "warning"
                              ? "bg-amber-400"
                              : "bg-slate-600"
                          }`}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between text-slate-400 text-[10px]">
                            <span className="font-semibold text-slate-300 uppercase">{ev.step_name}</span>
                            <span>{new Date(ev.created_at).toLocaleTimeString()}</span>
                          </div>
                          <div className="text-slate-200 mt-0.5">{ev.message}</div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* TAB 2: Root Cause Analysis */}
              {activeTab === "root_cause" && (
                <div className="space-y-4 text-xs font-mono">
                  {rootCause ? (
                    <>
                      <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-2">
                        <div className="text-slate-400 uppercase text-[10px] font-semibold">Problem Summary</div>
                        <div className="text-slate-100 font-medium text-sm">{rootCause.problem_summary}</div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
                          <div className="text-slate-400 uppercase text-[10px] font-semibold">Suspected Root Cause</div>
                          <div className="text-slate-200">{rootCause.suspected_root_cause}</div>
                        </div>

                        <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
                          <div className="text-slate-400 uppercase text-[10px] font-semibold">Confidence Metric</div>
                          <div className="flex items-center gap-2">
                            <div className="w-full bg-slate-800 rounded-full h-2">
                              <div
                                className="bg-sky-400 h-2 rounded-full"
                                style={{ width: `${Math.round(rootCause.confidence_score * 100)}%` }}
                              />
                            </div>
                            <span className="text-sky-300 font-bold">{Math.round(rootCause.confidence_score * 100)}%</span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1">{rootCause.confidence_explanation}</p>
                        </div>
                      </div>

                      <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-2">
                        <div className="text-slate-400 uppercase text-[10px] font-semibold">Affected Code Files</div>
                        {rootCause.affected_files && rootCause.affected_files.length > 0 ? (
                          <div className="space-y-1.5">
                            {rootCause.affected_files.map((file, idx) => (
                              <div key={idx} className="p-2 bg-slate-900 rounded border border-slate-800 text-[11px]">
                                <span className="text-sky-300 font-semibold">{file.file_path}</span>
                                {file.line_numbers && (
                                  <span className="text-slate-400 ml-2">(Lines: {file.line_numbers.join(", ")})</span>
                                )}
                                {file.reason && <p className="text-slate-400 mt-0.5">{file.reason}</p>}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-slate-500">No specific file records reported.</div>
                        )}
                      </div>

                      <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
                        <div className="text-slate-400 uppercase text-[10px] font-semibold">Correction Strategy</div>
                        <div className="text-slate-200">{rootCause.proposed_correction_strategy}</div>
                      </div>
                    </>
                  ) : (
                    <div className="text-slate-500 p-4 text-center">
                      Root cause analysis not yet available. Awaiting model synthesis...
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: Reproduction Test */}
              {activeTab === "test" && (
                <div className="space-y-4 text-xs font-mono">
                  {reproTest ? (
                    <>
                      <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                        <div>
                          <div className="text-slate-400 text-[10px] uppercase font-semibold">Test Target Path</div>
                          <div className="text-sky-300 font-bold">{reproTest.test_path}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-slate-400 text-[10px] uppercase font-semibold">Baseline Reproduction</div>
                          <span
                            className={`px-2 py-0.5 rounded font-bold ${
                              reproTest.baseline_reproduced
                                ? "bg-emerald-950 text-emerald-400 border border-emerald-700"
                                : "bg-amber-950 text-amber-400 border border-amber-700"
                            }`}
                          >
                            {reproTest.baseline_reproduced ? "CONFIRMED (Test Failed on Baseline)" : "UNCONFIRMED"}
                          </span>
                        </div>
                      </div>

                      <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-2">
                        <div className="text-slate-400 text-[10px] uppercase font-semibold">Generated Pytest Code</div>
                        <pre className="p-3 bg-slate-900 rounded border border-slate-800 text-[11px] text-slate-100 overflow-x-auto leading-relaxed">
                          {reproTest.test_code}
                        </pre>
                      </div>

                      {reproTest.baseline_summary?.stdout && (
                        <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-2">
                          <div className="text-slate-400 text-[10px] uppercase font-semibold">Baseline Execution Output</div>
                          <pre className="p-3 bg-slate-900 rounded border border-slate-800 text-[11px] text-rose-300 overflow-x-auto leading-relaxed">
                            {reproTest.baseline_summary.stdout}
                          </pre>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-slate-500 p-4 text-center">
                      Reproduction test not yet generated.
                    </div>
                  )}
                </div>
              )}

              {/* TAB 4: Proposed Patch & Human Approval Review */}
              {activeTab === "patch" && (
                <div className="space-y-4 text-xs font-mono">
                  {proposedPatch ? (
                    <>
                      {/* Summary & Rationale */}
                      <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
                        <div className="text-slate-400 text-[10px] uppercase font-semibold">Patch Summary</div>
                        <div className="text-slate-100 font-semibold">{proposedPatch.summary || "Unified Diff Patch"}</div>
                        {proposedPatch.rationale && (
                          <div className="text-slate-400 text-[11px] mt-1">{proposedPatch.rationale}</div>
                        )}
                      </div>

                      {/* Unified Diff Viewer */}
                      <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400 text-[10px] uppercase font-semibold">Minimal Unified Diff</span>
                          <span className="text-[11px] text-slate-500">
                            {proposedPatch.affected_files.join(", ")}
                          </span>
                        </div>
                        <div className="bg-slate-900 rounded border border-slate-800 p-3 overflow-x-auto">
                          <pre className="leading-relaxed">
                            {proposedPatch.patch_diff.split("\n").map((line, idx) => {
                              const isAdd = line.startsWith("+") && !line.startsWith("+++");
                              const isDel = line.startsWith("-") && !line.startsWith("---");
                              const isHunk = line.startsWith("@@");
                              const isHeader = line.startsWith("---") || line.startsWith("+++");

                              return (
                                <div
                                  key={idx}
                                  className={
                                    isAdd
                                      ? "text-emerald-400 bg-emerald-950/30"
                                      : isDel
                                      ? "text-rose-400 bg-rose-950/30"
                                      : isHunk
                                      ? "text-sky-400 bg-sky-950/20"
                                      : isHeader
                                      ? "text-slate-400 font-bold"
                                      : "text-slate-300"
                                  }
                                >
                                  {line}
                                </div>
                              );
                            })}
                          </pre>
                        </div>
                      </div>

                      {/* Human Approval Controls (RULE: Require human review before accepting patch) */}
                      <div className="p-4 bg-slate-950/90 rounded border border-sky-800/40 space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                            <span>Human Approval Workflow</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/40">
                              Mandatory Verification Gate
                            </span>
                          </h4>
                          <span className="text-xs text-slate-400">
                            Current Status:{" "}
                            <strong className="text-slate-200 uppercase">
                              {proposedPatch.patch_status.replace("_", " ")}
                            </strong>
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">
                          Automated commits and pushes are forbidden by security policy. Review the unified diff above and record explicit operator approval or rejection.
                        </p>

                        <div className="space-y-2">
                          <input
                            type="text"
                            value={approvalComment}
                            onChange={(e) => setApprovalComment(e.target.value)}
                            placeholder="Operator comment (e.g., Reviewed calculations. Verified fix.)"
                            className="w-full bg-slate-900 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500"
                            disabled={isReviewing}
                          />

                          <div className="flex gap-2 justify-end">
                            <button
                              onClick={() => handleReviewAction("rejected")}
                              disabled={isReviewing}
                              className="px-3 py-1.5 bg-rose-950/80 hover:bg-rose-900 border border-rose-700 text-rose-300 text-xs rounded transition-colors"
                            >
                              Reject Proposed Patch
                            </button>
                            <button
                              onClick={() => handleReviewAction("approved")}
                              disabled={isReviewing}
                              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded transition-colors"
                            >
                              Approve Proposed Patch
                            </button>
                          </div>
                        </div>

                        {reviewMessage && (
                          <div className="text-xs text-sky-300 font-mono mt-2">{reviewMessage}</div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="text-slate-500 p-4 text-center">
                      Proposed patch not yet generated.
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: Evidence Report */}
              {activeTab === "evidence" && (
                <div className="space-y-4 text-xs font-mono">
                  {evidenceReport ? (
                    <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400 text-[10px] uppercase font-semibold">
                          Immutable Evidence Report JSON
                        </span>
                        <span className="text-emerald-400 font-bold">Tamper-Proof Artifact</span>
                      </div>
                      <pre className="p-3 bg-slate-900 rounded border border-slate-800 text-[11px] text-slate-200 overflow-x-auto max-h-96 leading-relaxed">
                        {JSON.stringify(evidenceReport, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <div className="text-slate-500 p-4 text-center">
                      Final evidence report not yet compiled.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
