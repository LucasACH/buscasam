"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

type Area = { area_path: string; display_name: string };

async function fetchAreas(): Promise<Area[]> {
  const r = await fetch("/api/areas", { credentials: "same-origin" });
  if (!r.ok) throw new Error(`/api/areas ${r.status}`);
  return (await r.json()) as Area[];
}

function levelOf(area_path: string): number {
  return area_path.split(".").length;
}

function parentOf(area_path: string): string {
  const parts = area_path.split(".");
  parts.pop();
  return parts.join(".");
}

export type AreasCascaderProps = {
  onChange: (area_path: string | null) => void;
  requireLeaf?: boolean;
};

export function AreasCascader({ onChange, requireLeaf }: AreasCascaderProps) {
  const { data } = useQuery({ queryKey: ["areas"], queryFn: fetchAreas });
  const [escuela, setEscuela] = useState<string>("");
  const [carrera, setCarrera] = useState<string>("");
  const [materia, setMateria] = useState<string>("");

  useEffect(() => {
    if (requireLeaf) {
      onChange(materia || null);
      return;
    }
    onChange(materia || carrera || escuela || null);
  }, [escuela, carrera, materia, requireLeaf, onChange]);

  const rows = data ?? [];
  const escuelas = rows.filter((a) => levelOf(a.area_path) === 1);
  const carreras = rows.filter(
    (a) => levelOf(a.area_path) === 2 && parentOf(a.area_path) === escuela,
  );
  const materias = rows.filter(
    (a) => levelOf(a.area_path) === 3 && parentOf(a.area_path) === carrera,
  );

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-sm">
        <span>Escuela</span>
        <select
          aria-label="Escuela"
          value={escuela}
          onChange={(e) => {
            setEscuela(e.target.value);
            setCarrera("");
            setMateria("");
          }}
          className="border-input bg-background h-9 rounded-md border px-2"
        >
          <option value="">Elegí una escuela…</option>
          {escuelas.map((a) => (
            <option key={a.area_path} value={a.area_path}>
              {a.display_name}
            </option>
          ))}
        </select>
      </label>

      {escuela && (
        <label className="flex flex-col gap-1 text-sm">
          <span>Carrera</span>
          <select
            aria-label="Carrera"
            value={carrera}
            onChange={(e) => {
              setCarrera(e.target.value);
              setMateria("");
            }}
            className="border-input bg-background h-9 rounded-md border px-2"
          >
            <option value="">Elegí una carrera…</option>
            {carreras.map((a) => (
              <option key={a.area_path} value={a.area_path}>
                {a.display_name}
              </option>
            ))}
          </select>
        </label>
      )}

      {carrera && (
        <label className="flex flex-col gap-1 text-sm">
          <span>Materia</span>
          <select
            aria-label="Materia"
            value={materia}
            onChange={(e) => setMateria(e.target.value)}
            className="border-input bg-background h-9 rounded-md border px-2"
          >
            <option value="">Elegí una materia…</option>
            {materias.map((a) => (
              <option key={a.area_path} value={a.area_path}>
                {a.display_name}
              </option>
            ))}
          </select>
        </label>
      )}

      {requireLeaf && (escuela || carrera) && !materia && (
        <p className="text-destructive text-xs">Elegí una Materia</p>
      )}
    </div>
  );
}
