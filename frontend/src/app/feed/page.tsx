"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, hasToken, mediaUrl, type PackListItem } from "@/lib/api";

export default function FeedPage() {
  const router = useRouter();
  const [packs, setPacks] = useState<PackListItem[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setPacks(await api.feed());
  }, []);

  useEffect(() => {
    if (!hasToken()) {
      router.replace("/login");
      return;
    }
    load().catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load feed")
    );
  }, [router, load]);

  return (
    <AppShell>
      <p className="text-[11px] uppercase tracking-[0.22em] text-glacier">
        Dashboard
      </p>
      <h1 className="font-display mt-2 text-2xl text-fjord sm:text-3xl">
        Published packs
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-ink/60">
        Open a pack to study the poster, case, and submit answers for AI feedback.
      </p>

      {error ? <p className="mt-4 text-sm text-red-700/80">{error}</p> : null}

      <div className="mt-5 grid gap-3 sm:mt-8 sm:grid-cols-2 sm:gap-4">
        {packs.length === 0 ? (
          <p className="panel border-dashed p-5 text-sm text-mist sm:col-span-2 sm:p-8">
            No published content yet.
          </p>
        ) : (
          packs.map((p) => (
            <Link
              key={p.id}
              href={`/packs/${p.id}`}
              className="panel block overflow-hidden active:opacity-90"
            >
              {p.poster_image_path ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={mediaUrl(p.poster_image_path)}
                  alt={p.poster_title}
                  className="aspect-[4/3] w-full object-cover sm:aspect-square"
                />
              ) : (
                <div className="flex aspect-[4/3] items-center justify-center bg-ice/60 text-xs uppercase tracking-[0.16em] text-mist sm:aspect-square">
                  No image
                </div>
              )}
              <div className="p-4">
                <p className="text-[10px] uppercase tracking-[0.16em] text-mist">
                  {p.question_count} questions
                </p>
                <h2 className="font-display mt-1 break-words text-base leading-snug text-fjord sm:text-lg">
                  {p.poster_title}
                </h2>
                <p className="mt-1 line-clamp-2 break-words text-sm text-ink/60">
                  {p.topic}
                </p>
              </div>
            </Link>
          ))
        )}
      </div>
    </AppShell>
  );
}
