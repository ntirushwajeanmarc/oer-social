"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api,
  getStoredUser,
  hasToken,
  mediaUrl,
  type PackListItem,
  type SocialExport,
} from "@/lib/api";

export default function AdminPage() {
  const router = useRouter();
  const [packs, setPacks] = useState<PackListItem[]>([]);
  const [topic, setTopic] = useState("");
  const [focus, setFocus] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [exports, setExports] = useState<SocialExport[]>([]);

  const load = useCallback(async () => {
    setPacks(await api.adminPacks());
  }, []);

  useEffect(() => {
    if (!hasToken()) {
      router.replace("/login");
      return;
    }
    const u = getStoredUser();
    if (u?.role !== "admin") {
      router.replace("/feed");
      return;
    }
    load().catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load")
    );
  }, [router, load]);

  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setExports([]);
    try {
      await api.generatePack({
        topic: topic.trim(),
        focus: focus.trim(),
      });
      setTopic("");
      setFocus("");
      await load();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
      await load().catch(() => undefined);
    } finally {
      setLoading(false);
    }
  }

  async function publish(id: string) {
    setError("");
    setBusyId(id);
    try {
      await api.publishPack(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setBusyId(null);
    }
  }

  async function regenImage(id: string) {
    setError("");
    setBusyId(id);
    try {
      await api.regenerateImage(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image failed");
    } finally {
      setBusyId(null);
    }
  }

  async function postSocial(id: string) {
    setError("");
    setBusyId(id);
    try {
      setExports(await api.publishSocial(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Social post failed");
    } finally {
      setBusyId(null);
    }
  }

  async function removePack(id: string, title: string) {
    if (!window.confirm(`Delete pack “${title}”? This cannot be undone.`)) {
      return;
    }
    setError("");
    setBusyId(id);
    try {
      await api.deletePack(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusyId(null);
    }
  }

  function downloadImage(path: string, title: string) {
    const href = mediaUrl(path);
    if (!href) return;
    const a = document.createElement("a");
    a.href = href;
    a.download = `${title.replace(/[^\w\-]+/g, "_").slice(0, 80) || "poster"}.png`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  return (
    <AppShell>
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-glacier">
        Admin
      </p>
      <h1 className="font-display mt-1.5 text-[1.75rem] leading-tight tracking-tight text-fjord sm:text-3xl">
        Create pack
      </h1>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink/55">
        Generate teaching packs with poster, case, and graded questions — then
        publish to the learner feed.
      </p>

      <form
        onSubmit={onGenerate}
        className="panel mt-6 space-y-3 p-5 sm:mt-8 sm:space-y-4 sm:p-6"
      >
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.14em] text-glacier">
            Topic
          </span>
          <textarea
            required
            rows={3}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="input-field rounded-md"
            placeholder="e.g. MACCE — intraoperative hypertension: causes, management, reflection"
            enterKeyHint="done"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.14em] text-glacier">
            Focus (optional)
          </span>
          <input
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            className="input-field rounded-md"
            placeholder="reflection, keynotes, management…"
            enterKeyHint="done"
          />
        </label>
        <div className="sticky-generate">
          <button
            type="submit"
            disabled={loading || !topic.trim()}
            className="btn-primary w-full rounded-md"
          >
            {loading ? "Generating…" : "Generate pack"}
          </button>
        </div>
      </form>

      {error ? (
        <p className="mt-4 break-words rounded-none border border-red-200 bg-red-50/80 p-3 text-sm text-red-700/90">
          {error}
        </p>
      ) : null}

      <section className="mt-7 space-y-3 sm:mt-10">
        <h2 className="font-display text-lg text-fjord sm:text-xl">Your packs</h2>
        {packs.length === 0 ? (
          <p className="panel p-5 text-sm text-mist">No packs yet.</p>
        ) : (
          packs.map((p) => (
            <article key={p.id} className="panel overflow-hidden">
              {p.poster_image_path ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={mediaUrl(p.poster_image_path)}
                  alt={p.poster_title}
                  className="aspect-[4/3] w-full object-cover sm:aspect-[2/1] sm:max-h-56"
                />
              ) : null}
              <div className="p-4 sm:flex sm:items-start sm:justify-between sm:gap-4 sm:p-5">
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-[0.16em] text-mist">
                    <span className={p.status === "published" ? "text-glacier" : ""}>
                      {p.status}
                    </span>
                    {" · "}
                    {p.question_count} q
                    {p.poster_image_path ? " · image" : " · no image"}
                  </p>
                  <h3 className="font-display mt-1 break-words text-base leading-snug text-fjord sm:text-lg">
                    {p.poster_title}
                  </h3>
                  <p className="mt-1 line-clamp-2 break-words text-sm text-ink/60">
                    {p.topic}
                  </p>
                </div>
                <div className="action-grid mt-4 sm:mt-0 sm:min-w-[11rem]">
                  <Link href={`/packs/${p.id}`} className="btn-secondary">
                    Open
                  </Link>
                  {p.poster_image_path ? (
                    <button
                      type="button"
                      onClick={() => downloadImage(p.poster_image_path, p.poster_title)}
                      className="btn-secondary"
                    >
                      Download
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busyId === p.id}
                      onClick={() => regenImage(p.id)}
                      className="btn-primary"
                    >
                      {busyId === p.id ? "…" : "Image"}
                    </button>
                  )}
                  {p.status !== "published" ? (
                    <button
                      type="button"
                      disabled={busyId === p.id}
                      onClick={() => publish(p.id)}
                      className="btn-primary span-2"
                    >
                      Publish
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busyId === p.id}
                      onClick={() => postSocial(p.id)}
                      className="btn-secondary span-2"
                    >
                      {busyId === p.id ? "Posting…" : "Post IG & X"}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busyId === p.id}
                    onClick={() => removePack(p.id, p.poster_title)}
                    className="btn-danger span-2"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </article>
          ))
        )}
      </section>

      {exports.length > 0 ? (
        <section className="mt-8 space-y-3 sm:mt-10 sm:space-y-4">
          <h2 className="font-display text-lg text-fjord sm:text-xl">
            Social results
          </h2>
          {exports.map((ex) => (
            <div key={ex.id} className="panel p-4 sm:p-5">
              <p className="text-[10px] uppercase tracking-[0.16em] text-glacier">
                {ex.platform} · {ex.status}
                {ex.external_id ? ` · id ${ex.external_id}` : ""}
              </p>
              {ex.error_message ? (
                <p className="mt-2 break-words text-sm text-red-700/75">
                  {ex.error_message}
                </p>
              ) : null}
              <p className="mt-2 whitespace-pre-wrap break-words text-sm text-ink/80">
                {ex.caption}
              </p>
            </div>
          ))}
        </section>
      ) : null}
    </AppShell>
  );
}
