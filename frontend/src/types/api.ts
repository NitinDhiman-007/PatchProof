/**
 * TypeScript API contracts matching PatchProof FastAPI schemas.
 */

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}

export interface SystemStatusResponse {
  status: "operational" | "degraded" | string;
  version: string;
  environment: string;
  database: "connected" | "disconnected" | string;
  bharatcode_configured: boolean;
  repositories_count: number;
  timestamp: string;
}

export interface Repository {
  id: string;
  name: string;
  source_type: "git" | "zip";
  git_url?: string | null;
  default_branch?: string | null;
  file_count: number;
  detected_language: string;
  status: string;
  created_at: string;
}

export interface GitUrlRegistrationRequest {
  git_url: string;
  default_branch?: string;
}

export interface ZipValidationResponse {
  is_valid: boolean;
  message: string;
  repository?: Repository | null;
  filename: string;
  file_size_bytes: number;
  total_files: number;
  top_level_directories: string[];
  detected_language: string;
  errors: string[];
}

export interface BugAnalysisRequest {
  repository_id: string;
  bug_description: string;
  issue_url?: string;
  stack_trace?: string;
}

export interface BugAnalysisResponse {
  id: string;
  repository_id: string;
  bug_description: string;
  issue_url?: string | null;
  stack_trace?: string | null;
  status: "pending" | "analyzing" | "completed" | "failed";
  summary?: string | null;
  root_cause_json?: string | null;
  reproduction_test_code?: string | null;
  reproduction_test_path?: string | null;
  baseline_reproduced?: boolean;
  patch_diff?: string | null;
  patch_status?: "none" | "pending_approval" | "approved" | "rejected";
  verification_verdict?: "PENDING" | "VERIFIED" | "FAILED" | "INCONCLUSIVE" | "ERROR";
  evidence_report_json?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowEventResponse {
  id: string;
  analysis_id: string;
  step_name: string;
  status: "running" | "completed" | "failed" | "warning" | string;
  message: string;
  details_json?: string | null;
  created_at: string;
}

export interface RootCauseResponse {
  analysis_id: string;
  problem_summary: string;
  suspected_root_cause: string;
  affected_files: Array<{
    file_path: string;
    line_numbers?: number[];
    reason?: string;
  }>;
  explanation: string;
  confidence_score: number;
  confidence_explanation: string;
  proposed_correction_strategy: string;
}

export interface ReproductionTestResponse {
  analysis_id: string;
  test_path: string;
  test_code: string;
  baseline_reproduced: boolean;
  baseline_summary?: {
    status?: string;
    exit_code?: number | null;
    tests_failed?: number;
    tests_passed?: number;
    duration_seconds?: number;
    stdout?: string;
    stderr?: string;
  } | null;
}

export interface ProposedPatchResponse {
  analysis_id: string;
  patch_diff: string;
  patch_status: "none" | "pending_approval" | "approved" | "rejected";
  summary?: string | null;
  rationale?: string | null;
  affected_files: string[];
  is_valid: boolean;
  validation_error?: string | null;
}

export interface PatchApprovalResponse {
  analysis_id: string;
  patch_status: "approved" | "rejected";
  message: string;
  updated_at: string;
}

export interface ModelStatusResponse {
  configured: boolean;
  reachable: boolean;
  model: string;
  base_url: string;
  message: string;
  response_sample?: string | null;
}

export interface ApiError {
  error: string;
  detail: string;
  timestamp?: string;
}

export interface VerificationRunRequest {
  repository_id: string;
  command?: string;
  run_ruff?: boolean;
}

export interface VerificationRunResponse {
  id: string;
  repository_id: string;
  repository_name?: string | null;
  command: string;
  status: "pending" | "running" | "passed" | "failed" | "timed_out" | "error";
  exit_code?: number | null;
  duration_seconds: number;
  tests_passed: number;
  tests_failed: number;
  tests_skipped: number;
  tests_errors: number;
  ruff_passed: boolean;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface VerificationLogsResponse {
  run_id: string;
  status: string;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  error_message?: string | null;
}

export interface VerificationReportResponse {
  run_id: string;
  repository_id: string;
  repository_name: string;
  status: "passed" | "failed" | "timed_out" | "error";
  execution_environment: string;
  command: string;
  exit_code?: number | null;
  duration_seconds: number;
  tests_passed: number;
  tests_failed: number;
  tests_skipped: number;
  tests_errors: number;
  ruff_passed: boolean;
  ruff_issues: string[];
  ruff_exit_code?: number | null;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  infrastructure_error?: string | null;
  verification_summary: string;
  created_at: string;
  completed_at?: string | null;
}

export interface DockerStatusResponse {
  docker_available: boolean;
  detail: string;
}

