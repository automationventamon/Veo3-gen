const API_BASE  = import.meta.env.VITE_API_URL || "";
const getToken  = () => sessionStorage.getItem("flowgen_token");
const headers   = () => ({ Authorization: `Bearer ${getToken()}` });

export async function createJob(images) {
  const form = new FormData();
  const prompts = {};

  for (const entry of images) {
    form.append("images", entry.file, entry.file.name);
    prompts[entry.file.name] = entry.prompt;
  }
  form.append("prompts", JSON.stringify(prompts));

  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    headers: headers(),
    body: form,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getJob(jobId) {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, { headers: headers() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function listJobs() {
  const res = await fetch(`${API_BASE}/api/jobs`, { headers: headers() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function cancelJob(jobId) {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}/cancel`, {
    method: 'POST',
    headers: headers(),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export function downloadJobUrl(jobId) {
  return `${API_BASE}/api/jobs/${jobId}/download?token=${getToken()}`;
}
