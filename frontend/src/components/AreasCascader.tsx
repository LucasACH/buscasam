"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

type Area = components["schemas"]["AreaDTO"];

async function fetchAreas(): Promise<Area[]> {
  const { data, error } = await api.GET("/api/areas");
  if (error) throw error;
  return data ?? [];
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

  function emit(nextEscuela: string, nextCarrera: string, nextMateria: string) {
    if (requireLeaf) {
      onChange(nextMateria || null);
      return;
    }
    onChange(nextMateria || nextCarrera || nextEscuela || null);
  }

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
          value={escuela}
          onChange={(e) => {
            setEscuela(e.target.value);
            setCarrera("");
            setMateria("");
            emit(e.target.value, "", "");
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
            value={carrera}
            onChange={(e) => {
              setCarrera(e.target.value);
              setMateria("");
              emit(escuela, e.target.value, "");
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
            value={materia}
            onChange={(e) => {
              setMateria(e.target.value);
              emit(escuela, carrera, e.target.value);
            }}
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
