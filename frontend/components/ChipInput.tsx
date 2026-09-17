"use client";
import React, { useState, KeyboardEvent } from "react";

interface ChipInputProps {
  values: string[];
  onChange: (newValues: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  label?: string;
  hint?: string;
  id?: string;
}

export default function ChipInput({
  values = [],
  onChange,
  placeholder = "Digite e pressione Enter...",
  suggestions = [],
  label,
  hint,
  id,
}: ChipInputProps) {
  const [inputValue, setInputValue] = useState("");

  const addTag = (tag: string) => {
    const trimmed = tag.trim().replace(/^,+|,+$/g, "");
    if (!trimmed) return;

    const exists = values.some(
      (v) => v.toLowerCase() === trimmed.toLowerCase()
    );
    if (!exists) {
      onChange([...values, trimmed]);
    }
    setInputValue("");
  };

  const removeTag = (indexToRemove: number) => {
    onChange(values.filter((_, idx) => idx !== indexToRemove));
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(inputValue);
    } else if (e.key === "Backspace" && !inputValue && values.length > 0) {
      removeTag(values.length - 1);
    }
  };

  return (
    <div className="w-full space-y-2">
      {label && (
        <label
          htmlFor={id}
          className="text-xs font-semibold text-zinc-300 block"
        >
          {label}
        </label>
      )}

      {/* Caixa de Chips com Input Embutido */}
      <div className="min-h-[46px] p-2 rounded-lg bg-surface-base border border-surface-border/80 focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-500 transition-all flex flex-wrap items-center gap-2">
        {values.map((val, idx) => (
          <span
            key={idx}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-800 text-xs font-medium text-zinc-200"
          >
            <span>{val}</span>
            <button
              type="button"
              onClick={() => removeTag(idx)}
              className="text-zinc-400 hover:text-rose-400 p-0.5 rounded transition-colors"
              aria-label={`Remover ${val}`}
            >
              ✕
            </button>
          </span>
        ))}

        <input
          id={id}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (inputValue.trim()) {
              addTag(inputValue);
            }
          }}
          placeholder={values.length === 0 ? placeholder : "Adicionar outro..."}
          className="flex-1 min-w-[140px] bg-transparent border-0 px-2 py-1 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-0"
        />
      </div>

      {/* Sugestões rápidas com tamanho legível >= 12px */}
      {suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="text-xs text-zinc-400 font-medium mr-1">Sugestões:</span>
          {suggestions
            .filter((s) => !values.some((v) => v.toLowerCase() === s.toLowerCase()))
            .slice(0, 6)
            .map((sug, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => addTag(sug)}
                className="text-xs px-2.5 py-1 rounded-full bg-zinc-800 hover:bg-brand-500 hover:text-zinc-950 text-zinc-300 transition-all min-h-[32px]"
              >
                + {sug}
              </button>
            ))}
        </div>
      )}

      {hint && <p className="text-xs text-zinc-400 mt-1 max-w-prose">{hint}</p>}
    </div>
  );
}
