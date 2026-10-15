import { useEffect, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface TypewriterTextProps {
  text: string;
  enabled?: boolean;
  speed?: number;
  intervalMs?: number;
  onDone?: () => void;
}

/**
 * Reveals text progressively for new assistant messages.
 * Renders markdown (GFM: bold, lists, tables, etc.).
 */
export function TypewriterText({
  text,
  enabled = true,
  speed = 3,
  intervalMs = 16,
  onDone,
}: TypewriterTextProps) {
  const [displayed, setDisplayed] = useState(enabled ? '' : text);
  const startedRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setDisplayed(text);
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;

    let i = 0;
    const id = setInterval(() => {
      i = Math.min(i + speed, text.length);
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(id);
        onDone?.();
      }
    }, intervalMs);

    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isTyping = enabled && displayed.length < text.length;

  return (
    <div className="markdown-body break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ node, ...props }) => (
            <p className="mb-3 last:mb-0 leading-[1.7]" {...props} />
          ),
          ul: ({ node, ...props }) => (
            <ul className="list-disc pl-5 mb-3 space-y-1" {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol className="list-decimal pl-5 mb-3 space-y-1" {...props} />
          ),
          li: ({ node, ...props }) => <li className="leading-[1.6]" {...props} />,
          strong: ({ node, ...props }) => (
            <strong className="font-semibold text-foreground" {...props} />
          ),
          em: ({ node, ...props }) => <em className="italic" {...props} />,
          a: ({ node, ...props }) => (
            <a
              className="text-primary underline underline-offset-2 hover:opacity-80"
              target="_blank"
              rel="noopener noreferrer"
              {...props}
            />
          ),
          h1: ({ node, ...props }) => (
            <h1 className="text-[18px] font-semibold mt-4 mb-2" {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className="text-[16px] font-semibold mt-4 mb-2" {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className="text-[15px] font-semibold mt-3 mb-1.5" {...props} />
          ),
          code: ({ node, className, children, ...props }) => {
            const inline = !className;
            if (inline) {
              return (
                <code
                  className="px-1 py-0.5 rounded bg-muted text-[13px] font-mono"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className="block p-3 rounded-md bg-muted text-[13px] font-mono overflow-x-auto"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ node, ...props }) => (
            <pre className="mb-3 overflow-x-auto" {...props} />
          ),
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="border-l-2 border-border pl-3 my-3 text-muted-foreground"
              {...props}
            />
          ),
          table: ({ node, ...props }) => (
            <div className="my-3 overflow-x-auto">
              <table
                className="w-full border-collapse text-[13px]"
                {...props}
              />
            </div>
          ),
          thead: ({ node, ...props }) => (
            <thead className="border-b border-border" {...props} />
          ),
          th: ({ node, ...props }) => (
            <th
              className="text-left font-medium px-3 py-2 text-muted-foreground"
              {...props}
            />
          ),
          td: ({ node, ...props }) => (
            <td className="px-3 py-2 border-b border-border/60" {...props} />
          ),
          hr: () => <hr className="my-4 border-border" />,
        }}
      >
        {displayed}
      </ReactMarkdown>
      {isTyping && (
        <span className="inline-block w-[2px] h-[0.9em] align-[-2px] ml-0.5 bg-primary/60 animate-pulse" />
      )}
    </div>
  );
}
