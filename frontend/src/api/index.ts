/**
 * API client functions for interacting with the backend.
 *
 * Each function returns a promise that resolves with the JSON data
 * from the corresponding endpoint.  Errors are propagated as
 * rejected promises.
 */
export interface UploadResponse {
  id: number;
  data: Array<Record<string, any>>;
}

export interface UploadInfo {
  id: number;
  filename: string;
  created_at: string;
}

export interface UploadDetail {
  id: number;
  filename: string;
  created_at: string;
  data: Array<Record<string, any>>;
  download_url: string;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'Network error');
  }
  return (await response.json()) as T;
}

export async function uploadScript(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/upload', {
    method: 'POST',
    body: formData,
  });
  return handleResponse<UploadResponse>(res);
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