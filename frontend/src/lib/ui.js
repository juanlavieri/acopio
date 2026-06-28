// Shared UI helpers: category colors, formatting.

export const KIND_META = {
  food: { label: "Food", color: "#f59e0b", emoji: "🍚" },
  water: { label: "Water", color: "#0ea5e9", emoji: "💧" },
  medical: { label: "Medical", color: "#ef4444", emoji: "➕" },
  hygiene: { label: "Hygiene", color: "#8b5cf6", emoji: "🧼" },
  shelter: { label: "Shelter", color: "#14b8a6", emoji: "⛺" },
  clothing: { label: "Clothing", color: "#ec4899", emoji: "👕" },
  tools: { label: "Tools", color: "#64748b", emoji: "🔦" },
  baby: { label: "Baby", color: "#f97316", emoji: "🍼" },
  other: { label: "Other", color: "#94a3b8", emoji: "📦" },
};

export function kindColor(kind) {
  return (KIND_META[kind] || KIND_META.other).color;
}

export const EXPIRY_META = {
  expired: { color: "#dc2626", bg: "#fef2f2" },
  critical: { color: "#ea580c", bg: "#fff7ed" },
  warning: { color: "#d97706", bg: "#fffbeb" },
  caution: { color: "#ca8a04", bg: "#fefce8" },
  ok: { color: "#16a34a", bg: "#f0fdf4" },
  none: { color: "#94a3b8", bg: "#f8fafc" },
};
export function expiryColor(s) {
  return (EXPIRY_META[s] || EXPIRY_META.none).color;
}

export const PRIORITY_META = {
  urgent: { color: "#dc2626", bg: "#fef2f2" },
  high: { color: "#ea580c", bg: "#fff7ed" },
  normal: { color: "#0d9488", bg: "#f0fdfa" },
  low: { color: "#64748b", bg: "#f8fafc" },
};
export function priorityColor(p) {
  return (PRIORITY_META[p] || PRIORITY_META.normal).color;
}

export const REASONS = {
  in: ["donation", "purchase", "transfer_in", "return"],
  out: ["distributed", "transferred", "damaged", "expired", "lost"],
};

export function fmtNum(n) {
  if (n === null || n === undefined) return "0";
  const v = Number(n);
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function fmtDate(s) {
  if (!s) return "";
  try {
    return new Date(s).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return s;
  }
}

export function timeAgo(s) {
  if (!s) return "";
  const d = new Date(s).getTime();
  const sec = Math.floor((Date.now() - d) / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}
