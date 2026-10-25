/** Up to two capital initials of a display name, for avatars without a photo. */
export function initials(name: string): string {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() ?? "");
  return letters.slice(0, 2).join("") || "?";
}
