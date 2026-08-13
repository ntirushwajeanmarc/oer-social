"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, saveAuth } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [cadre, setCadre] = useState("Anesthesia trainee");
  const [site, setSite] = useState("");
  const [educationLevel, setEducationLevel] = useState("");
  const [experienceYears, setExperienceYears] = useState("0");
  const [learningGoals, setLearningGoals] = useState("");
  const [topicsOfInterest, setTopicsOfInterest] = useState("");
  const [preferredLanguage, setPreferredLanguage] = useState("English");
  const [localContext, setLocalContext] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.signup({
        name: name.trim(),
        email: email.trim(),
        password,
        cadre: cadre.trim(),
        site: site.trim() || "Training site",
        education_level: educationLevel.trim(),
        experience_years: Number(experienceYears) || 0,
        learning_goals: learningGoals.trim(),
        topics_of_interest: topicsOfInterest.trim(),
        preferred_language: preferredLanguage.trim() || "English",
        local_context: localContext.trim(),
      });
      saveAuth(res.access_token, res.user);
      await new Promise((r) => setTimeout(r, 50));
      router.push("/feed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-4 py-10 sm:px-6 sm:py-16">
      <Link href="/" className="font-display text-2xl text-fjord">
        OER Social
      </Link>
      <h1 className="mt-6 font-display text-3xl text-fjord sm:text-4xl">
        Learner signup
      </h1>
      <p className="mt-2 text-sm text-ink/60">
        Complete this checklist once. The AI stores it as your learning profile
        and uses it to personalize future grading and feedback.
      </p>
      <form
        method="post"
        action="/signup"
        autoComplete="on"
        onSubmit={onSubmit}
        className="panel mt-8 space-y-4 p-5 sm:p-6"
      >
        <Field id="name" name="name" label="Full name" autoComplete="name" value={name} onChange={setName} required />
        <Field id="email" name="username" label="Email" type="email" autoComplete="username" value={email} onChange={setEmail} required />
        <Field id="password" name="password" label="Password" type="password" autoComplete="new-password" value={password} onChange={setPassword} required minLength={8} hint="At least 8 characters" />
        <Field id="cadre" name="organization-title" label="Cadre / role" autoComplete="organization-title" value={cadre} onChange={setCadre} />
        <Field id="site" name="organization" label="Training site" autoComplete="organization" value={site} onChange={setSite} />
        <div className="border-t border-fjord/10 pt-5">
          <p className="text-xs uppercase tracking-[0.16em] text-glacier">
            Learning profile
          </p>
          <p className="mt-1 text-xs leading-relaxed text-mist">
            Do not enter patient names or other confidential clinical information.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="education-level"
            name="education-level"
            label="Education / training level"
            value={educationLevel}
            onChange={setEducationLevel}
            required
          />
          <Field
            id="experience-years"
            name="experience-years"
            label="Years of clinical experience"
            type="number"
            value={experienceYears}
            onChange={setExperienceYears}
            required
            min={0}
            max={70}
          />
          <Field
            id="preferred-language"
            name="preferred-language"
            label="Preferred learning language"
            value={preferredLanguage}
            onChange={setPreferredLanguage}
            required
          />
          <Field
            id="topics"
            name="topics"
            label="Topics of greatest interest"
            value={topicsOfInterest}
            onChange={setTopicsOfInterest}
            placeholder="Resuscitation, safe anesthesia, postoperative pain"
            required
          />
        </div>
        <TextArea
          id="learning-goals"
          name="learning-goals"
          label="What do you want to learn or improve?"
          value={learningGoals}
          onChange={setLearningGoals}
          required
        />
        <TextArea
          id="local-context"
          name="local-context"
          label="Local context, available equipment, or learning constraints"
          value={localContext}
          onChange={setLocalContext}
          placeholder="Describe your training setting without patient-identifying information"
          required
        />
        {error ? <p className="text-sm text-red-700/80">{error}</p> : null}
        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Creating…" : "Sign up"}
        </button>
      </form>
      <p className="mt-6 text-sm text-ink/55">
        Already have an account?{" "}
        <Link href="/login" className="text-fjord underline underline-offset-4">
          Log in
        </Link>
      </p>
    </div>
  );
}

function Field(props: {
  id: string;
  name: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  min?: number;
  max?: number;
  hint?: string;
  placeholder?: string;
}) {
  return (
    <label className="block" htmlFor={props.id}>
      <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-glacier">
        {props.label}
      </span>
      <input
        id={props.id}
        name={props.name}
        type={props.type ?? "text"}
        autoComplete={props.autoComplete}
        required={props.required}
        minLength={props.minLength}
        min={props.min}
        max={props.max}
        placeholder={props.placeholder}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        className="input-field"
      />
      {props.hint ? <span className="mt-1 block text-xs text-mist">{props.hint}</span> : null}
    </label>
  );
}

function TextArea(props: {
  id: string;
  name: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="block" htmlFor={props.id}>
      <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-glacier">
        {props.label}
      </span>
      <textarea
        id={props.id}
        name={props.name}
        rows={4}
        required={props.required}
        value={props.value}
        placeholder={props.placeholder}
        onChange={(e) => props.onChange(e.target.value)}
        className="input-field min-h-28 resize-y"
      />
    </label>
  );
}
