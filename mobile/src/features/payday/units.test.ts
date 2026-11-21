import { newId } from '@/lib/ids';

import type { PlanLine } from './api';
import { groupByTier } from './PlanLines';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));

const line = (position: number, tier: PlanLine['tier']) => ({ position, tier }) as PlanLine;

describe('groupByTier', () => {
  it('groups runs of one tier in waterfall order, whatever order they arrive in', () => {
    const groups = groupByTier([
      line(2, 'essential'),
      line(0, 'bill'),
      line(1, 'bill'),
      line(3, 'goal'),
    ]);

    expect(groups.map((group) => [group.tier, group.lines.map((l) => l.position)])).toEqual([
      ['bill', [0, 1]],
      ['essential', [2]],
      ['goal', [3]],
    ]);
  });

  it('keeps a tier that appears twice as two groups, as the waterfall funded it', () => {
    // Goals without a deadline are funded last, after the emergency fund and other goals.
    const groups = groupByTier([line(0, 'goal'), line(1, 'emergency_fund'), line(2, 'goal')]);
    expect(groups.map((group) => group.tier)).toEqual(['goal', 'emergency_fund', 'goal']);
  });
});

describe('newId', () => {
  it('makes distinct version 4 UUIDs, with or without Web Crypto', () => {
    const crypto = globalThis.crypto;
    const ids = new Set<string>();
    try {
      Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
      for (let i = 0; i < 1000; i += 1) ids.add(newId());
    } finally {
      Object.defineProperty(globalThis, 'crypto', { value: crypto, configurable: true });
    }
    ids.add(newId());
    expect(ids.size).toBe(1001);
    for (const id of ids) {
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    }
  });
});
