import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';

export const accountKeys = {
  me: ['me'] as const,
};

/** The signed-in user. */
export function useMe() {
  return useQuery({
    queryKey: accountKeys.me,
    queryFn: () => unwrap(api.GET('/me')),
  });
}
