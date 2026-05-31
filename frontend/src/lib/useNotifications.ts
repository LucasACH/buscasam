"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { useUser } from "@/lib/useUser";

export type NotificationDTO = components["schemas"]["NotificationDTO"];

export const NOTIFICATIONS_QUERY_KEY = ["notifications"] as const;
export const UNREAD_COUNT_QUERY_KEY = ["notifications", "unread_count"] as const;

async function fetchNotifications() {
  const { data, error } = await api.GET("/api/notifications");
  if (error) throw error;
  return data!.items;
}

// Keep the list query warm from the always-mounted bell so opening the
// popover hits cache instead of triggering the first fetch.
export function usePrefetchNotifications() {
  const { isInvitado } = useUser();
  useQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    enabled: !isInvitado,
    queryFn: fetchNotifications,
  });
}

export function useUnreadCount() {
  const { isInvitado } = useUser();
  const query = useQuery({
    queryKey: UNREAD_COUNT_QUERY_KEY,
    enabled: !isInvitado,
    refetchOnWindowFocus: true,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/notifications/unread_count");
      if (error) throw error;
      return data!.count;
    },
  });
  return {
    count: isInvitado ? 0 : (query.data ?? 0),
    isLoading: !isInvitado && query.isLoading,
  };
}

export function useNotifications() {
  const { isInvitado } = useUser();
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    enabled: !isInvitado,
    queryFn: fetchNotifications,
  });

  const markRead = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.POST(
        "/api/notifications/{notification_id}/read",
        { params: { path: { notification_id: id } } },
      );
      if (error) throw error;
    },
    onMutate: async (id) => {
      await cancelBoth(qc);
      return flipLocally(qc, (n) => n.id === id);
    },
    onError: (_e, _id, ctx) => rollback(qc, ctx),
    onSettled: () => invalidateBoth(qc),
  });

  const markAllRead = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/notifications/mark_all_read");
      if (error) throw error;
    },
    onMutate: async () => {
      await cancelBoth(qc);
      return flipLocally(qc, () => true);
    },
    onError: (_e, _v, ctx) => rollback(qc, ctx),
    onSettled: () => invalidateBoth(qc),
  });

  return {
    items: isInvitado ? [] : (query.data ?? []),
    isLoading: !isInvitado && query.isLoading,
    markRead: (id: number) => markRead.mutate(id),
    markAllRead: () => markAllRead.mutate(),
  };
}

type Snapshot = {
  items: NotificationDTO[] | undefined;
  count: number | undefined;
};

function flipLocally(
  qc: ReturnType<typeof useQueryClient>,
  shouldFlip: (n: NotificationDTO) => boolean,
): Snapshot {
  const prevItems = qc.getQueryData<NotificationDTO[]>(NOTIFICATIONS_QUERY_KEY);
  const prevCount = qc.getQueryData<number>(UNREAD_COUNT_QUERY_KEY);

  const flipped = (prevItems ?? []).filter(
    (n) => n.read_at === null && shouldFlip(n),
  ).length;

  qc.setQueryData<NotificationDTO[]>(NOTIFICATIONS_QUERY_KEY, (old) =>
    old?.map((n) =>
      n.read_at === null && shouldFlip(n)
        ? { ...n, read_at: new Date().toISOString() }
        : n,
    ),
  );
  qc.setQueryData<number>(UNREAD_COUNT_QUERY_KEY, (c) =>
    Math.max(0, (c ?? 0) - flipped),
  );
  return { items: prevItems, count: prevCount };
}

function rollback(
  qc: ReturnType<typeof useQueryClient>,
  ctx: Snapshot | undefined,
) {
  if (!ctx) return;
  qc.setQueryData(NOTIFICATIONS_QUERY_KEY, ctx.items);
  qc.setQueryData(UNREAD_COUNT_QUERY_KEY, ctx.count);
}

// Cancel in-flight refetches so a slow GET can't land after the optimistic
// flip and clobber it; settle then re-syncs both keys with server truth.
async function cancelBoth(qc: ReturnType<typeof useQueryClient>) {
  await Promise.all([
    qc.cancelQueries({ queryKey: NOTIFICATIONS_QUERY_KEY }),
    qc.cancelQueries({ queryKey: UNREAD_COUNT_QUERY_KEY }),
  ]);
}

function invalidateBoth(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
  qc.invalidateQueries({ queryKey: UNREAD_COUNT_QUERY_KEY });
}
