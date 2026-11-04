import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';

export const healthKeys = {
  all: ['health'] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: healthKeys.all,
    queryFn: () => unwrap(api.GET('/health')),
  });
}
