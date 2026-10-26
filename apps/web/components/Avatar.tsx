import { Avatar } from "@trovelya/ui";

import { initials } from "@/lib/initials";
import { pickVariant, type Variant } from "@/lib/media";

/** A member's photo (P2-T02c), or their initials while they have none. */
export function MemberAvatar({
  name,
  avatar,
  size,
}: {
  name: string;
  avatar?: Variant[] | null;
  size: number;
}) {
  const src = pickVariant(avatar, size);
  return <Avatar name={name} initials={initials(name)} size={size} {...(src ? { src } : {})} />;
}
