"use client";

import React, { useCallback, useEffect, useState } from "react";
import { BugAnalysisPanel } from "@/components/BugAnalysisPanel";
import { Header } from "@/components/Header";
import { RecentAnalysisList } from "@/components/RecentAnalysisList";
import { RepositoriesList } from "@/components/RepositoriesList";
import { RepositoryConnect } from "@/components/RepositoryConnect";
import { NavTab, Sidebar } from "@/components/Sidebar";
import { VerificationCards } from "@/components/VerificationCards";
import { VerificationPanel } from "@/components/VerificationPanel";
import { api, ApiClientError } from "@/lib/api";
import {
  BugAnalysisResponse,
  DockerStatusResponse,
  Repository,
  SystemStatusResponse,
  VerificationRunResponse,
} from "@/types/api";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<NavTab>("overview");
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [analyses, setAnalyses] = useState<BugAnalysisResponse[]>([]);
  const [verificationRuns, setVerificationRuns] = useState<VerificationRunResponse[]>([]);
  const [dockerStatus, setDockerStatus] = useState<DockerStatusResponse | null>(null);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [apiError, setApiError] = useState<string | null>(null);

  // Fetch all state from FastAPI backend
  const loadDashboardData = useCallback(async () => {
    setIsLoading(true);
    setApiError(null);

    try {
      // 1. Fetch system operational status
      const statusRes = await api.getSystemStatus().catch((err) => {
        throw err;
      });
      setSystemStatus(statusRes);

      // 2. Fetch registered repositories
      const reposRes = await api.listRepositories().catch(() => []);
      setRepositories(reposRes);

      // 3. Fetch recent bug analyses
      const analysisRes = await api.listAnalysisRuns().catch(() => []);
      setAnalyses(analysisRes);

      // 4. Fetch verification run history & Docker engine status
      const [runsRes, docRes] = await Promise.all([
        api.listVerifications().catch(() => []),
        api.getDockerStatus().catch(() => null),
      ]);
      setVerificationRuns(runsRes);
      setDockerStatus(docRes);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setApiError(`Backend Connection Error: ${err.detail || err.message}`);
      } else {
        setApiError(
          `Unable to reach backend at ${api.getBaseUrl()}. Ensure the FastAPI server is running.`
        );
      }
      setSystemStatus(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    async function init() {
      try {
        const [statusRes, reposRes, analysisRes, runsRes, docRes] = await Promise.all([
          api.getSystemStatus().catch(() => null),
          api.listRepositories().catch(() => []),
          api.listAnalysisRuns().catch(() => []),
          api.listVerifications().catch(() => []),
          api.getDockerStatus().catch(() => null),
        ]);
        if (!ignore) {
          setSystemStatus(statusRes);
          setRepositories(reposRes);
          setAnalyses(analysisRes);
          setVerificationRuns(runsRes);
          setDockerStatus(docRes);
          if (!statusRes) {
            setApiError(
              `Unable to reach backend at ${api.getBaseUrl()}. Ensure the FastAPI server is running.`
            );
          }
        }
      } catch {
        if (!ignore) {
          setApiError(
            `Unable to reach backend at ${api.getBaseUrl()}. Ensure the FastAPI server is running.`
          );
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    init();
    return () => {
      ignore = true;
    };
  }, []);

  const handleRepositoryConnected = (newRepo: Repository) => {
    setRepositories((prev) => [newRepo, ...prev]);
    // Refresh status to update repo counts
    api.getSystemStatus().then(setSystemStatus).catch(() => null);
  };

  const handleAnalysisStarted = (newRun: BugAnalysisResponse) => {
    setAnalyses((prev) => [newRun, ...prev]);
    setSelectedAnalysisId(newRun.id);
  };

  const handleVerificationCompleted = () => {
    api.listVerifications().then(setVerificationRuns).catch(() => null);
  };

  const sidebarStatus = isLoading
    ? "loading"
    : systemStatus?.status === "operational"
    ? "operational"
    : systemStatus?.status === "degraded"
    ? "degraded"
    : "offline";

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        systemStatus={sidebarStatus}
        version={systemStatus?.version || "0.1.0"}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <Header
          systemStatus={systemStatus}
          isLoading={isLoading}
          onRefresh={loadDashboardData}
        />

        {/* Global Connection Warning */}
        {apiError && (
          <div className="bg-rose-950/80 border-b border-rose-800/80 px-8 py-2.5 flex items-center justify-between text-xs font-mono text-rose-300">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
              <span>{apiError}</span>
            </div>
            <button
              onClick={loadDashboardData}
              className="px-2.5 py-1 bg-rose-900/60 hover:bg-rose-800 border border-rose-700/60 rounded text-[11px] text-white transition-colors"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Dynamic View Body */}
        <main className="flex-1 overflow-y-auto p-8 space-y-6">
          {/* OVERVIEW TAB */}
          {activeTab === "overview" && (
            <>
              {/* Metric Verification Cards */}
              <VerificationCards
                systemStatus={systemStatus}
                repositoriesCount={repositories.length}
                analysesCount={analyses.length}
                verificationRunsCount={verificationRuns.length}
                dockerAvailable={dockerStatus?.docker_available}
              />

              {/* Main Action Grids */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <RepositoryConnect
                  onRepositoryConnected={handleRepositoryConnected}
                />
                <BugAnalysisPanel
                  repositories={repositories}
                  onAnalysisStarted={handleAnalysisStarted}
                  selectedAnalysisId={selectedAnalysisId}
                />
              </div>

              {/* Repositories and Analyses Tables */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <RepositoriesList repositories={repositories} />
                <RecentAnalysisList
                  analyses={analyses}
                  repositories={repositories}
                  selectedAnalysisId={selectedAnalysisId}
                  onSelectAnalysis={setSelectedAnalysisId}
                />
              </div>
            </>
          )}

          {/* REPOSITORIES TAB */}
          {activeTab === "repositories" && (
            <div className="space-y-6">
              <RepositoryConnect
                onRepositoryConnected={handleRepositoryConnected}
              />
              <RepositoriesList repositories={repositories} />
            </div>
          )}

          {/* BUG ANALYSIS TAB */}
          {activeTab === "analysis" && (
            <div className="space-y-6">
              <BugAnalysisPanel
                repositories={repositories}
                onAnalysisStarted={handleAnalysisStarted}
                selectedAnalysisId={selectedAnalysisId}
              />
              <RecentAnalysisList
                analyses={analyses}
                repositories={repositories}
                selectedAnalysisId={selectedAnalysisId}
                onSelectAnalysis={setSelectedAnalysisId}
              />
            </div>
          )}

          {/* VERIFICATION REPORTS TAB */}
          {activeTab === "reports" && (
            <VerificationPanel
              repositories={repositories}
              verificationRuns={verificationRuns}
              dockerStatus={dockerStatus}
              onRunCompleted={handleVerificationCompleted}
            />
          )}

          {/* SETTINGS TAB */}
          {activeTab === "settings" && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-6 space-y-5">
              <div>
                <h2 className="text-sm font-semibold text-slate-100">Environment & System Settings</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Runtime parameters and security thresholds configured via environment variables.
                </p>
              </div>

              <div className="space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-400">NEXT_PUBLIC_API_BASE_URL</span>
                  <span className="text-sky-400">{api.getBaseUrl()}</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-400">FastAPI Environment</span>
                  <span className="text-slate-200">{systemStatus?.environment || "development"}</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-400">Database Engine</span>
                  <span className="text-slate-200">SQLite (Thread-safe connection pool)</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-400">BharatCode AI Credentials</span>
                  <span className={systemStatus?.bharatcode_configured ? "text-emerald-400" : "text-amber-400"}>
                    {systemStatus?.bharatcode_configured ? "Configured in backend" : "Not Set (Standby)"}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-400">Max ZIP Upload Size</span>
                  <span className="text-slate-200">50 MB</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-400">Host Code Execution</span>
                  <span className="text-emerald-400">DISABLED (Strict Non-Execution Policy)</span>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
