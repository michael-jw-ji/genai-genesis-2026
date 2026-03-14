import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

type RevealTag = "div" | "section" | "article" | "header" | "main" | "aside" | "nav" | "span";

type RevealProps = {
  as?: RevealTag;
  children: ReactNode;
  className?: string;
  delay?: number;
  id?: string;
};

function Reveal({
  as: Tag = "div",
  children,
  className = "",
  delay = 0,
  id,
}: RevealProps) {
  const ref = useRef<HTMLElement | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;

    if (!node) {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    if (mediaQuery.matches) {
      setIsVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting);
      },
      { threshold: 0.18, rootMargin: "0px 0px -10% 0px" }
    );

    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  const style = { "--reveal-delay": `${delay}ms` } as CSSProperties;

  return (
    <Tag
      ref={ref as never}
      id={id}
      className={`reveal ${isVisible ? "is-visible" : ""} ${className}`.trim()}
      style={style}
    >
      {children}
    </Tag>
  );
}

export default Reveal;
