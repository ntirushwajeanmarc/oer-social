"use client";

import { Suspense } from "react";
import WorkspacePage from "./WorkspaceClient";

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-5xl px-4 py-10 text-sm text-ink/45">
          Loading workspace…
        </div>
      }
    >
      <WorkspacePage />
    </Suspense>
  );
}
