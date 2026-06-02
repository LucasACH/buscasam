"use server";

import { revalidatePath } from "next/cache";

// Refresh the público landing caches (count + most-read) the moment a doc is
// published, instead of waiting out the 5-minute ISR window. Invoked from the
// publish mutation; runs on the Next server so revalidatePath applies directly.
export async function revalidateBuscar() {
  revalidatePath("/buscar");
}
