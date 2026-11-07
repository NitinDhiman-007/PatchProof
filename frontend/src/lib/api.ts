import {
  BugAnalysisRequest,
  BugAnalysisResponse,
  DockerStatusResponse,
  GitUrlRegistrationRequest,
  HealthResponse,
  ModelStatusResponse,
  PatchApprovalResponse,
  ProposedPatchResponse,
  ReproductionTestResponse,
  Repository,
  RootCauseResponse,
  SystemStatusResponse,
  VerificationLogsResponse,
  VerificationReportResponse,
  VerificationRunRequest,
  VerificationRunResponse,
  WorkflowEventResponse,
  ZipValidationResponse,
} from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

class ApiClientError extends Error {
  public status?: number;
  public detail?: string;

  constructor(message: string, status?: number, detail?: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.detail = detail;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = "An unexpected error occurred.";
    try {
      const errJson = await res.json();
      detail = errJson.detail || errJson.error || JSON.stringify(errJson);
    } catch {
      detail = await res.text().catch(() => res.statusText);
    }
    throw new ApiClientError(detail, res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getBaseUrl(): string {
    return API_BASE_URL;
  },

  async getHealth(): Promise<HealthResponse> {
    const res = await fetch(`${API_BASE_URL}/health`, {
      cache: "no-store",
    });
    return handleResponse<HealthResponse>(res);
  },

  async getSystemStatus(): Promise<SystemStatusResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/status`, {
      cache: "no-store",
    });
    return handleResponse<SystemStatusResponse>(res);
  },

  async registerGitUrl(
    payload: GitUrlRegistrationRequest
  ): Promise<Repository> {
    const res = await fetch(`${API_BASE_URL}/api/v1/repositories/register-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    return handleResponse<Repository>(res);
  },

  async uploadZipArchive(file: File): Promise<ZipValidationResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE_URL}/api/v1/repositories/upload-zip`, {
      method: "POST",
      body: formData,
    });
    return handleResponse<ZipValidationResponse>(res);
  },

  async listRepositories(): Promise<Repository[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/repositories`, {
      cache: "no-store",
    });
    return handleResponse<Repository[]>(res);
  },

  async startBugAnalysis(
    payload: BugAnalysisRequest
  ): Promise<BugAnalysisResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    return handleResponse<BugAnalysisResponse>(res);
  },

  async listAnalysisRuns(): Promise<BugAnalysisResponse[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis`, {
      cache: "no-store",
    });
    return handleResponse<BugAnalysisResponse[]>(res);
  },

  async getAnalysisStatus(analysisId: string): Promise<BugAnalysisResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}`, {
      cache: "no-store",
    });
    return handleResponse<BugAnalysisResponse>(res);
  },

  async getModelStatus(): Promise<ModelStatusResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/model/status`, {
      cache: "no-store",
    });
    return handleResponse<ModelStatusResponse>(res);
  },

  async getAnalysisEvents(analysisId: string): Promise<WorkflowEventResponse[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}/events`, {
      cache: "no-store",
    });
    return handleResponse<WorkflowEventResponse[]>(res);
  },

  async getRootCause(analysisId: string): Promise<RootCauseResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}/root-cause`, {
      cache: "no-store",
    });
    return handleResponse<RootCauseResponse>(res);
  },

  async getReproductionTest(analysisId: string): Promise<ReproductionTestResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}/test`, {
      cache: "no-store",
    });
    return handleResponse<ReproductionTestResponse>(res);
  },

  async getProposedPatch(analysisId: string): Promise<ProposedPatchResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}/patch`, {
      cache: "no-store",
    });
    return handleResponse<ProposedPatchResponse>(res);
  },

  async approvePatch(
    analysisId: string,
    status: "approved" | "rejected",
    comment?: string
  ): Promise<PatchApprovalResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}/patch/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status, comment }),
    });
    return handleResponse<PatchApprovalResponse>(res);
  },

  async getEvidenceReport(analysisId: string): Promise<Record<string, unknown>> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analysis/${analysisId}/evidence`, {
      cache: "no-store",
    });
    return handleResponse<Record<string, unknown>>(res);
  },

  async startVerification(
    payload: VerificationRunRequest
  ): Promise<VerificationReportResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/verification/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    return handleResponse<VerificationReportResponse>(res);
  },

  async getVerificationStatus(
    runId: string
  ): Promise<VerificationRunResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/verification/${runId}`, {
      cache: "no-store",
    });
    return handleResponse<VerificationRunResponse>(res);
  },

  async getVerificationLogs(
    runId: string
  ): Promise<VerificationLogsResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/verification/${runId}/logs`, {
      cache: "no-store",
    });
    return handleResponse<VerificationLogsResponse>(res);
  },

  async getVerificationReport(
    runId: string
  ): Promise<VerificationReportResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/verification/${runId}/report`, {
      cache: "no-store",
    });
    return handleResponse<VerificationReportResponse>(res);
  },

  async listVerifications(): Promise<VerificationRunResponse[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/verification`, {
      cache: "no-store",
    });
    return handleResponse<VerificationRunResponse[]>(res);
  },

  async getDockerStatus(): Promise<DockerStatusResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/verification/docker/status`, {
      cache: "no-store",
    });
    return handleResponse<DockerStatusResponse>(res);
  },
};

export { ApiClientError };

