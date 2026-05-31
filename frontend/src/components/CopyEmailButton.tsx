"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function CopyEmailButton({ email }: { email: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(email);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Button
      type="button"
      size="icon-sm"
      variant="outline"
      onClick={copy}
      aria-label={copied ? "Correo copiado" : "Copiar correo"}
    >
      {copied ? <Check /> : <Copy />}
    </Button>
  );
}
