/**
 * API client functions for interacting with the backend.
 *
 * Each function returns a promise that resolves with the JSON data
 * from the corresponding endpoint.  Errors are propagated as
 * rejected promises.
 */

// Represents a single scene object streamed from the server
export interface SceneData {
  [key: string]: any;
}

export interface UploadInitiatedResponse {
  id: number;
  status: string;
}

export interface UploadInfo {
  id: number;
  filename: string;
  created_at: string;
  status: string;
}

export interface UploadDetail {
  id: number;
  filename: string;
  created_at: string;
  status: string;
  data?: Record<string, Record<string, SceneData[]>>;
  download_url?: string;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Network error or invalid JSON response' }));
    throw new Error(errorData.detail || 'An unknown error occurred');
  }
  return (await response.json()) as T;
}

export async function initiateUpload(file: File): Promise<UploadInitiatedResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/initiate-upload', {
    method: 'POST',
    body: formData,
  });
  return handleResponse<UploadInitiatedResponse>(res);
}

export async function getHistory(): Promise<UploadInfo[]> {
  const res = await fetch('/history');
  return handleResponse<UploadInfo[]>(res);
}

export async function getResult(id: number): Promise<UploadDetail> {
  const res = await fetch(`/result/${id}`);
  return handleResponse<UploadDetail>(res);
}

export function getDownloadUrl(id: number): string {
  return `/download/${id}`;
}