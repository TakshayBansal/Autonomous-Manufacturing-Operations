export function roleLabel(role: string) {
  return role.split("_").map((part) => part[0]?.toUpperCase() + part.slice(1)).join(" ");
}

export function asText(value: unknown, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function moneyLakh(value: unknown) {
  const amount = Number(value ?? 0);
  if (Number.isNaN(amount)) return "Rs. -";
  return `Rs. ${(amount / 100000).toFixed(1)}L`;
}
