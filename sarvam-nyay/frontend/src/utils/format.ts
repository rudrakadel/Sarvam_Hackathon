/**
 * VeriDictum AI — Formatting Utilities
 */

/** Convert snake_case / UPPER_CASE enum strings to Title Case labels. */
export const formatLabel = (s: string): string =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Convert raw seconds (e.g. 134.0) to MM:SS display (e.g. "2:14"). */
export const formatTimestamp = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
};

/** Format response_time_ms into a human-readable string. */
export const formatResponseTime = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`;
  return `Answered in ${(ms / 1000).toFixed(1)}s`;
};

/** Parse a User-Agent string into a human-readable device label. */
export const parseUserAgent = (ua: string | null | undefined): string => {
  if (!ua) return "Unknown device";
  const s = ua.toLowerCase();

  // OS detection
  let os = "Unknown OS";
  if (s.includes("windows")) os = "Windows";
  else if (s.includes("mac os") || s.includes("macintosh")) os = "macOS";
  else if (s.includes("iphone") || s.includes("ipad")) os = "iOS";
  else if (s.includes("android")) os = "Android";
  else if (s.includes("linux")) os = "Linux";

  // Browser detection
  let browser = "Unknown Browser";
  if (s.includes("edg/") || s.includes("edge/")) browser = "Edge";
  else if (s.includes("chrome") && !s.includes("chromium")) browser = "Chrome";
  else if (s.includes("firefox")) browser = "Firefox";
  else if (s.includes("safari") && !s.includes("chrome")) browser = "Safari";
  else if (s.includes("opera") || s.includes("opr/")) browser = "Opera";

  if (browser === "Unknown Browser" && os === "Unknown OS") return "Unknown device";
  if (browser === "Unknown Browser") return `${os} device`;
  if (os === "Unknown OS") return browser;
  return `${browser} on ${os}`;
};
