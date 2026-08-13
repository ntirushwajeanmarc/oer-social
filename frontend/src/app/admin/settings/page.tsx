"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api,
  getStoredUser,
  hasToken,
  type ProgramBrief,
  type ProgramBriefInput,
} from "@/lib/api";

const emptyBrief: ProgramBriefInput = {
  program_topic: "",
  target_learners: "",
  oer_rationale: "",
  distribution_channels: "",
  learning_objectives: "",
  approved_references: "",
  local_context: "",
  preferred_language: "English",
  restricted_topics: "",
  brand_tone: "",
  responsible_educator: "",
};

export default function ProgramSettingsPage() {
  const router = useRouter();
  const [form, setForm] = useState<ProgramBriefInput>(emptyBrief);
  const [history, setHistory] = useState<ProgramBrief[]>([]);
  const [version, setVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [current, versions] = await Promise.all([
      api.currentProgramBrief(),
      api.programBriefHistory(),
    ]);
    const {
      id: _id,
      version: currentVersion,
      is_active: _isActive,
      created_at: _createdAt,
      ...editable
    } = current;
    void _id;
    void _isActive;
    void _createdAt;
    setForm(editable);
    setVersion(currentVersion);
    setHistory(versions);
  }, []);

  useEffect(() => {
    if (!hasToken()) {
      router.replace("/login");
      return;
    }
    if (getStoredUser()?.role !== "admin") {
      router.replace("/feed");
      return;
    }
    load()
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load settings")
      )
      .finally(() => setLoading(false));
  }, [load, router]);

  function update<K extends keyof ProgramBriefInput>(
    key: K,
    value: ProgramBriefInput[K]
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await api.updateProgramBrief(form);
      setVersion(saved.version);
      setMessage(
        `Version ${saved.version} is now active and will ground all future AI work.`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save brief");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <AppShell>
        <p className="text-glacier">Loading program brief…</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <p className="text-[11px] uppercase tracking-[0.22em] text-glacier">
        Admin settings
      </p>
      <h1 className="font-display mt-2 text-2xl text-fjord sm:text-3xl">
        OER program brief
      </h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink/60">
        This is the platform’s authoritative grounding. The active version is
        included in poster generation, case questions, grading, and feedback.
        Saving creates a new audit version rather than overwriting history.
      </p>

      {version ? (
        <p className="mt-4 text-xs uppercase tracking-[0.14em] text-glacier">
          Active version {version}
        </p>
      ) : null}

      <form
        onSubmit={onSubmit}
        className="panel mt-6 space-y-5 p-4 sm:mt-8 sm:p-6"
      >
        <Area
          label="Program / topic"
          value={form.program_topic}
          onChange={(value) => update("program_topic", value)}
          required
        />
        <Area
          label="Stakeholders and target learners"
          value={form.target_learners}
          onChange={(value) => update("target_learners", value)}
          required
        />
        <Area
          label="Why OER is appropriate"
          value={form.oer_rationale}
          onChange={(value) => update("oer_rationale", value)}
          required
        />
        <Area
          label="Distribution channels and OER tools"
          value={form.distribution_channels}
          onChange={(value) => update("distribution_channels", value)}
          required
        />
        <Area
          label="Program and learning objectives"
          value={form.learning_objectives}
          onChange={(value) => update("learning_objectives", value)}
          required
          rows={5}
        />
        <Area
          label="Approved references, guidelines, and protocols"
          value={form.approved_references}
          onChange={(value) => update("approved_references", value)}
          placeholder="Name approved sources and current local protocols"
          rows={5}
        />
        <Area
          label="Country, training sites, resources, and local context"
          value={form.local_context}
          onChange={(value) => update("local_context", value)}
        />
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Preferred language"
            value={form.preferred_language}
            onChange={(value) => update("preferred_language", value)}
            required
          />
          <Field
            label="Responsible educator"
            value={form.responsible_educator}
            onChange={(value) => update("responsible_educator", value)}
          />
        </div>
        <Area
          label="Restricted topics and safety boundaries"
          value={form.restricted_topics}
          onChange={(value) => update("restricted_topics", value)}
          rows={5}
        />
        <Area
          label="Brand, poster style, and teaching tone"
          value={form.brand_tone}
          onChange={(value) => update("brand_tone", value)}
        />

        {error ? <p className="text-sm text-red-700/80">{error}</p> : null}
        {message ? <p className="text-sm text-glacier">{message}</p> : null}

        <button type="submit" disabled={saving} className="btn-primary">
          {saving ? "Saving new version…" : "Save and activate"}
        </button>
      </form>

      <section className="mt-8 sm:mt-10">
        <h2 className="font-display text-lg text-fjord sm:text-xl">
          Version history
        </h2>
        <div className="mt-3 space-y-2">
          {history.map((item) => (
            <div
              key={item.id}
              className="panel flex flex-col gap-1 p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="text-sm font-medium text-fjord">
                  Version {item.version}
                  {item.is_active ? " — active" : ""}
                </p>
                <p className="text-xs text-mist">{item.responsible_educator}</p>
              </div>
              <time className="text-xs text-mist">
                {new Date(item.created_at).toLocaleString()}
              </time>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}

function Area({
  label,
  value,
  onChange,
  required,
  placeholder,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-glacier">
        {label}
      </span>
      <textarea
        rows={rows}
        required={required}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="input-field min-h-24 resize-y"
      />
    </label>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-glacier">
        {label}
      </span>
      <input
        required={required}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="input-field"
      />
    </label>
  );
}
