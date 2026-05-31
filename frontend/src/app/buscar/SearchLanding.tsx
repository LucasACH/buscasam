"use client";

import { useState } from "react";
import { ArrowUp } from "lucide-react";

import { useUser } from "@/lib/useUser";

import { useMostRead } from "./useMostRead";

const SUGGESTED = [
  "visión por computadora",
  "modelos de lenguaje",
  "microplásticos",
  "algoritmos genéticos",
];

function greetWord(): string {
  const h = new Date().getHours();
  return h < 12 ? "Buenos días" : h < 20 ? "Buenas tardes" : "Buenas noches";
}

function HomeMark() {
  return (
    <svg width={34} height={34} viewBox="0 0 26 26" fill="none" aria-hidden>
      <rect width="26" height="26" rx="7.5" fill="var(--primary)" />
      <circle cx="11" cy="11" r="4.4" stroke="#fff" strokeWidth="2.1" />
      <path
        d="M14.4 14.4 18.5 18.5"
        stroke="#fff"
        strokeWidth="2.1"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function SearchLanding({ onSearch }: { onSearch: (q: string) => void }) {
  const { user, isInvitado } = useUser();
  const { publicTotal } = useMostRead();
  const [q, setQ] = useState("");

  const first = user?.name ? user.name.split(" ")[0] : null;
  const title = first && !isInvitado ? `${greetWord()}, ${first}` : greetWord();
  const submit = () => onSearch(q.trim());

  return (
    <main className="flex min-h-[calc(100dvh-61px)] items-center justify-center px-5 pt-10 pb-18">
      <div className="flex w-full max-w-[660px] flex-col items-center">
        <div className="flex flex-col items-center text-center">
          <HomeMark />
          <h1 className="mt-5 text-[40px] leading-[1.05] font-semibold tracking-[-0.035em]">
            {title}
          </h1>
          <p className="text-muted-foreground mt-2.5 text-[17px] tracking-[-0.01em]">
            ¿Qué querés investigar hoy?
          </p>
        </div>

        <form
          className="mt-[30px] w-full"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="border-border-strong bg-card focus-within:border-primary focus-within:ring-primary-tint flex min-h-[118px] w-full flex-col justify-between rounded-[18px] border py-4 pr-4 pb-3 pl-[18px] shadow-[0_1px_2px_rgba(23,23,23,0.04),0_12px_32px_-16px_rgba(23,23,23,0.18)] transition focus-within:ring-4">
            <textarea
              autoFocus
              rows={1}
              aria-label="Buscar trabajos"
              placeholder="Buscá un tema, título o autor…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              className="placeholder:text-muted-foreground/60 w-full flex-1 resize-none border-none bg-transparent text-[18px] leading-[1.45] tracking-[-0.01em] outline-none"
            />
            <div className="mt-3 flex items-center justify-between">
              <span className="text-muted-foreground/60 inline-flex items-center gap-[7px] text-xs whitespace-nowrap">
                <span className="border-border inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border bg-neutral-50 px-1 font-mono text-[11px]">
                  ↩
                </span>
                <span>para buscar</span>
              </span>
              <button
                type="submit"
                aria-label="Buscar"
                className="bg-primary hover:bg-primary-hover grid size-10 flex-none place-items-center rounded-[11px] text-white shadow-[0_3px_8px_-2px_rgba(29,78,216,0.45)] transition hover:-translate-y-px active:scale-95"
              >
                <ArrowUp className="size-[19px]" />
              </button>
            </div>
          </div>
          <p className="text-muted-foreground/60 mt-3 text-center text-xs">
            Buscando en{" "}
            <b className="text-muted-foreground font-semibold">
              {new Intl.NumberFormat("es-AR").format(publicTotal)}
            </b>{" "}
            trabajos de la comunidad UNSAM
          </p>
        </form>

        <div className="mt-[22px] flex flex-wrap justify-center gap-2">
          {SUGGESTED.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSearch(s)}
              className="border-input bg-card hover:border-border-strong inline-flex h-9 items-center gap-[7px] rounded-full border px-3.5 text-[13.5px] font-medium tracking-[-0.01em] whitespace-nowrap transition hover:bg-neutral-50"
            >
              <span aria-hidden className="text-primary font-mono text-xs">
                ↗
              </span>
              {s}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
