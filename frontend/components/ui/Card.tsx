import { type HTMLAttributes } from "react";
import clsx from "clsx";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Lifts and brightens the border on hover — for cards that act like a
   *  single clickable/selectable unit rather than a passive container. */
  interactive?: boolean;
}

export function Card({ className, interactive, ...props }: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-md border border-border bg-surface p-5 transition-colors duration-150",
        interactive && "hover:border-border-strong hover:bg-surface-hover",
        className
      )}
      {...props}
    />
  );
}
