"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({
  content,
  className = "",
}: {
  content: string;
  className?: string;
}) {
  if (!content?.trim()) return null;

  return (
    <div className={`md-body ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
