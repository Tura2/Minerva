import axios, { AxiosInstance } from "axios";
import { ApiError } from "./types";

const apiClient: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: {
    "Content-Type": "application/json",
  },
});

// Intercept network-level failures (ECONNREFUSED, wrong port, CORS) and
// surface a human-readable message instead of an opaque AxiosError.
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (!err.response) {
      // No HTTP response — server unreachable or CORS preflight blocked
      const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      throw new ApiError(0, `Backend not reachable at ${base}. Is uvicorn running? Check NEXT_PUBLIC_API_URL in .env.local.`);
    }
    // Let individual API functions handle HTTP errors (4xx/5xx)
    return Promise.reject(err);
  }
);

export default apiClient;
