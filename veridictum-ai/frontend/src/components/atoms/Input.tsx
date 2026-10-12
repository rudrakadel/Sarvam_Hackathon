/**
 * VeriDictum AI — Input Atom Component
 */

import { clsx } from "clsx";
import type { InputHTMLAttributes } from "react";
import { forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, className, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            "block w-full rounded-lg border px-3 py-2 text-sm",
            "text-gray-900 dark:text-gray-100",
            "placeholder-gray-400 dark:placeholder-gray-500 shadow-sm transition-colors",
            "focus:outline-none focus:ring-2 focus:ring-navy-500 dark:focus:ring-gold-400 focus:border-transparent",
            error
              ? "border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/40"
              : "border-gray-300 bg-white hover:border-gray-400 dark:border-navy-700 dark:bg-navy-900/60 dark:hover:border-navy-600",
            className
          )}
          {...props}
        />
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        {hint && !error && <p className="text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
      </div>
    );
  }
);
Input.displayName = "Input";
