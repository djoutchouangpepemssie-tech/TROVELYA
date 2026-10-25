import { notFound } from "next/navigation";

// Any unknown address under /[locale] gets the French 404 (not-found.tsx), not Next's default.
export default function UnknownPage() {
  notFound();
}
