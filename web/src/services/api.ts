const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getToken(): string | null {
  try {
    const stored = localStorage.getItem('auth-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed.state?.token ?? null;
    }
  } catch {
    // ignore
  }
  return null;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || body.detail || `Request failed: ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

// Auth
export const authApi = {
  login: async (username: string, password: string) => {
    // Login uses OAuth2 form data, not JSON
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);

    const res = await fetch(`${BASE_URL}/api/auth/login`, {
      method: 'POST',
      body: params,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `Login failed: ${res.status}`);
    }

    const data = await res.json() as { access_token: string; token_type: string };

    // Store token first so the /me request can use it
    const tempState = JSON.stringify({ state: { token: data.access_token } });
    localStorage.setItem('auth-storage', tempState);

    // Fetch user profile
    const user = await request<{ id: string; username: string; email: string }>('/api/auth/me');
    return { token: data.access_token, user };
  },

  register: async (username: string, email: string, password: string) => {
    // Register returns user, then we login to get a token
    await request<{ id: string; username: string; email: string }>(
      '/api/auth/register',
      { method: 'POST', body: JSON.stringify({ username, email, password }) }
    );
    // Auto-login after registration
    return authApi.login(username, password);
  },

  me: () =>
    request<{ id: string; username: string; email: string }>('/api/auth/me'),
};

// Projects
export const projectsApi = {
  list: () =>
    request<{ items: import('../types').Project[] }>('/api/projects'),
  create: (name: string) =>
    request<import('../types').Project>('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  get: (id: string) =>
    request<import('../types').Project>(`/api/projects/${id}`),
  update: (id: string, data: Partial<import('../types').Project>) =>
    request<import('../types').Project>(`/api/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
};

// Media
export const mediaApi = {
  list: () =>
    request<import('../types').MediaFile[]>('/api/media'),
  get: (id: string) =>
    request<import('../types').MediaFile>(`/api/media/${id}`),
  upload: (file: File, onProgress?: (pct: number) => void) => {
    return new Promise<import('../types').MediaFile>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('file', file);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Upload failed')));

      const token = getToken();
      xhr.open('POST', `${BASE_URL}/api/media/upload`);
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.send(formData);
    });
  },
  delete: (id: string) =>
    request<void>(`/api/media/${id}`, { method: 'DELETE' }),
  streamUrl: (id: string) => {
    const token = getToken();
    return `${BASE_URL}/api/media/${id}/stream${token ? `?token=${token}` : ''}`;
  },
  thumbnailUrl: (id: string) => {
    const token = getToken();
    return `${BASE_URL}/api/media/${id}/thumbnail${token ? `?token=${token}` : ''}`;
  },
  proxyUrl: (id: string) => {
    const token = getToken();
    return `${BASE_URL}/api/media/${id}/proxy${token ? `?token=${token}` : ''}`;
  },
};

// Detection
export const detectionApi = {
  run: (mediaId: string) =>
    request<import('../types').DetectionResult>(`/api/detection/run/${mediaId}`, {
      method: 'POST',
    }),
  status: (mediaId: string) =>
    request<import('../types').DetectionResult>(`/api/detection/status/${mediaId}`),
  results: (mediaId: string) =>
    request<import('../types').DetectionResult>(`/api/detection/results/${mediaId}`),
};

// Render
export const renderApi = {
  submit: (projectId: string) =>
    request<import('../types').RenderJob>('/api/render', {
      method: 'POST',
      body: JSON.stringify({ projectId }),
    }),
  status: (jobId: string) =>
    request<import('../types').RenderJob>(`/api/render/${jobId}/status`),
  downloadUrl: (jobId: string) => `${BASE_URL}/api/render/${jobId}/download`,
};
