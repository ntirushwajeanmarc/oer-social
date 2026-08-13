import Link from "next/link";

export default function HomePage() {
  return (
    <div className="relative mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-4 py-12 sm:px-6 sm:py-16">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(var(--ice) 1px, transparent 1px), linear-gradient(90deg, var(--ice) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
          maskImage:
            "radial-gradient(ellipse 75% 55% at 40% 35%, black, transparent)",
        }}
      />
      <div className="relative">
        <p className="text-[11px] uppercase tracking-[0.28em] text-glacier sm:text-xs">
          Open Education Resources
        </p>
        <h1 className="font-display mt-3 max-w-xl text-4xl leading-[1.08] tracking-tight text-fjord sm:text-5xl md:text-6xl">
          OER Social
        </h1>
        <p className="mt-4 max-w-lg text-base font-light leading-relaxed text-ink/70 sm:text-lg">
          AI posters, elaborations, and case questions for anesthesia,
          perioperative medicine, and critical care — with personalized
          feedback for every learner.
        </p>
        <div className="mt-8 flex w-full max-w-sm flex-col gap-3 sm:mt-10 sm:max-w-none sm:flex-row">
          <Link href="/signup" className="btn-primary text-center">
            Learner signup
          </Link>
          <Link href="/login" className="btn-secondary text-center">
            Log in
          </Link>
        </div>
      </div>
    </div>
  );
}
