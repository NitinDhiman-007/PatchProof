"use client";

import React, { useState } from "react";
import { api, ApiClientError } from "@/lib/api";
import { Repository } from "@/types/api";

interface RepositoryConnectProps {
  onRepositoryConnected: (repo: Repository) => void;
}

export function RepositoryConnect({
  onRepositoryConnected,
}: RepositoryConnectProps) {
  const [tab, setTab] = useState<"git" | "zip">("git");

  // Git state
  const [gitUrl, setGitUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [isSubmittingGit, setIsSubmittingGit] = useState(false);
  const [gitError, setGitError] = useState<string | null>(null);

  // ZIP state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploadingZip, setIsUploadingZip] = useState(false);
  const [zipError, setZipError] = useState<string | null>(null);
  const [zipSuccessMessage, setZipSuccessMessage] = useState<string | null>(null);

  // Handle Git submission
  const handleGitSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGitError(null);

    const clean = gitUrl.trim();
    if (!clean) {
      setGitError("Please enter a valid Git repository URL.");
      return;
    }

    // Client-side guard against command injection
    if (/[;&|`<>\n\r]/.test(clean) || clean.startsWith("-")) {
      setGitError("Invalid characters detected in Git URL.");
      return;
    }

    setIsSubmittingGit(true);
    try {
      const repo = await api.registerGitUrl({
        git_url: clean,
        default_branch: branch.trim() || "main",
      });
      setGitUrl("");
      onRepositoryConnected(repo);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setGitError(err.detail || err.message);
      } else {
        setGitError("Failed to connect repository. Verify backend is running.");
      }
    } finally {
      setIsSubmittingGit(false);
    }
  };

  // Handle ZIP submission
  const handleZipSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setZipError(null);
    setZipSuccessMessage(null);

    if (!selectedFile) {
      setZipError("Please select a .zip archive to upload.");
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".zip")) {
      setZipError("Only files ending in .zip are accepted.");
      return;
    }

    setIsUploadingZip(true);
    try {
      const res = await api.uploadZipArchive(selectedFile);
      if (!res.is_valid || !res.repository) {
        const errorList = res.errors?.length ? res.errors.join(", ") : res.message;
        setZipError(errorList || "ZIP verification failed.");
      } else {
        setZipSuccessMessage(
          `Verified safely (${res.total_files} files, ${res.detected_language} detected). Registered!`
        );
        setSelectedFile(null);
        onRepositoryConnected(res.repository);
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setZipError(err.detail || err.message);
      } else {
        setZipError("Failed to upload ZIP. Ensure backend is operational.");
      }
    } finally {
      setIsUploadingZip(false);
    }
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <span>Repository Connection</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/40">
              Safe Inspection
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Connect an untrusted codebase for bug isolation. Code is never executed directly on host.
          </p>
        </div>

        {/* Tab Selector */}
        <div className="flex bg-slate-950 p-1 rounded-md border border-slate-800">
          <button
            type="button"
            onClick={() => {
              setTab("git");
              setGitError(null);
            }}
            className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
              tab === "git"
                ? "bg-slate-800 text-sky-400 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            GitHub / Git URL
          </button>
          <button
            type="button"
            onClick={() => {
              setTab("zip");
              setZipError(null);
            }}
            className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
              tab === "zip"
                ? "bg-slate-800 text-sky-400 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            ZIP Upload
          </button>
        </div>
      </div>

      {tab === "git" ? (
        <form onSubmit={handleGitSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div className="md:col-span-3">
              <label className="block text-xs font-mono text-slate-400 mb-1">
                GitHub Repository URL
              </label>
              <input
                type="text"
                value={gitUrl}
                onChange={(e) => setGitUrl(e.target.value)}
                placeholder="https://github.com/psf/requests"
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 transition-colors"
                disabled={isSubmittingGit}
              />
            </div>
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">
                Branch
              </label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 transition-colors"
                disabled={isSubmittingGit}
              />
            </div>
          </div>

          {gitError && (
            <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-800/60 rounded px-3 py-2 font-mono flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              <span>{gitError}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmittingGit || !gitUrl.trim()}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors flex items-center gap-2"
            >
              {isSubmittingGit ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Validating & Registering...</span>
                </>
              ) : (
                <span>Register Repository</span>
              )}
            </button>
          </div>
        </form>
      ) : (
        <form onSubmit={handleZipSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-slate-400 mb-1">
              Select Codebase ZIP Archive (Max 50MB)
            </label>
            <div className="border border-dashed border-slate-800 hover:border-slate-700 rounded-lg p-6 bg-slate-950/50 flex flex-col items-center justify-center text-center cursor-pointer relative transition-colors">
              <input
                type="file"
                accept=".zip,application/zip"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null;
                  setSelectedFile(file);
                  setZipError(null);
                  setZipSuccessMessage(null);
                }}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                disabled={isUploadingZip}
              />
              <svg className="w-8 h-8 text-slate-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              {selectedFile ? (
                <div>
                  <div className="text-xs font-mono text-sky-400 font-semibold">{selectedFile.name}</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for in-memory safety inspection
                  </div>
                </div>
              ) : (
                <div>
                  <div className="text-xs text-slate-300 font-medium">Click or drag ZIP archive to upload</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Analyzed for zip bombs and path traversal without unpacking on host.
                  </div>
                </div>
              )}
            </div>
          </div>

          {zipError && (
            <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-800/60 rounded px-3 py-2 font-mono flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              <span>{zipError}</span>
            </div>
          )}

          {zipSuccessMessage && (
            <div className="text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-800/60 rounded px-3 py-2 font-mono flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span>{zipSuccessMessage}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isUploadingZip || !selectedFile}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors flex items-center gap-2"
            >
              {isUploadingZip ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Inspecting Archive Safely...</span>
                </>
              ) : (
                <span>Upload & Verify Archive</span>
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

