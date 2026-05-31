"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export function BackButton() {
  const router = useRouter();

  function goBack() {
    if (window.history.length > 1) router.back();
    else router.push("/buscar");
  }

  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={goBack}
      className="text-muted-foreground -ml-2 mb-3"
    >
      <ArrowLeft />
      Volver a resultados
    </Button>
  );
}
