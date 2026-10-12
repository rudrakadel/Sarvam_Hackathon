/**
 * VeriDictum AI — Axios API Client
 * Centralised HTTP client with JWT auth, auto-refresh, and error handling.
 */

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/authStore";

const BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// ─── Request interceptor: attach JWT ────────────────────────────────────────
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ─── Response interceptor: auto-refresh expired tokens ──────────────────────
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
}> = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token);
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = useAuthStore.getState().refreshToken;
      if (!refreshToken) {
        useAuthStore.getState().logout();
        return Promise.reject(error);
      }

      try {
        const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
        processQueue(null, data.access_token);
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as Error, null);
        useAuthStore.getState().logout();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ─── Typed API methods ────────────────────────────────────────────────────────
export const authApi = {
  register: (data: object) => apiClient.post("/auth/register", data),
  login: (data: object) => apiClient.post("/auth/login", data),
  logout: (refreshToken: string) => apiClient.post("/auth/logout", { refresh_token: refreshToken }),
  verifyEmail: (token: string) => apiClient.post("/auth/verify-email", { token }),
  forgotPassword: (email: string) => apiClient.post("/auth/forgot-password", { email }),
  resetPassword: (token: string, newPassword: string) =>
    apiClient.post("/auth/reset-password", { token, new_password: newPassword }),
  setupMFA: () => apiClient.post("/auth/mfa/setup"),
  confirmMFA: (code: string) => apiClient.post("/auth/mfa/confirm", { totp_code: code }),
  // Backend requires a fresh TOTP code to disable MFA (defence against
  // an attacker who hijacks a session and tries to drop the second factor).
  // Axios DELETE supports a request body via the `data` option.
  disableMFA: (totpCode: string) =>
    apiClient.delete("/auth/mfa/disable", { data: { totp_code: totpCode } }),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiClient.post("/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  me: () => apiClient.get("/users/me"),
  updateProfile: (userId: string, data: object) => apiClient.patch(`/users/${userId}`, data),
  listSessions: () => apiClient.get("/auth/sessions"),
  revokeSession: (tokenId: string) => apiClient.delete(`/auth/sessions/${tokenId}`),
};

export const casesApi = {
  list: (params?: object) => apiClient.get("/cases", { params }),
  create: (data: object) => apiClient.post("/cases", data),
  get: (id: string) => apiClient.get(`/cases/${id}`),
  update: (id: string, data: object) => apiClient.patch(`/cases/${id}`, data),
  archive: (id: string) => apiClient.post(`/cases/${id}/archive`),
  listMembers: (id: string) => apiClient.get(`/cases/${id}/members`),
  addMember: (id: string, data: object) => apiClient.post(`/cases/${id}/members`, data),
  updateMember: (caseId: string, userId: string, data: object) =>
    apiClient.patch(`/cases/${caseId}/members/${userId}`, data),
  removeMember: (caseId: string, userId: string) =>
    apiClient.delete(`/cases/${caseId}/members/${userId}`),
  getAuditLog: (id: string, params?: object) => apiClient.get(`/cases/${id}/audit-log`, { params }),
};

export const audioApi = {
  upload: (caseId: string, formData: FormData) =>
    apiClient.post(`/cases/${caseId}/audio`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  list: (caseId: string) => apiClient.get(`/cases/${caseId}/audio`),
  get: (caseId: string, audioId: string) => apiClient.get(`/cases/${caseId}/audio/${audioId}`),
  retranscribe: (caseId: string, audioId: string, params?: object) =>
    apiClient.post(`/cases/${caseId}/audio/${audioId}/retranscribe`, null, { params }),
  listTranscripts: (caseId: string, audioId: string) =>
    apiClient.get(`/cases/${caseId}/audio/${audioId}/transcripts`),
  getSegments: (caseId: string, audioId: string, transcriptId: string) =>
    apiClient.get(`/cases/${caseId}/audio/${audioId}/transcripts/${transcriptId}/segments`),
  editSegment: (caseId: string, audioId: string, transcriptId: string, segmentId: string, text: string) =>
    apiClient.patch(
      `/cases/${caseId}/audio/${audioId}/transcripts/${transcriptId}/segments/${segmentId}`,
      { text }
    ),
  setSpeakerLabels: (caseId: string, audioId: string, transcriptId: string, mappings: Record<string, string>) =>
    apiClient.post(
      `/cases/${caseId}/audio/${audioId}/transcripts/${transcriptId}/speaker-labels`,
      { mappings }
    ),
  summarizeTranscript: (caseId: string, audioId: string, transcriptId: string) =>
    apiClient.post(`/cases/${caseId}/audio/${audioId}/transcripts/${transcriptId}/summarize`),
};

export const documentsApi = {
  upload: (caseId: string, formData: FormData) =>
    apiClient.post(`/cases/${caseId}/documents`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  list: (caseId: string) => apiClient.get(`/cases/${caseId}/documents`),
  get: (caseId: string, docId: string) => apiClient.get(`/cases/${caseId}/documents/${docId}`),
  getPages: (caseId: string, docId: string) => apiClient.get(`/cases/${caseId}/documents/${docId}/pages`),
  correctPage: (caseId: string, docId: string, page: number, text: string) =>
    apiClient.patch(`/cases/${caseId}/documents/${docId}/pages/${page}/correct`, { text }),
  delete: (caseId: string, docId: string) => apiClient.delete(`/cases/${caseId}/documents/${docId}`),
};

export const contradictionsApi = {
  analyze: (caseId: string) => apiClient.post(`/cases/${caseId}/contradictions/analyze`),
  listJobs: (caseId: string) => apiClient.get(`/cases/${caseId}/contradictions/jobs`),
  list: (caseId: string, params?: object) => apiClient.get(`/cases/${caseId}/contradictions`, { params }),
  get: (caseId: string, id: string) => apiClient.get(`/cases/${caseId}/contradictions/${id}`),
  review: (caseId: string, id: string, data: object) =>
    apiClient.patch(`/cases/${caseId}/contradictions/${id}/review`, data),
  stats: (caseId: string) => apiClient.get(`/cases/${caseId}/contradictions/summary/stats`),
};

export const queryApi = {
  ask: (caseId: string, query: string) => apiClient.post(`/cases/${caseId}/query`, { query }),
  history: (caseId: string, params?: object) => apiClient.get(`/cases/${caseId}/query/history`, { params }),
};

export const reportsApi = {
  create: (caseId: string, data: object) => apiClient.post(`/cases/${caseId}/reports`, data),
  list: (caseId: string, params?: object) => apiClient.get(`/cases/${caseId}/reports`, { params }),
  get: (caseId: string, id: string) => apiClient.get(`/cases/${caseId}/reports/${id}`),
};

// ─── Phase D — Courtroom Audit (voice + cross-validation + PDF brief) ──────
export const courtroomApi = {
  audit: (caseId: string) => apiClient.post(`/cases/${caseId}/courtroom-audit`),
  brief: (caseId: string) =>
    apiClient.get(`/cases/${caseId}/courtroom-brief.pdf`, { responseType: "blob" }),
  // Phase E — list persisted voice transcripts for the case
  voiceRecords: (caseId: string) =>
    apiClient.get(`/cases/${caseId}/voice-records`),
};

export const dashboardApi = {
  get: () => apiClient.get("/dashboard"),
};

export const notificationsApi = {
  list: (params?: object) => apiClient.get("/notifications", { params }),
  unreadCount: () => apiClient.get("/notifications/unread-count"),
  markRead: (id: string) => apiClient.patch(`/notifications/${id}/read`),
  markAllRead: () => apiClient.patch("/notifications/read-all"),
  delete: (id: string) => apiClient.delete(`/notifications/${id}`),
};
