import { useEffect, useState } from "react";
import axiosInstance from "../api";
import type { DepartmentNode } from "../utils/departmentNavigation";

let request: Promise<DepartmentNode[]> | null = null;

function loadNavigation(): Promise<DepartmentNode[]> {
  request ??= axiosInstance
    .get<DepartmentNode[]>("departments/navigation/")
    .then(({ data }) => data)
    .catch((error: unknown) => {
      request = null;
      throw error;
    });
  return request;
}

export function useNavigationNodes() {
  const [nodes, setNodes] = useState<DepartmentNode[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setStatus("loading");
    loadNavigation()
      .then((data) => {
        if (!alive) return;
        setNodes(data);
        setStatus("ready");
      })
      .catch(() => alive && setStatus("error"));
    return () => {
      alive = false;
    };
  }, [attempt]);
  return { nodes, status, retry: () => setAttempt((n) => n + 1) };
}
