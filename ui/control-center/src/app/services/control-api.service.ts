import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface ControlApiResponse<T> {
  status: string;
  data: T;
  error?: { code: string; message: string };
  request_id?: string;
}

export interface RunSummaryView {
  run_id: string;
  plan_id: string;
  status: string;
  source_root: string;
  staging_root?: string;
  created_at: string;
  updated_at: string;
  has_recovery_required: boolean;
  terminal_state?: string;
}

export interface RunDetailView {
  run_id: string;
  plan_id: string;
  status: string;
  source_root: string;
  staging_root?: string;
  current_step_id?: string;
  created_at: string;
  updated_at: string;
  terminal_state?: string;
  terminal_reason?: string;
  affected_files: string[];
  recovery_actions: string[];
  checkpoints: Array<{ checkpoint_id: string; type: string; timestamp: string; state_data: any }>;
}

export interface DiffReviewView {
  run_id: string;
  changeset_id?: string;
  changeset_digest?: string;
  files: Array<{
    path: string;
    change_type: string;
    old_content?: string;
    new_content?: string;
    patch: string;
    is_safe: boolean;
    additions: number;
    deletions: number;
  }>;
  total_files: number;
  total_additions: number;
  total_deletions: number;
  is_clean: boolean;
}

export interface PlanView {
  plan_id: string;
  status: string;
  plan_digest: string;
  steps: Array<{
    step_id: string;
    title: string;
    description: string;
    scope: string;
    risk: string;
    dependencies: string[];
    expected_files: string[];
    confidence: number;
  }>;
  is_approved: boolean;
  approval_signature?: any;
}

export interface GraphView {
  nodes: any[];
  edges: any[];
  mermaid_source: string;
  domains: string[];
}

@Injectable({
  providedIn: 'root',
})
export class ControlApiService {
  private readonly http = inject(HttpClient);
  readonly sessionToken = signal<string>('');

  setSessionToken(token: string): void {
    this.sessionToken.set(token);
  }

  private getHeaders(): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });
    const token = this.sessionToken();
    if (token) {
      headers = headers.set('X-Session-Token', token).set('X-CSRF-Token', token);
    }
    return headers;
  }

  getHealth(): Observable<any> {
    return this.http
      .get<ControlApiResponse<any>>('/api/v1/health', { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }

  listRuns(): Observable<RunSummaryView[]> {
    return this.http
      .get<ControlApiResponse<RunSummaryView[]>>('/api/v1/runs', { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }

  getRun(runId: string): Observable<RunDetailView> {
    return this.http
      .get<ControlApiResponse<RunDetailView>>(`/api/v1/runs/${runId}`, { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }

  getDiff(runId: string): Observable<DiffReviewView> {
    return this.http
      .get<ControlApiResponse<DiffReviewView>>(`/api/v1/runs/${runId}/diff`, { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }

  getPlan(planId: string): Observable<PlanView> {
    return this.http
      .get<ControlApiResponse<PlanView>>(`/api/v1/plans/${planId}`, { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }

  approvePlan(planId: string, actor: string, notes: string): Observable<PlanView> {
    const payload = {
      actor,
      notes,
      request_id: `req-${Date.now()}`,
    };
    return this.http
      .post<ControlApiResponse<PlanView>>(`/api/v1/plans/${planId}/approve`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map((res) => res.data));
  }

  applyRun(runId: string, actor: string): Observable<RunDetailView> {
    const payload = {
      actor,
      request_id: `req-${Date.now()}`,
    };
    return this.http
      .post<ControlApiResponse<RunDetailView>>(`/api/v1/runs/${runId}/apply`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map((res) => res.data));
  }

  getGraph(): Observable<GraphView> {
    return this.http
      .get<ControlApiResponse<GraphView>>('/api/v1/graph', { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }

  getLearnings(): Observable<any> {
    return this.http
      .get<ControlApiResponse<any>>('/api/v1/learnings', { headers: this.getHeaders() })
      .pipe(map((res) => res.data));
  }
}
