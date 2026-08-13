"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Markdown } from "@/components/Markdown";
import { api, hasToken, mediaUrl, type Pack, type Submission } from "@/lib/api";

export default function PackDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [pack, setPack] = useState<Pack | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, Submission>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) {
      router.replace("/login");
      return;
    }
    api
      .getPack(id)
      .then(setPack)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed"));
  }, [id, router]);

  async function onSubmit(e: FormEvent, questionId: string) {
    e.preventDefault();
    const answer = (answers[questionId] || "").trim();
    if (!answer) return;
    setBusy(questionId);
    setError("");
    try {
      const sub = await api.submitAnswer(questionId, answer);
      setResults((prev) => ({ ...prev, [questionId]: sub }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Grading failed");
    } finally {
      setBusy(null);
    }
  }

  if (!pack && !error) {
    return (
      <AppShell>
        <p className="text-glacier">Loading pack…</p>
      </AppShell>
    );
  }

  if (!pack) {
    return (
      <AppShell>
        <p className="text-red-700/80">{error}</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <p className="text-[11px] uppercase tracking-[0.22em] text-glacier">
        {pack.topic}
      </p>
      <h1 className="font-display mt-2 break-words text-2xl text-fjord sm:text-3xl md:text-4xl">
        {pack.poster_title}
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink/70">
        {pack.poster_caption}
      </p>

      {pack.poster_image_path ? (
        <div className="panel mt-6 overflow-hidden sm:mt-8">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={mediaUrl(pack.poster_image_path)}
            alt={pack.poster_title}
            className="mx-auto w-full max-w-xl object-contain"
          />
        </div>
      ) : null}

      <section className="panel mt-6 p-4 sm:mt-8 sm:p-6">
        <h2 className="font-display text-lg text-fjord sm:text-xl">Elaboration</h2>
        <div className="mt-3">
          <Markdown content={pack.elaboration} />
        </div>
      </section>

      <section className="panel mt-4 p-4 sm:mt-6 sm:p-6">
        <h2 className="font-display text-lg text-fjord sm:text-xl">Case study</h2>
        <div className="mt-3">
          <Markdown content={pack.case_study} />
        </div>
      </section>

      <section className="mt-8 space-y-4 sm:mt-10 sm:space-y-6">
        <h2 className="font-display text-lg text-fjord sm:text-xl">
          Audience questions
        </h2>
        {pack.questions.map((q, i) => {
          const result = results[q.id];
          return (
            <div key={q.id} className="panel p-4 sm:p-5">
              <p className="text-[10px] uppercase tracking-[0.16em] text-mist">
                Question {i + 1}
              </p>
              <div className="mt-2 text-sm font-medium text-fjord">
                <Markdown content={q.prompt} />
              </div>
              {!result ? (
                <form onSubmit={(e) => onSubmit(e, q.id)} className="mt-4 space-y-3">
                  <textarea
                    required
                    rows={5}
                    value={answers[q.id] || ""}
                    onChange={(e) =>
                      setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))
                    }
                    className="input-field min-h-[8rem] resize-y text-sm"
                    placeholder="Write your answer…"
                  />
                  <button
                    type="submit"
                    disabled={busy === q.id}
                    className="btn-primary"
                  >
                    {busy === q.id ? "AI grading…" : "Submit for feedback"}
                  </button>
                </form>
              ) : (
                <div className="mt-4 border-t border-fjord/10 pt-4">
                  <p className="font-display text-3xl text-fjord sm:text-4xl">
                    {result.score.toFixed(0)}
                    <span className="text-base text-mist"> / 100</span>
                  </p>
                  <div className="mt-3">
                    <Markdown content={result.feedback} />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </section>

      {error ? <p className="mt-4 text-sm text-red-700/80">{error}</p> : null}

      <details className="mt-8 text-sm text-ink/50 sm:mt-10">
        <summary className="cursor-pointer py-2 text-glacier">
          Poster visual prompt
        </summary>
        <p className="mt-2 whitespace-pre-wrap break-words">{pack.poster_visual_prompt}</p>
      </details>
    </AppShell>
  );
}
