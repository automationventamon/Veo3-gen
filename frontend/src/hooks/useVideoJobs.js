import { useState, useEffect, useRef, useCallback } from "react";
import { listJobs, getJob } from "../services/jobService.js";

const POLL_MS = 5000;

export function useVideoJobs() {
  const [jobs,    setJobs]    = useState([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
    } catch {
      // silent — network hiccup
    }
  }, []);

  // Poll active jobs individually for fresh status
  const pollActive = useCallback(async () => {
    setJobs((prev) => {
      const active = prev.filter((j) => j.status === "pending" || j.status === "running");
      if (!active.length) return prev;

      Promise.all(active.map((j) => getJob(j.id).catch(() => null))).then((results) => {
        setJobs((current) => {
          const map = new Map(current.map((j) => [j.id, j]));
          for (const r of results) {
            if (r) map.set(r.id, r);
          }
          return Array.from(map.values());
        });
      });
      return prev;
    });
  }, []);

  useEffect(() => {
    fetchJobs();
    timerRef.current = setInterval(pollActive, POLL_MS);
    return () => clearInterval(timerRef.current);
  }, [fetchJobs, pollActive]);

  const addJob = (job) => {
    setJobs((prev) => [job, ...prev]);
  };

  const hasActive = jobs.some((j) => j.status === "pending" || j.status === "running");

  return { jobs, loading, addJob, refresh: fetchJobs, hasActive };
}
