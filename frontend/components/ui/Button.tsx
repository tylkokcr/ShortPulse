import { type ButtonHTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

/**
 * `gradient` is kept as a name because it is the primary call to action in
 * a dozen call sites, but it no longer draws a gradient — a moving
 * three-stop fill was the loudest generated-template tell in the old
 * design. It is now the accent, flat, and it is the only thing on a given
 * screen wearing that colour.
 */
type Variant = "primary" | "secondary" | "ghost" | "gradient" | "outline";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-accent hover:bg-accent-hover text-black font-semibold",
  secondary: "bg-surface hover:bg-surface-hover text-white border border-border",
  ghost: "bg-transparent hover:bg-surface text-white/80",
  gradient: "bg-accent hover:bg-accent-hover text-black font-semibold",
  outline: "bg-transparent border border-border-strong text-white hover:border-white/40 hover:bg-white/5",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs rounded gap-1.5",
  md: "px-4 py-2.5 text-sm rounded-md gap-2",
  lg: "px-6 py-3 text-[15px] rounded-md gap-2.5",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={clsx(
        "inline-flex items-center justify-center font-medium",
        "transition-[background-color,border-color,transform] duration-150",
        "active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className
      )}
      {...props}
    />
  )
);
Button.displayName = "Button";
