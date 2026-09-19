"use client";

import { useEffect, useState } from "react";
import { Share2 } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { getSocialPlatforms } from "@/lib/api";

/**
 * Header entry to the connected accounts.
 *
 * Without it the page is reachable only from the publish panel, which
 * needs a finished render to appear — so an account connected on Monday
 * could not be removed on Tuesday without first rendering something. The
 * same reasoning as the credit balance in AccountBar: a page nothing
 * links to is a page that does not exist.
 *
 * Renders nothing when this deployment publishes nowhere, following the
 * rule the platform list itself follows — an unconfigured platform is
 * absent rather than shown leading to a dead end. The call is also what
 * signed-out pages get a 401 from, and the same silence is right there.
 */
export function ConnectionsLink({ className }: { className?: string }) {
  const [configured, setConfigured] = useState(false);

  useEffect(() => {
    let live = true;
    getSocialPlatforms()
      .then((platforms) => live && setConfigured(platforms.length > 0))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  if (!configured) return null;

  return (
    <Link href="/connections" className={className}>
      <Share2 size={16} />
      Connections
    </Link>
  );
}
