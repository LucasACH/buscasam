import createClient from "openapi-fetch";
import { toast } from "sonner";

import type { paths } from "./schema";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const TOAST_MESSAGE = "Iniciá sesión para continuar";

export function withAuthToast(
  inner: typeof fetch,
): (input: Request) => Promise<Response> {
  return async (input) => {
    const response = await inner(input);
    if (
      response.status === 401 &&
      UNSAFE_METHODS.has(input.method.toUpperCase())
    ) {
      toast(TOAST_MESSAGE);
    }
    return response;
  };
}

export const api = createClient<paths>({
  fetch: withAuthToast(globalThis.fetch.bind(globalThis)),
});
