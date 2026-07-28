/**
 * Shared button styles so Capture/Send/Save/Test Connection don't each
 * hand-roll slightly different hover/press/focus states. One accent
 * color (indigo) for primary actions, per the redesign audit's "pick
 * one accent, remove the rest"; timing is 120ms per
 * VisionLearn_Premium_UI_Guide.md's Motion section ("Hover 120ms... No
 * bouncing or distracting effects" — press feedback is a brightness
 * shift, not a scale/bounce).
 */

import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary";

const BASE =
  "rounded-sm px-4 py-2 text-sm font-medium transition-[color,background-color,box-shadow] duration-[120ms] disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-indigo-600 text-white shadow-subtle hover:bg-indigo-700 active:bg-indigo-800",
  secondary: "border border-slate-300 text-slate-700 hover:bg-slate-50 active:bg-slate-100",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }): JSX.Element {
  return <button type="button" className={`${BASE} ${VARIANTS[variant]} ${className}`} {...props} />;
}
