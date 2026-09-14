const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = new Error(data?.detail || `HTTP ${res.status}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  rules: () => request("/rules/"),
  elections: () => request("/elections/"),
  election: (slug) => request(`/elections/${slug}/`),
  compute: (slug) => request(`/elections/${slug}/compute/`, { method: "POST" }),
  publish: (slug) => request(`/elections/${slug}/publish/`, { method: "POST" }),
  ballotChain: (slug, code) =>
    request(`/elections/${slug}/ballots/${encodeURIComponent(code)}/`),
};
