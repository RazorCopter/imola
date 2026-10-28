import {
  forwardRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "plain" | "primary" | "secondary" | "danger";
};

/** Keeps native form semantics; presentation and interaction states are shared. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "plain", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" &&
          "border border-transparent bg-accent px-4 py-2 text-accent-foreground hover:bg-accent/85",
        variant === "secondary" && "border border-input bg-background px-3 py-2 hover:bg-muted",
        variant === "danger" &&
          "border border-danger-action bg-danger-action px-3 py-2 text-danger-foreground hover:bg-danger-action/85",
        className,
      )}
      {...props}
    />
  );
});

const field =
  "min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground transition-colors disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, type, ...props }, ref) {
    const choice = type === "checkbox" || type === "radio";
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          choice ? "size-4 shrink-0 accent-accent" : field,
          type === "file" &&
            "file:mr-3 file:rounded file:border-0 file:bg-muted file:px-3 file:py-1 file:text-foreground",
          className,
        )}
        {...props}
      />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return <select ref={ref} className={cn(field, "min-h-9", className)} {...props} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn(field, "min-h-24 resize-y", className)} {...props} />;
});
