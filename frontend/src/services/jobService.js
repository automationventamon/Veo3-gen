const getToken = () => sessionStorage.getItem("flowgen_token");

const headers = () => ({
  Authorization: `Bearer ${getToken()}`,
});

export async function createJob(images) {
  const form = new FormData();
  const prompts = {};

  for (const entry of images) {
    form.append("images", entry.file, entry.file.name);
    prompts[entry.file.name] = entry.prompt;
  }
  form.append("prompts", JSON.stringify(prompts));

  const res = await fetch("/api/jobs", {
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
  const res = await fetch(`/api/jobs/${jobId}`, { headers: headers() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function listJobs() {
  const res = await fetch("/api/jobs", { headers: headers() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function downloadJobUrl(jobId) {
  return `/api/jobs/${jobId}/download?token=${getToken()}`;
}
